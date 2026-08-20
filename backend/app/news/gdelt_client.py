import time

import httpx

GDELT_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
ECON_THEMES = ["ECON_CURRENCY", "ECON_CENTRALBANK", "ECON_INTERESTRATES", "ECON_INFLATION"]
MAX_RECORDS = 30
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 15


class GDELTRateLimitedError(Exception):
    """Raised when GDELT is still returning 429 after exhausting
    MAX_RETRIES. Deliberately distinct from other HTTP errors (which
    still propagate as httpx.HTTPStatusError via raise_for_status() --
    a genuine infrastructure failure). Live verification across
    multiple real runs showed a shared CI runner IP hitting persistent
    GDELT throttling on *some* currency is common enough to be an
    expected per-currency outcome, not a job-wide emergency -- callers
    should catch this specifically and skip that currency, the same way
    "fewer than MIN_ARTICLES found" is skipped, rather than aborting
    every other currency behind it.
    """


def fetch_articles(country_query: str) -> list[dict]:
    """Fetches recent (last ~48h) GDELT news articles relevant to a
    currency's country/region: filtered by GDELT's own documented
    ECON_* theme taxonomy combined with a plain keyword for the
    country's proper name. Returns [] for zero results -- GDELT
    returning nothing for a given day/country is a normal outcome, not
    an error. Network failures and any non-2xx response other than a
    retried-and-still-failing 429 propagate as httpx.HTTPStatusError --
    those are unexpected and should fail the job loudly. A 429 that
    survives MAX_RETRIES raises GDELTRateLimitedError instead (see that
    class's docstring for why this is handled differently).

    Response shape confirmed live against the DOC 2.0 API: results come
    back as {"articles": [...]}, each article carrying at least "title"
    (plus "seendate", "url", "domain", "language", "sourcecountry" --
    no snippet/excerpt field is present in artlist mode, so downstream
    consumers work from titles only). A query with zero matches returns
    a bare {} rather than {"articles": []}, hence the .get() below.
    GDELT also requires parenthesized theme groups to be OR'd (a lone
    "(theme:X)" is rejected as a syntax error) -- satisfied here since
    ECON_THEMES is always joined with " OR ".
    """
    theme_filter = " OR ".join(f"theme:{t}" for t in ECON_THEMES)
    query = f"({theme_filter}) {country_query}"
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": MAX_RECORDS,
        "timespan": "48h",
    }
    response = httpx.get(GDELT_BASE_URL, params=params, timeout=30.0)
    for attempt in range(MAX_RETRIES):
        if response.status_code != 429:
            break
        time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        response = httpx.get(GDELT_BASE_URL, params=params, timeout=30.0)
    if response.status_code == 429:
        raise GDELTRateLimitedError(
            f"GDELT still rate-limited after {MAX_RETRIES} retries"
        )
    response.raise_for_status()
    data = response.json()
    return data.get("articles", [])
