from unittest.mock import MagicMock, patch

from app.agent.supabase_rest import get_llm_settings


def test_get_llm_settings_returns_the_users_row():
    response = MagicMock()
    response.json.return_value = [
        {"provider": "openrouter", "api_key_encrypted": "ciphertext", "model": None}
    ]
    response.raise_for_status.return_value = None

    with patch(
        "app.agent.supabase_rest.httpx.get", return_value=response
    ) as mock_get:
        result = get_llm_settings("u1")

    assert result["provider"] == "openrouter"
    assert mock_get.call_args.kwargs["params"]["user_id"] == "eq.u1"


def test_get_llm_settings_returns_none_when_not_configured():
    response = MagicMock()
    response.json.return_value = []
    response.raise_for_status.return_value = None

    with patch("app.agent.supabase_rest.httpx.get", return_value=response):
        result = get_llm_settings("u1")

    assert result is None
