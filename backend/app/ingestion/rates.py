from datetime import date

from app.ingestion.frankfurter import fetch_latest, fetch_range
from app.ingestion.supabase_rest import get_active_currencies, upsert_rates

PIVOT = "USD"


def _non_pivot_currencies() -> list[str]:
    return [code for code in get_active_currencies() if code != PIVOT]


def run_daily() -> int:
    symbols = _non_pivot_currencies()
    data = fetch_latest(PIVOT, symbols)
    as_of = data["date"]
    rows = [
        {"base_code": PIVOT, "quote_code": code, "rate": rate, "as_of": as_of}
        for code, rate in data["rates"].items()
    ]
    upsert_rates(rows)
    return len(rows)


def run_backfill(start_date: str = "1999-01-04", end_date: str | None = None) -> int:
    symbols = _non_pivot_currencies()
    end_date = end_date or date.today().isoformat()
    data = fetch_range(PIVOT, symbols, start_date, end_date)
    rows = [
        {"base_code": PIVOT, "quote_code": code, "rate": rate, "as_of": as_of}
        for as_of, day_rates in data["rates"].items()
        for code, rate in day_rates.items()
    ]
    upsert_rates(rows)
    return len(rows)
