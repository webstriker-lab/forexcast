import httpx

from app.config import get_settings


def _headers() -> dict:
    settings = get_settings()
    return {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }


def get_llm_settings(user_id: str) -> dict | None:
    """Returns the user's llm_settings row (provider, api_key_encrypted,
    model), or None if they haven't configured a provider yet.
    """
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/llm_settings",
        params={"select": "provider,api_key_encrypted,model", "user_id": f"eq.{user_id}"},
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None
