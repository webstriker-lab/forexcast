from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.config import is_llm_configured
from app.news.country_map import COUNTRY_NAMES
from app.news.gdelt_client import fetch_articles
from app.news.llm_client import score_sentiment

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

MIN_ARTICLES = 3


@router.get("/{base}/{quote}/insights")
def get_insights(
    base: str,
    quote: str,
    _user_id: str = Depends(get_current_user),
) -> dict:
    """Returns LLM sentiment for a currency pair.

    Scores the non-USD leg (or quote when neither is USD). Returns
    requires_llm_setup=True when no LLM key is configured so the
    frontend can surface a setup prompt without making a failed call.
    """
    if not is_llm_configured():
        return {"requires_llm_setup": True, "sentiment": None}

    # Pick the currency to score: prefer the non-USD leg; fall back to quote.
    target = quote if base == "USD" else base
    country = COUNTRY_NAMES.get(target)
    if country is None:
        return {"requires_llm_setup": False, "sentiment": None}

    articles = fetch_articles(country)
    if len(articles) < MIN_ARTICLES:
        return {"requires_llm_setup": False, "sentiment": None}

    result = score_sentiment(articles, country)
    return {"requires_llm_setup": False, "sentiment": result}