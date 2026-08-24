"""Manual pipeline trigger endpoint."""
import os

import httpx
from fastapi import APIRouter, HTTPException

from shared.config import settings

router = APIRouter(tags=["run"])

FETCHER_URL = os.getenv("FETCHER_URL", "http://fetcher:8001")
SCORER_URL = os.getenv("SCORER_URL", "http://scorer:8002")
SUMMARISER_URL = os.getenv("SUMMARISER_URL", "http://summariser:8003")


@router.post("/run")
def trigger_run(scope: str = None):
    """Trigger a manual run of the entire pipeline."""
    scope = scope or settings.fetch_scope
    results = {}
    try:
        r = httpx.post(f"{FETCHER_URL}/run", params={"scope": scope}, timeout=settings.fetcher_run_timeout)
        r.raise_for_status()
        results["fetcher"] = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"fetcher failed: {e}")

    try:
        r = httpx.post(f"{SCORER_URL}/run", timeout=settings.scorer_run_timeout)
        r.raise_for_status()
        results["scorer"] = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"scorer failed: {e}")

    try:
        r = httpx.post(f"{SUMMARISER_URL}/run", timeout=settings.summariser_llm_timeout + 120)
        r.raise_for_status()
        results["summariser"] = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"summariser failed: {e}")

    return results
