import httpx

GDELT_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
ECON_THEMES = ["ECON_CURRENCY", "ECON_CENTRALBANK", "ECON_INTERESTRATES", "ECON_INFLATION"]
MAX_RECORDS = 30


def fetch_articles(country_query: str) -> list[dict]:
    """Fetches recent (last ~48h) GDELT news articles relevant to a
    currency's country/region: filtered by GDELT's own documented
    ECON_* theme taxonomy combined with a plain keyword for the
    country's proper name. Returns [] for zero results -- GDELT
    returning nothing for a given day/country is a normal outcome, not
    an error. Network failures, rate-limiting, and any non-2xx response
    propagate -- those are unexpected and should fail the job loudly.

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
    response = httpx.get(
        GDELT_BASE_URL,
        params={
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": MAX_RECORDS,
            "timespan": "48h",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("articles", [])
