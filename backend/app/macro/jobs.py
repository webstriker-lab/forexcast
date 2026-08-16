import logging

from app.macro.fred_client import fetch_observations
from app.macro.series_map import FRED_SERIES
from app.macro.supabase_rest import upsert_macro_rates

logger = logging.getLogger(__name__)


def run_macro_ingestion() -> int:
    """Refreshes every mapped currency's full FRED observation history.
    Unlike rates_cache, there's no backfill/daily split: FRED's monthly
    series are small (a few hundred rows per currency), so a full
    re-fetch every run is cheap and avoids incremental-update bugs. A
    currency whose series returns no data (fetch_observations -> None)
    is an expected skip, not an error; any other exception (network,
    5xx, rate-limit) propagates and fails the job.
    """
    rows = []
    for currency_code, series_id in FRED_SERIES.items():
        observations = fetch_observations(series_id)
        if observations is None:
            logger.warning(
                "Skipping %s: FRED series %s returned no data", currency_code, series_id
            )
            continue
        rows.extend(
            {
                "currency_code": currency_code,
                "as_of": date,
                "series_id": series_id,
                "rate": rate,
            }
            for date, rate in observations
        )
    if not rows and FRED_SERIES:
        logger.warning(
            "run_macro_ingestion produced zero rows despite %d mapped currencies -- "
            "check FRED_API_KEY and series_map.py",
            len(FRED_SERIES),
        )
    upsert_macro_rates(rows)
    return len(rows)
