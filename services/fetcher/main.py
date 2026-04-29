import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException

from shared.config import settings
from shared.database import get_db, init_db
from fetcher.imap_client import IMAPClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    conn = get_db()
    init_db(conn)
    conn.close()
    yield


app = FastAPI(title="fetcher", lifespan=lifespan)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/run")
def run(scope: Optional[str] = None):
    """Fetch emails and store in database.
    
    Args:
        scope: Fetch scope ("unread", "since_last_run", or default 24h).
    
    Returns:
        Status and count of new emails fetched.
    """
    scope = scope or settings.fetch_scope
    conn = get_db()
    run_id = conn.execute(
        "INSERT INTO fetch_runs (scope, status) VALUES (?, 'running')", (scope,)
    ).lastrowid
    conn.commit()

    try:
        client = IMAPClient()
        count = client.fetch_emails(scope, conn)
        conn.execute(
            "UPDATE fetch_runs SET status='success', completed_at=datetime('now'), "
            "emails_fetched=? WHERE id=?",
            (count, run_id),
        )
        conn.commit()
        return {"status": "success", "emails_fetched": count, "scope": scope}
    except Exception as exc:
        conn.execute(
            "UPDATE fetch_runs SET status='error', completed_at=datetime('now'), "
            "error_message=? WHERE id=?",
            (str(exc), run_id),
        )
        conn.commit()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
