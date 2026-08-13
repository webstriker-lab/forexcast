import httpx
from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    settings = get_settings()
    try:
        response = httpx.get(
            f"{settings.supabase_url}/rest/v1/",
            headers={"apikey": settings.supabase_service_key},
            timeout=5.0,
        )
        reachable = response.status_code < 500
    except Exception:
        reachable = False
    return {
        "status": "ok" if reachable else "degraded",
        "supabase_reachable": reachable,
    }
