"""Summary history endpoints."""
from fastapi import APIRouter, HTTPException

from shared.database import get_db_ctx

router = APIRouter(prefix="/summaries", tags=["summaries"])


@router.get("")
def list_summaries(limit: int = 30):
    """List all summaries."""
    with get_db_ctx() as conn:
        rows = conn.execute(
            "SELECT id, date, summary_text, email_count, top_email_ids, sent_at, sent_to "
            "FROM summaries ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/{summary_id}")
def get_summary(summary_id: int):
    """Get a single summary by ID."""
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT * FROM summaries WHERE id=?", (summary_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Summary not found")
        return dict(row)
