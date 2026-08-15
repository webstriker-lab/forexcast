import httpx

from app.config import get_settings

BATCH_SIZE = 500
PAGE_SIZE = 1000


def _headers(prefer: str | None = None) -> dict:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def get_rate_series(quote_code: str) -> tuple[list[str], list[float]]:
    """Returns (dates, rates) for `quote_code`'s USD-pivot series, ordered
    oldest to newest -- the same values rates_cache stores for
    (base_code='USD', quote_code=<quote_code>). Paginated explicitly via
    limit/offset so a full ~27-year history is always returned regardless
    of the Supabase project's PostgREST max-rows setting -- an unbounded
    single request would silently truncate to the oldest PAGE_SIZE rows if
    that setting is more restrictive than the true row count.
    """
    settings = get_settings()
    dates: list[str] = []
    rates: list[float] = []
    offset = 0
    while True:
        response = httpx.get(
            f"{settings.supabase_url}/rest/v1/rates_cache",
            params={
                "select": "as_of,rate",
                "base_code": "eq.USD",
                "quote_code": f"eq.{quote_code}",
                "order": "as_of.asc",
                "limit": PAGE_SIZE,
                "offset": offset,
            },
            headers=_headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        rows = response.json()
        dates.extend(row["as_of"] for row in rows)
        rates.extend(float(row["rate"]) for row in rows)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return dates, rates


def insert_predictions(rows: list[dict]) -> None:
    """Appends a batch of prediction rows. Plain insert, not upsert --
    `predictions` has no unique constraint (unlike rates_cache and
    backtest_stats), so each day's run adds a fresh, generated_at-stamped
    batch rather than replacing prior predictions in place. A future
    consumer looking for "today's" prediction for a pair+horizon should
    query for the most recent generated_at.
    """
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/predictions",
            headers=_headers(),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()


def get_backtest_stats(quote_code: str, horizon_days: int) -> dict | None:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/backtest_stats",
        params={
            "select": "error_lower_pct,error_upper_pct,volatility_p90",
            "quote_code": f"eq.{quote_code}",
            "horizon_days": f"eq.{horizon_days}",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    return {
        "error_lower_pct": float(results[0]["error_lower_pct"]),
        "error_upper_pct": float(results[0]["error_upper_pct"]),
        "volatility_p90": float(results[0]["volatility_p90"]),
    }


def upsert_backtest_stats(rows: list[dict]) -> None:
    settings = get_settings()
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/backtest_stats",
        params={"on_conflict": "quote_code,horizon_days"},
        headers=_headers(prefer="resolution=merge-duplicates"),
        json=rows,
        timeout=60.0,
    )
    response.raise_for_status()
