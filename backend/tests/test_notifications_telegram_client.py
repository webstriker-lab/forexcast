from unittest.mock import MagicMock, patch

from app.notifications.telegram_client import get_updates, send_message


def test_send_message_posts_to_telegram_api():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch("app.notifications.telegram_client.get_settings") as mock_settings, patch(
        "app.notifications.telegram_client.httpx.post", return_value=mock_response
    ) as mock_post:
        mock_settings.return_value.telegram_bot_token = "test-token"
        send_message("12345", "hello")

    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.telegram.org/bottest-token/sendMessage"
    assert kwargs["json"] == {"chat_id": "12345", "text": "hello"}


def test_send_message_propagates_http_errors():
    import httpx

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad request", request=MagicMock(), response=mock_response
    )
    with patch("app.notifications.telegram_client.get_settings") as mock_settings, patch(
        "app.notifications.telegram_client.httpx.post", return_value=mock_response
    ):
        mock_settings.return_value.telegram_bot_token = "test-token"
        try:
            send_message("12345", "hello")
            assert False, "expected HTTPStatusError to propagate"
        except httpx.HTTPStatusError:
            pass


def test_get_updates_returns_result_list_with_no_offset_param():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"ok": True, "result": [{"update_id": 1}]}
    with patch("app.notifications.telegram_client.get_settings") as mock_settings, patch(
        "app.notifications.telegram_client.httpx.get", return_value=mock_response
    ) as mock_get:
        mock_settings.return_value.telegram_bot_token = "test-token"
        result = get_updates()

    assert result == [{"update_id": 1}]
    assert "offset" not in mock_get.call_args.kwargs["params"]


def test_get_updates_passes_offset_when_given():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"ok": True, "result": []}
    with patch("app.notifications.telegram_client.get_settings") as mock_settings, patch(
        "app.notifications.telegram_client.httpx.get", return_value=mock_response
    ) as mock_get:
        mock_settings.return_value.telegram_bot_token = "test-token"
        get_updates(offset=42)

    assert mock_get.call_args.kwargs["params"]["offset"] == 42
