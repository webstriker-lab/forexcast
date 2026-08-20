from unittest.mock import MagicMock, patch

from app.news.gdelt_client import GDELTRateLimitedError, MAX_RETRIES, fetch_articles


def test_fetch_articles_returns_article_list():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "articles": [
            {
                "title": "Turkey central bank holds rates steady",
                "seendate": "20260816T120000Z",
            },
            {
                "title": "Lira weakens against dollar amid inflation concerns",
                "seendate": "20260816T110000Z",
            },
        ]
    }
    with patch(
        "app.news.gdelt_client.httpx.get", return_value=mock_response
    ) as mock_get:
        result = fetch_articles("Turkey")

    assert len(result) == 2
    assert result[0]["title"] == "Turkey central bank holds rates steady"
    args, kwargs = mock_get.call_args
    assert args[0] == "https://api.gdeltproject.org/api/v2/doc/doc"
    assert "Turkey" in kwargs["params"]["query"]
    assert "theme:ECON_CURRENCY" in kwargs["params"]["query"]
    assert kwargs["params"]["mode"] == "artlist"
    assert kwargs["params"]["format"] == "json"
    assert kwargs["params"]["timespan"] == "48h"


def test_fetch_articles_returns_empty_list_for_no_results():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"articles": []}
    with patch("app.news.gdelt_client.httpx.get", return_value=mock_response):
        result = fetch_articles("SomeObscureRegion")

    assert result == []


def test_fetch_articles_handles_missing_articles_key():
    # GDELT returns a bare {} (confirmed live) for a query with zero
    # matches, not an explicit empty "articles" list.
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {}
    with patch("app.news.gdelt_client.httpx.get", return_value=mock_response):
        result = fetch_articles("SomeObscureRegion")

    assert result == []


def test_fetch_articles_propagates_server_errors():
    import httpx

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=mock_response
    )
    with patch("app.news.gdelt_client.httpx.get", return_value=mock_response):
        try:
            fetch_articles("Turkey")
            assert False, "expected HTTPStatusError to propagate"
        except httpx.HTTPStatusError:
            pass


def test_fetch_articles_retries_on_429_then_succeeds():
    rate_limited = MagicMock()
    rate_limited.status_code = 429
    success = MagicMock()
    success.status_code = 200
    success.raise_for_status.return_value = None
    success.json.return_value = {"articles": [{"title": "Recovered after retry"}]}
    with patch(
        "app.news.gdelt_client.httpx.get", side_effect=[rate_limited, success]
    ) as mock_get, patch("app.news.gdelt_client.time.sleep"):
        result = fetch_articles("Turkey")

    assert result == [{"title": "Recovered after retry"}]
    assert mock_get.call_count == 2


def test_fetch_articles_raises_gdelt_rate_limited_error_after_exhausting_retries():
    # Deliberately does NOT raise via raise_for_status()/HTTPStatusError --
    # a still-429 after exhausting MAX_RETRIES is its own distinct
    # exception type (see GDELTRateLimitedError's docstring), so a
    # caller can catch it specifically and skip that currency rather
    # than treating it the same as a genuine infrastructure failure.
    rate_limited = MagicMock()
    rate_limited.status_code = 429
    with patch(
        "app.news.gdelt_client.httpx.get", return_value=rate_limited
    ) as mock_get, patch("app.news.gdelt_client.time.sleep"):
        try:
            fetch_articles("Turkey")
            assert False, "expected GDELTRateLimitedError to be raised"
        except GDELTRateLimitedError:
            pass

    assert mock_get.call_count == 1 + MAX_RETRIES
    rate_limited.raise_for_status.assert_not_called()
