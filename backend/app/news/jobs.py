import logging
from datetime import date

from app.news.country_map import COUNTRY_NAMES
from app.news.gdelt_client import fetch_articles
from app.news.llm_client import score_sentiment
from app.news.supabase_rest import upsert_news_sentiment

logger = logging.getLogger(__name__)

MIN_ARTICLES = 3


def run_news_sentiment() -> int:
    """Daily job: for every currency with a mapped country/region name,
    fetches recent GDELT news and scores sentiment via the configured
    LLM. A currency with fewer than MIN_ARTICLES articles that day is
    skipped -- insufficient signal, not an error, and score_sentiment is
    never even called for it. A malformed/unparseable LLM response for
    one currency is also skipped (logged), but does not abort the rest
    of the run -- one bad completion shouldn't starve every other
    currency, matching the recommendation-engine plan's per-alert
    isolation fix.
    """
    rows = []
    today = date.today().isoformat()
    for currency_code, country_name in COUNTRY_NAMES.items():
        articles = fetch_articles(country_name)
        if len(articles) < MIN_ARTICLES:
            logger.info(
                "Skipping %s: only %d articles found (need >= %d)",
                currency_code,
                len(articles),
                MIN_ARTICLES,
            )
            continue
        result = score_sentiment(articles)
        if result is None:
            logger.warning(
                "Skipping %s: LLM response did not parse into the expected shape",
                currency_code,
            )
            continue
        rows.append(
            {
                "currency_code": currency_code,
                "as_of": today,
                "score": result["score"],
                "summary": result["summary"],
                "article_count": len(articles),
            }
        )
    upsert_news_sentiment(rows)
    return len(rows)
