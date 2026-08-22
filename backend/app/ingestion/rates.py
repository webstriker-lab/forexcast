from datetime import date

from app.ingestion.frankfurter import fetch_latest, fetch_range
from app.ingestion.supabase_rest import get_active_currencies, upsert_rates

PIVOT = "USD"


def _non_pivot_currencies() -> list[str]:
    return [code for code in get_active_currencies() if code != PIVOT]


def _build_cross_rates(usd_rates: dict[str, float], as_of: str) -> list[dict]:
    """Given USD->X rates, compute all cross-rates X->Y and return rows
    ready for upsert. For example, if USD->INR=83 and USD->EUR=0.92,
    then INR->EUR = 0.92/83 = 0.01108.
    """
    rows = []
    currencies = list(usd_rates.keys())
    for i, base in enumerate(currencies):
        for quote in currencies[i + 1:]:
            rate = usd_rates[quote] / usd_rates[base]
            rows.append({"base_code": base, "quote_code": quote, "rate": round(rate, 6), "as_of": as_of})
            rows.append({"base_code": quote, "quote_code": base, "rate": round(1 / rate, 6), "as_of": as_of})
    return rows


def run_daily() -> int:
    symbols = _non_pivot_currencies()
    data = fetch_latest(PIVOT, symbols)
    as_of = data["date"]
    usd_rates = data["rates"]
    # Store USD->X rates
    rows = [
        {"base_code": PIVOT, "quote_code": code, "rate": rate, "as_of": as_of}
        for code, rate in usd_rates.items()
    ]
    # Store all cross-rates (INR->EUR, EUR->GBP, etc.)
    rows.extend(_build_cross_rates(usd_rates, as_of))
    upsert_rates(rows)
    return len(rows)


def run_backfill(start_date: str = "1999-01-04", end_date: str | None = None) -> int:
    symbols = _non_pivot_currencies()
    end_date = end_date or date.today().isoformat()
    data = fetch_range(PIVOT, symbols, start_date, end_date)
    rows = []
    for as_of, day_rates in data["rates"].items():
        # Store USD->X rates
        rows.extend(
            {"base_code": PIVOT, "quote_code": code, "rate": rate, "as_of": as_of}
            for code, rate in day_rates.items()
        )
        # Store all cross-rates
        rows.extend(_build_cross_rates(day_rates, as_of))
    upsert_rates(rows)
    return len(rows)
