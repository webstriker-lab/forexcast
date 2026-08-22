from unittest.mock import MagicMock, patch

from app.agent.providers import MAX_RETRIES, PROVIDERS, call_chat_completion


def _mock_completion_response(content: str = "hello") -> MagicMock:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": content}}]
    }
    return mock_response


def test_call_chat_completion_uses_providers_base_url_and_default_model():
    with patch(
        "app.agent.providers.httpx.post", return_value=_mock_completion_response()
    ) as mock_post:
        call_chat_completion("groq", "test-key", None, [{"role": "user", "content": "hi"}], [])

    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.groq.com/openai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["model"] == PROVIDERS["groq"]["default_model"]


def test_call_chat_completion_uses_explicit_model_override():
    with patch(
        "app.agent.providers.httpx.post", return_value=_mock_completion_response()
    ) as mock_post:
        call_chat_completion(
            "openai", "test-key", "gpt-4o", [{"role": "user", "content": "hi"}], []
        )

    assert mock_post.call_args.kwargs["json"]["model"] == "gpt-4o"


def test_call_chat_completion_raises_for_unknown_provider():
    try:
        call_chat_completion("not-a-provider", "key", None, [], [])
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "not-a-provider" in str(exc)


def test_call_chat_completion_retries_on_429_then_succeeds():
    rate_limited = MagicMock()
    rate_limited.status_code = 429
    success = _mock_completion_response("recovered")
    with patch(
        "app.agent.providers.httpx.post", side_effect=[rate_limited, success]
    ) as mock_post, patch("app.agent.providers.time.sleep"):
        result = call_chat_completion(
            "openrouter", "key", None, [{"role": "user", "content": "hi"}], []
        )

    assert result["choices"][0]["message"]["content"] == "recovered"
    assert mock_post.call_count == 2


def test_call_chat_completion_propagates_after_exhausting_retries():
    import httpx

    rate_limited = MagicMock()
    rate_limited.status_code = 429
    rate_limited.raise_for_status.side_effect = httpx.HTTPStatusError(
        "rate limited", request=MagicMock(), response=rate_limited
    )
    with patch(
        "app.agent.providers.httpx.post", return_value=rate_limited
    ) as mock_post, patch("app.agent.providers.time.sleep"):
        try:
            call_chat_completion("gemini", "key", None, [], [])
            assert False, "expected HTTPStatusError to propagate"
        except httpx.HTTPStatusError:
            pass

    assert mock_post.call_count == 1 + MAX_RETRIES
