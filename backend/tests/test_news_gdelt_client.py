from unittest.mock import MagicMock, patch

from app.news.gdelt_client import fetch_articles


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
