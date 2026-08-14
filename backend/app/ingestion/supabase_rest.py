import httpx

from app.config import get_settings

BATCH_SIZE = 500


def _headers(prefer: str | None = None) -> dict:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def get_active_currencies() -> list[str]:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/currencies",
        params={"select": "code", "is_active": "eq.true"},
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return sorted(row["code"] for row in response.json())


def upsert_rates(rows: list[dict]) -> None:
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/rates_cache",
            params={"on_conflict": "base_code,quote_code,as_of"},
            headers=_headers(prefer="resolution=merge-duplicates"),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()


def get_usd_rate(as_of: str, currency_code: str) -> float | None:
    if currency_code == "USD":
        return 1.0
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/rates_cache",
        params={
            "select": "rate",
            "base_code": "eq.USD",
            "quote_code": f"eq.{currency_code}",
            "as_of": f"eq.{as_of}",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    results = response.json()
    return float(results[0]["rate"]) if results else None
