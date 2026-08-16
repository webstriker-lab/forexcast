from unittest.mock import patch

from app.news.jobs import run_news_sentiment


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
    rows = mock_upsert.call_args[0][0]
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
    mock_upsert.assert_called_once_with([])


def test_run_news_sentiment_skips_currency_with_unparseable_llm_response_but_continues():
    fake_countries = {"TRY": "Turkey", "EUR": "Eurozone"}
    fake_articles = {c: [{"title": f"h{i}"} for i in range(5)] for c in fake_countries.values()}

    def fake_score(articles):
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
