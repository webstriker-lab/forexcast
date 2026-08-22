from datetime import date

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


def upsert_news_sentiment(rows: list[dict]) -> None:
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/news_sentiment",
            params={"on_conflict": "currency_code,as_of"},
            headers=_headers(prefer="resolution=merge-duplicates"),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()


def get_latest_news_sentiment(currency_code: str) -> dict | None:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/news_sentiment",
        params={
            "select": "score,summary,article_count,as_of",
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
    row = rows[0]
    # Deliberately stricter than app.macro's 548-day staleness window --
    # that one tolerates FRED's monthly publication cadence, but a news
    # sentiment reading is a daily signal: anything not dated exactly
    # today is meaningless as "today's shock," not just stale.
    if row["as_of"] != date.today().isoformat():
        return None
    return {
        "score": float(row["score"]),
        "summary": row["summary"],
        "article_count": row["article_count"],
    }
