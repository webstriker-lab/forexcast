import httpx

from app.config import get_settings

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch_observations(series_id: str) -> list[tuple[str, float]] | None:
    """Fetches a FRED series' full observation history (oldest to
    newest). Returns None when FRED doesn't recognize `series_id` (HTTP
    400) or the series has no usable observations -- both mean "no data
    for this currency," not an error, matching the same
    expected-gap-vs-real-error split used everywhere else in this app.
    Missing individual observations (FRED's "." placeholder for a
    not-yet-published or suppressed value) are skipped. Any other HTTP
    error (5xx, timeout, rate-limit) propagates -- those are unexpected
    and should fail the ingestion job loudly.
    """
    settings = get_settings()
    response = httpx.get(
        FRED_BASE_URL,
        params={
            "series_id": series_id,
            "api_key": settings.fred_api_key,
            "file_type": "json",
        },
        timeout=30.0,
    )
    if response.status_code == 400:
        return None
    response.raise_for_status()
    observations = response.json()["observations"]
    result = [
        (obs["date"], float(obs["value"]))
        for obs in observations
        if obs["value"] != "."
    ]
    return result if result else None
