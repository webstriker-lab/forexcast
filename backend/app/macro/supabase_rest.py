from datetime import date as _date

import httpx

from app.config import get_settings

BATCH_SIZE = 500
PAGE_SIZE = 1000
# Same 548-day (~18 month) staleness window as app.macro.align.align_as_of,
# applied here to the single latest-row lookup: tolerates FRED's monthly
# publication cadence while still catching a genuinely discontinued series.
MAX_STALENESS_DAYS = 548


def _headers(prefer: str | None = None) -> dict:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def upsert_macro_rates(rows: list[dict]) -> None:
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/macro_rates",
            params={"on_conflict": "currency_code,as_of"},
            headers=_headers(prefer="resolution=merge-duplicates"),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()


def get_macro_rate_series(currency_code: str) -> list[tuple[str, float]]:
    settings = get_settings()
    result: list[tuple[str, float]] = []
    offset = 0
    while True:
        response = httpx.get(
            f"{settings.supabase_url}/rest/v1/macro_rates",
            params={
                "select": "as_of,rate",
                "currency_code": f"eq.{currency_code}",
                "order": "as_of.asc",
                "limit": PAGE_SIZE,
                "offset": offset,
            },
            headers=_headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        rows = response.json()
        result.extend((row["as_of"], float(row["rate"])) for row in rows)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return result


def get_latest_macro_rate(currency_code: str) -> float | None:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/macro_rates",
        params={
            "select": "as_of,rate",
            "currency_code": f"eq.{currency_code}",
            "order": "as_of.desc",
            "limit": 1,
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None
    as_of = _date.fromisoformat(rows[0]["as_of"])
    if (_date.today() - as_of).days > MAX_STALENESS_DAYS:
        return None
    return float(rows[0]["rate"])


# --- Generic, table-parameterized versions of the three functions above,
# reused across macro_cpi/macro_gdp/macro_current_account -- macro_rates
# itself keeps using its own dedicated functions, untouched, since it
# predates these and there's no reason to disturb already-stable code.
# All four tables share the identical (currency_code, as_of, series_id,
# rate) shape, so one implementation genuinely fits all of them.


def upsert_series(table: str, rows: list[dict]) -> None:
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/{table}",
            params={"on_conflict": "currency_code,as_of"},
            headers=_headers(prefer="resolution=merge-duplicates"),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()


def get_series_history(table: str, currency_code: str) -> list[tuple[str, float]]:
    settings = get_settings()
    result: list[tuple[str, float]] = []
    offset = 0
    while True:
        response = httpx.get(
            f"{settings.supabase_url}/rest/v1/{table}",
            params={
                "select": "as_of,rate",
                "currency_code": f"eq.{currency_code}",
                "order": "as_of.asc",
                "limit": PAGE_SIZE,
                "offset": offset,
            },
            headers=_headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        rows = response.json()
        result.extend((row["as_of"], float(row["rate"])) for row in rows)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return result


def get_latest_series_value(table: str, currency_code: str) -> float | None:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/{table}",
        params={
            "select": "as_of,rate",
            "currency_code": f"eq.{currency_code}",
            "order": "as_of.desc",
            "limit": 1,
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None
    as_of = _date.fromisoformat(rows[0]["as_of"])
    if (_date.today() - as_of).days > MAX_STALENESS_DAYS:
        return None
    return float(rows[0]["rate"])
