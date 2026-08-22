from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.news.supabase_rest import get_latest_news_sentiment, upsert_news_sentiment


def test_upsert_news_sentiment_posts_with_merge_duplicates():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {
            "currency_code": "TRY",
            "as_of": "2026-08-16",
            "score": -0.6,
            "summary": "Rate hike expected.",
            "article_count": 12,
        }
    ]
    with patch(
        "app.news.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        upsert_news_sentiment(rows)

    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/news_sentiment"
    assert kwargs["params"] == {"on_conflict": "currency_code,as_of"}
    assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates"
    assert kwargs["json"] == rows


def test_get_latest_news_sentiment_returns_todays_row():
    today = date.today().isoformat()
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [
        {"score": -0.6, "summary": "Rate hike expected.", "article_count": 12, "as_of": today}
    ]
    with patch(
        "app.news.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_latest_news_sentiment("TRY")

    assert result == {"score": -0.6, "summary": "Rate hike expected.", "article_count": 12}
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["order"] == "as_of.desc"
    assert kwargs["params"]["limit"] == 1


def test_get_latest_news_sentiment_returns_none_for_stale_row():
    stale = (date.today() - timedelta(days=3)).isoformat()
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [
        {"score": -0.6, "summary": "Old news.", "as_of": stale}
    ]
    with patch("app.news.supabase_rest.httpx.get", return_value=mock_response):
        result = get_latest_news_sentiment("TRY")

    assert result is None


def test_get_latest_news_sentiment_returns_none_when_no_data():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = []
    with patch("app.news.supabase_rest.httpx.get", return_value=mock_response):
        result = get_latest_news_sentiment("TRY")

    assert result is None
