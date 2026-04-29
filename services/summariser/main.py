"""FastAPI server for email digest summarization."""
import json
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException
from openai import OpenAI

from shared.database import get_db, init_db
from summariser.prompt import build_prompt, SYSTEM_PROMPT
from summariser.mailer import send_summary_email


# Module-level client placeholder; actual initialization deferred
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """Lazily initialize and return the OpenAI client.
    
    This deferred initialization prevents import-time failures when
    environment variables are absent or config is not yet initialized.
    """
    global _client
    if _client is None:
        from shared.config import settings
        _client = OpenAI(base_url=settings.llm_base_url, api_key="ignored")
    return _client


class _ClientProxy:
    """Proxy object that delegates to the lazily-initialized client.
    
    Allows tests to patch `summariser.main.client` even though the
    actual client is created lazily inside _get_client().
    """

    def __getattr__(self, name):
        """Delegate attribute access to the actual client."""
        return getattr(_get_client(), name)


# Expose module-level 'client' for test patching
client = _ClientProxy()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    conn = get_db()
    init_db(conn)
    conn.close()
    yield


app = FastAPI(title="summariser", lifespan=lifespan)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/run")
def run():
    """Generate and send daily email digest.
    
    Returns:
        JSON response with status and details
    """
    from shared.config import settings
    conn = get_db()
    try:
        today = date.today().isoformat()

        # Check if already summarized today
        existing = conn.execute(
            "SELECT id FROM summaries WHERE date=?", (today,)
        ).fetchone()
        if existing:
            return {"status": "skipped", "reason": "already summarised today"}

        # Fetch top emails by score from last 24 hours
        rows = conn.execute(
            "SELECT e.id, e.subject, e.sender_email, e.sender_name, "
            "e.received_at, e.body_text, s.total_score "
            "FROM emails e JOIN email_scores s ON e.id=s.email_id "
            "WHERE date(e.received_at) >= date('now','-1 day') "
            "ORDER BY s.total_score DESC LIMIT ?",
            (settings.summary_top_n,),
        ).fetchall()

        # Count total emails from last 24 hours
        email_count = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE date(received_at) >= date('now','-1 day')"
        ).fetchone()[0]

        if not rows:
            return {"status": "success", "message": "no emails to summarise"}

        # Convert rows to dicts for prompt building
        email_dicts = [dict(r) for r in rows]
        user_prompt = build_prompt(email_dicts)

        # Call LLM to generate summary
        response = client.chat.completions.create(
            model=settings.summariser_llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        
        # Guard against empty LLM response
        if not response.choices:
            raise ValueError("LLM returned empty response")
        summary_text = response.choices[0].message.content
        if not summary_text:
            raise ValueError("LLM returned empty summary content")

        # Store summary in database (no commit yet)
        top_ids = [r["id"] for r in rows[:10]]
        conn.execute(
            "INSERT INTO summaries (date, summary_text, email_count, top_email_ids) "
            "VALUES (?,?,?,?)",
            (today, summary_text, email_count, json.dumps(top_ids)),
        )

        # Send email — if this raises, rollback will undo the INSERT
        send_summary_email(summary_text, settings.summary_send_to)

        # Mark as sent and commit everything atomically
        conn.execute(
            "UPDATE summaries SET sent_at=datetime('now'), sent_to=? WHERE date=?",
            (settings.summary_send_to, today),
        )
        conn.commit()

        return {"status": "success", "email_count": email_count}
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
