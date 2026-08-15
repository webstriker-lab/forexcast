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


def get_latest_predictions(quote_code: str) -> list[dict]:
    """Returns the most recent forecast batch for (base_code='USD',
    quote_code=<quote_code>) -- up to 4 rows, one per horizon. Finds the
    exact latest generated_at first, then fetches only rows stamped with
    that exact value, so a currency with fewer than 4 horizons written
    today never gets padded out with a stale row from a previous day.
    """
    settings = get_settings()
    latest_response = httpx.get(
        f"{settings.supabase_url}/rest/v1/predictions",
        params={
            "select": "generated_at",
            "base_code": "eq.USD",
            "quote_code": f"eq.{quote_code}",
            "order": "generated_at.desc",
            "limit": 1,
        },
        headers=_headers(),
        timeout=30.0,
    )
    latest_response.raise_for_status()
    latest_rows = latest_response.json()
    if not latest_rows:
        return []
    latest_generated_at = latest_rows[0]["generated_at"]

    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/predictions",
        params={
            "select": "horizon_days,predicted_rate,lower_bound,upper_bound,confidence",
            "base_code": "eq.USD",
            "quote_code": f"eq.{quote_code}",
            "generated_at": f"eq.{latest_generated_at}",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return [
        {
            "horizon_days": row["horizon_days"],
            "predicted_rate": float(row["predicted_rate"]),
            "lower_bound": float(row["lower_bound"]),
            "upper_bound": float(row["upper_bound"]),
            "confidence": row["confidence"],
        }
        for row in rows
    ]


def get_current_rate(quote_code: str) -> float | None:
    """Returns the most recent USD-pivot rate for `quote_code` from
    rates_cache, or None if no rate exists yet.
    """
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/rates_cache",
        params={
            "select": "rate",
            "base_code": "eq.USD",
            "quote_code": f"eq.{quote_code}",
            "order": "as_of.desc",
            "limit": 1,
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return float(rows[0]["rate"]) if rows else None


def insert_recommendations(rows: list[dict]) -> None:
    """Appends a batch of recommendation rows. Plain insert, not upsert --
    recommendations has no unique constraint, matching predictions'
    append-only pattern (needed so recommendation_change alerts can
    compare today's row against the prior one).
    """
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/recommendations",
            headers=_headers(),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()
