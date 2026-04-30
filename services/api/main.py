"""Main FastAPI application."""
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI

from shared.database import get_db, init_db
from api.routers.dashboard import router as dashboard_router
from api.routers.emails import router as emails_router
from api.routers.summaries_router import router as summaries_router
from api.routers.config_router import router as config_router
from api.routers.run_router import router as run_router, trigger_run


def scheduled_run():
    """Run the pipeline on schedule."""
    from shared.config import settings

    try:
        trigger_run(scope=settings.fetch_scope)
    except Exception as e:
        print(f"Scheduled run failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and scheduler on startup."""
    from shared.config import settings

    conn = get_db()
    init_db(conn)
    conn.close()

    scheduler = AsyncIOScheduler()
    cron_parts = settings.schedule_cron.split()
    if len(cron_parts) != 5:
        raise ValueError(
            f"Invalid schedule_cron '{settings.schedule_cron}': expected 5 parts, got {len(cron_parts)}"
        )

    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(settings.schedule_timezone)
    except Exception as e:
        print(f"Invalid SCHEDULE_TIMEZONE '{settings.schedule_timezone}', falling back to UTC: {e}")
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("UTC")

    scheduler.add_job(
        scheduled_run,
        CronTrigger(
            minute=cron_parts[0],
            hour=cron_parts[1],
            day=cron_parts[2],
            month=cron_parts[3],
            day_of_week=cron_parts[4],
            timezone=tz,
        ),
    )
    scheduler.start()
    print(f"Scheduler started: cron='{settings.schedule_cron}' tz='{settings.schedule_timezone}'")
    yield
    scheduler.shutdown()


app = FastAPI(title="Email Summariser", lifespan=lifespan)

app.include_router(dashboard_router)
app.include_router(emails_router)
app.include_router(summaries_router)
app.include_router(config_router)
app.include_router(run_router)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/search")
def search_proxy(q: str):
    """Search emails (convenience endpoint)."""
    from api.routers.emails import search_emails

    return search_emails(q=q)
