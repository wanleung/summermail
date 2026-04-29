"""Email listing and search endpoints."""
from fastapi import APIRouter, HTTPException, Query

from shared.database import get_db_ctx

router = APIRouter(prefix="/emails", tags=["emails"])


@router.get("")
def list_emails(limit: int = 50, min_score: int = 0):
    """List emails with optional score filtering."""
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT e.id, e.subject, e.sender_email, e.sender_name, e.received_at, "
            "e.is_read, s.total_score, s.vip_match "
            "FROM emails e LEFT JOIN email_scores s ON e.id=s.email_id "
            "WHERE COALESCE(s.total_score,0) >= ? "
            "ORDER BY s.total_score DESC, e.received_at DESC LIMIT ?",
            (min_score, limit),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/search")
def search_emails(q: str = Query(..., min_length=1)):
    """Search emails using full-text search."""
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT e.id, e.subject, e.sender_email, e.received_at, "
            "COALESCE(s.total_score,0) as total_score "
            "FROM emails_fts fts "
            "JOIN emails e ON fts.rowid=e.rowid "
            "LEFT JOIN email_scores s ON e.id=s.email_id "
            "WHERE emails_fts MATCH ? "
            "ORDER BY rank LIMIT 30",
            (q,),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/{email_id}")
def get_email(email_id: str):
    """Get a single email by ID."""
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT e.*, s.total_score, s.vip_match, s.keyword_score, "
            "s.llm_score, s.llm_reasoning "
            "FROM emails e LEFT JOIN email_scores s ON e.id=s.email_id "
            "WHERE e.id=?",
            (email_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Email not found")
        return dict(row)
