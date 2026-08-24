"""Email scorer service orchestration.

Combines three scoring layers:
1. VIP sender matching (+50 if match)
2. Keyword matching (0-10 weight, scaled 0-100)
3. LLM importance classification (0-100)

Formula: raw = (50 if vip else 0) + keyword * 0.3 + llm * 0.7
Final: min(100, int(raw))
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from shared.database import get_db, init_db
from scorer.vip import check_vip
from scorer.keywords import score_keywords
from scorer.llm_scorer import score_llm


def compute_total_score(vip: bool, keyword: int, llm: int) -> int:
    """Compute combined email importance score from three layers.
    
    Args:
        vip: Whether sender is in VIP list
        keyword: Keyword match score (0-100)
        llm: LLM importance score (0-100)
        
    Returns:
        Combined score (0-100)
        
    Formula:
        raw = (50 if vip else 0) + keyword * 0.3 + llm * 0.7
        result = min(100, int(raw))
    """
    keyword = max(0, min(100, keyword))
    llm = max(0, min(100, llm))
    raw = (50 if vip else 0) + keyword * 0.3 + llm * 0.7
    return min(100, int(raw))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context: init DB on startup."""
    conn = get_db()
    init_db(conn)
    conn.close()
    yield


app = FastAPI(title="scorer", lifespan=lifespan)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/run")
def run():
    """Score all unscored emails using the three-layer formula.
    
    Returns:
        JSON with status and count of emails scored
        
    Raises:
        HTTPException: If database error occurs
    """
    conn = get_db()
    try:
        # Find all emails that don't have scores yet
        unscored = conn.execute(
            "SELECT e.id, e.subject, e.sender_email, e.body_text "
            "FROM emails e LEFT JOIN email_scores s ON e.id=s.email_id "
            "WHERE s.email_id IS NULL"
        ).fetchall()

        scored = 0
        failed = 0
        for row in unscored:
            email_id = row["id"]
            subject = row["subject"] or ""
            sender = row["sender_email"] or ""
            body = row["body_text"] or ""

            # Layer 1: VIP check
            vip = check_vip(sender, conn)

            # Layer 2: Keyword scoring
            kw_score = score_keywords(subject, body, conn)

            # Layer 3: LLM scoring. On failure, leave the email unscored rather
            # than persisting a 0 — an unscored row is retried on the next run,
            # a persisted one never is.
            try:
                llm_score, reasoning = score_llm(subject, body)
            except Exception as e:
                print(f"LLM scoring failed for {email_id}, will retry next run: {e}")
                failed += 1
                continue

            # Combine layers using formula
            total = compute_total_score(vip, kw_score, llm_score)

            # Store results, committing per email so a run that is cut short
            # (client timeout, restart) keeps the work it already did
            conn.execute(
                "INSERT OR REPLACE INTO email_scores "
                "(email_id, vip_match, keyword_score, llm_score, total_score, llm_reasoning) "
                "VALUES (?,?,?,?,?,?)",
                (email_id, vip, kw_score, llm_score, total, reasoning),
            )
            conn.commit()
            scored += 1

        return {"status": "success", "emails_scored": scored, "emails_failed": failed}

    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
