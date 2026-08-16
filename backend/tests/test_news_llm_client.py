import json
from unittest.mock import MagicMock, patch

from app.news.llm_client import score_sentiment


def _mock_completion_response(content: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return mock_response


def test_score_sentiment_uses_forced_provider_when_configured():
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post",
        return_value=_mock_completion_response(
            json.dumps({"score": 0.3, "summary": "Mildly positive outlook."})
        ),
    ) as mock_post:
        mock_settings.return_value.llm_api_key = "forced-key"
        mock_settings.return_value.llm_provider = "groq"
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}], "Turkey")

    assert result == {"score": 0.3, "summary": "Mildly positive outlook."}
    args, kwargs = mock_post.call_args
    assert "groq.com" in args[0]
    assert kwargs["headers"]["Authorization"] == "Bearer forced-key"


def test_score_sentiment_falls_back_to_openrouter_when_forced_provider_unset():
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post",
        return_value=_mock_completion_response(
            json.dumps({"score": -0.8, "summary": "Significant negative development."})
        ),
    ) as mock_post:
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}], "Turkey")

    assert result == {"score": -0.8, "summary": "Significant negative development."}
    args, kwargs = mock_post.call_args
    assert "openrouter.ai" in args[0]
    assert kwargs["headers"]["Authorization"] == "Bearer fallback-key"


def test_score_sentiment_raises_when_nothing_configured():
    with patch("app.news.llm_client.get_settings") as mock_settings:
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = ""
        try:
            score_sentiment([{"title": "Some headline"}], "Turkey")
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_score_sentiment_returns_none_for_unparseable_json():
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post",
        return_value=_mock_completion_response("This is not JSON at all."),
    ):
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}], "Turkey")

    assert result is None


def test_score_sentiment_strips_markdown_code_fence():
    fenced = '```json\n{"score": 0.1, "summary": "Neutral-ish."}\n```'
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post",
        return_value=_mock_completion_response(fenced),
    ):
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}], "Turkey")

    assert result == {"score": 0.1, "summary": "Neutral-ish."}


def test_score_sentiment_returns_none_for_out_of_range_score():
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post",
        return_value=_mock_completion_response(
            json.dumps({"score": 5.0, "summary": "Nonsense score."})
        ),
    ):
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}], "Turkey")

    assert result is None


def test_score_sentiment_propagates_server_errors():
    import httpx

    error_response = MagicMock()
    error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=error_response
    )
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post", return_value=error_response
    ):
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        try:
            score_sentiment([{"title": "Some headline"}], "Turkey")
            assert False, "expected HTTPStatusError to propagate"
        except httpx.HTTPStatusError:
            pass


def test_score_sentiment_returns_none_for_missing_choices_key():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"error": {"message": "upstream provider unavailable"}}
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post", return_value=mock_response
    ):
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}], "Turkey")

    assert result is None


def test_score_sentiment_returns_none_for_null_content():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"choices": [{"message": {"content": None}}]}
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post", return_value=mock_response
    ):
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}], "Turkey")

    assert result is None


def test_score_sentiment_includes_country_name_and_skips_titleless_articles():
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post",
        return_value=_mock_completion_response(
            json.dumps({"score": 0.1, "summary": "Fine."})
        ),
    ) as mock_post:
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        score_sentiment(
            [{"title": "Real headline"}, {"no_title_field": True}], "Turkey"
        )

    args, kwargs = mock_post.call_args
    user_message = kwargs["json"]["messages"][1]["content"]
    assert "Turkey" in user_message
    assert "Real headline" in user_message
