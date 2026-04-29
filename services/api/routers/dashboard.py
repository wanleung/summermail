"""Dashboard web UI endpoint."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from shared.database import get_db_ctx

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Render the main dashboard page."""
    with get_db_ctx() as conn:
        emails = conn.execute(
            "SELECT e.id, e.subject, e.sender_email, e.sender_name, e.received_at, "
            "e.is_read, COALESCE(s.total_score,0) as total_score, "
            "COALESCE(s.vip_match,0) as vip_match "
            "FROM emails e LEFT JOIN email_scores s ON e.id=s.email_id "
            "ORDER BY total_score DESC, e.received_at DESC LIMIT 50"
        ).fetchall()

        today_summary = conn.execute(
            "SELECT summary_text FROM summaries ORDER BY date DESC LIMIT 1"
        ).fetchone()

        last_run = conn.execute(
            "SELECT * FROM fetch_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

        vip_senders = conn.execute("SELECT * FROM vip_senders ORDER BY id").fetchall()
        keywords = conn.execute("SELECT * FROM keywords ORDER BY id").fetchall()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "emails": [dict(e) for e in emails],
            "summary": dict(today_summary) if today_summary else None,
            "last_run": dict(last_run) if last_run else None,
            "vip_senders": [dict(v) for v in vip_senders],
            "keywords": [dict(k) for k in keywords],
        },
    )


@router.get("/emails/{email_id}/view", response_class=HTMLResponse)
def email_detail_view(request: Request, email_id: str):
    """Render the email detail page."""
    from fastapi import HTTPException
    with get_db_ctx() as conn:
        row = conn.execute(
            "SELECT e.*, COALESCE(s.total_score,0) as total_score, "
            "COALESCE(s.vip_match,0) as vip_match, "
            "COALESCE(s.keyword_score,0) as keyword_score, "
            "COALESCE(s.llm_score,0) as llm_score, s.llm_reasoning "
            "FROM emails e LEFT JOIN email_scores s ON e.id=s.email_id "
            "WHERE e.id=?",
            (email_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Email not found")
    return templates.TemplateResponse(
        "email_detail.html", {"request": request, "email": dict(row)}
    )


@router.get("/config", response_class=HTMLResponse)
def config_page(request: Request):
    """Render the configuration settings page."""
    with get_db_ctx() as conn:
        vip_senders = conn.execute("SELECT * FROM vip_senders ORDER BY id").fetchall()
        keywords = conn.execute("SELECT * FROM keywords ORDER BY id").fetchall()
    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "vip_senders": [dict(v) for v in vip_senders],
            "keywords": [dict(k) for k in keywords],
        },
    )
