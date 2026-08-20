from unittest.mock import patch

import pytest

from app.news.gdelt_client import GDELTRateLimitedError
from app.news.jobs import run_news_sentiment


@pytest.fixture(autouse=True)
def _no_real_sleep():
    # Tests exercise the proactive inter-request pause's presence via
    # mocking, not by actually waiting GDELT_REQUEST_PAUSE_SECONDS per
    # currency -- this fixture applies to every test in this file.
    with patch("app.news.jobs.time.sleep"):
        yield


def test_run_news_sentiment_scores_and_upserts_currencies_with_enough_coverage():
    # dict insertion order is preserved in Python 3.7+, so COUNTRY_NAMES
    # iterates TRY then EUR -- the two side_effect lists below rely on
    # that call order, not on inspecting which articles were passed.
    fake_countries = {"TRY": "Turkey", "EUR": "Eurozone"}
    fake_articles = [{"title": f"headline {i}"} for i in range(5)]
    fake_scores = [
        {"score": -0.6, "summary": "Negative."},
        {"score": 0.1, "summary": "Neutral."},
    ]
    with patch("app.news.jobs.COUNTRY_NAMES", fake_countries), patch(
        "app.news.jobs.fetch_articles", return_value=fake_articles
    ), patch(
        "app.news.jobs.score_sentiment", side_effect=fake_scores
    ), patch("app.news.jobs.upsert_news_sentiment") as mock_upsert:
        count = run_news_sentiment()

    assert count == 2
    # Each currency is upserted immediately (one call per currency, each
    # with a single-row list), not batched into one call at the end.
    assert mock_upsert.call_count == 2
    rows = [row for call in mock_upsert.call_args_list for row in call[0][0]]
    try_row = next(r for r in rows if r["currency_code"] == "TRY")
    assert try_row["score"] == -0.6
    assert try_row["summary"] == "Negative."
    assert try_row["article_count"] == 5


def test_run_news_sentiment_skips_currency_with_too_few_articles():
    fake_countries = {"TRY": "Turkey"}
    with patch("app.news.jobs.COUNTRY_NAMES", fake_countries), patch(
        "app.news.jobs.fetch_articles", return_value=[{"title": "only one"}]
    ), patch("app.news.jobs.score_sentiment") as mock_score, patch(
        "app.news.jobs.upsert_news_sentiment"
    ) as mock_upsert:
        count = run_news_sentiment()

    assert count == 0
    mock_score.assert_not_called()
    # No currency reached the upsert call -- upsert_news_sentiment is only
    # invoked incrementally, per successfully-scored currency.
    mock_upsert.assert_not_called()


def test_run_news_sentiment_skips_currency_with_unparseable_llm_response_but_continues():
    fake_countries = {"TRY": "Turkey", "EUR": "Eurozone"}
    fake_articles = {c: [{"title": f"h{i}"} for i in range(5)] for c in fake_countries.values()}

    def fake_score(articles, country_name):
        # First call (Turkey) returns None; second call (Eurozone) succeeds.
        if fake_score.calls == 0:
            fake_score.calls += 1
            return None
        return {"score": 0.2, "summary": "Fine."}
    fake_score.calls = 0

    with patch("app.news.jobs.COUNTRY_NAMES", fake_countries), patch(
        "app.news.jobs.fetch_articles", side_effect=lambda q: fake_articles[q]
    ), patch("app.news.jobs.score_sentiment", side_effect=fake_score), patch(
        "app.news.jobs.upsert_news_sentiment"
    ) as mock_upsert:
        count = run_news_sentiment()

    assert count == 1  # TRY skipped (unparseable), EUR still written
    rows = mock_upsert.call_args[0][0]
    assert len(rows) == 1
    assert rows[0]["currency_code"] == "EUR"


def test_run_news_sentiment_skips_currency_rate_limited_by_gdelt_but_continues():
    fake_countries = {"TRY": "Turkey", "EUR": "Eurozone"}
    fake_articles = [{"title": f"h{i}"} for i in range(5)]

    def fake_fetch(country_name):
        if country_name == "Turkey":
            raise GDELTRateLimitedError("still 429 after retries")
        return fake_articles

    with patch("app.news.jobs.COUNTRY_NAMES", fake_countries), patch(
        "app.news.jobs.fetch_articles", side_effect=fake_fetch
    ), patch(
        "app.news.jobs.score_sentiment",
        return_value={"score": 0.2, "summary": "Fine."},
    ) as mock_score, patch(
        "app.news.jobs.upsert_news_sentiment"
    ) as mock_upsert:
        count = run_news_sentiment()

    assert count == 1  # TRY skipped (still rate-limited), EUR still written
    mock_score.assert_called_once()  # never invoked for the rate-limited TRY
    rows = mock_upsert.call_args[0][0]
    assert rows[0]["currency_code"] == "EUR"


def test_run_news_sentiment_propagates_unexpected_errors():
    fake_countries = {"TRY": "Turkey"}
    with patch("app.news.jobs.COUNTRY_NAMES", fake_countries), patch(
        "app.news.jobs.fetch_articles", side_effect=RuntimeError("boom")
    ), patch("app.news.jobs.upsert_news_sentiment") as mock_upsert:
        try:
            run_news_sentiment()
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass
    mock_upsert.assert_not_called()
