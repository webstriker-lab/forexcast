# backend/tests/test_notifications_supabase_rest.py
from unittest.mock import MagicMock, patch

from app.notifications.supabase_rest import (
    get_alert,
    get_notification_settings,
    get_unnotified_alert_events,
    link_telegram,
    mark_alert_event_notified,
)


def test_get_unnotified_alert_events_filters_by_null_notified_at():
    response = MagicMock()
    response.json.return_value = [
        {"id": 1, "alert_id": "a1", "fired_at": "2026-08-22T10:00:00+00:00", "details": {}}
    ]
    response.raise_for_status.return_value = None
    with patch(
        "app.notifications.supabase_rest.httpx.get", return_value=response
    ) as mock_get:
        result = get_unnotified_alert_events()

    assert len(result) == 1
    assert mock_get.call_args.kwargs["params"]["notified_at"] == "is.null"


def test_get_alert_returns_row_when_found():
    response = MagicMock()
    response.json.return_value = [{"user_id": "u1", "base_code": "USD", "quote_code": "EUR"}]
    response.raise_for_status.return_value = None
    with patch("app.notifications.supabase_rest.httpx.get", return_value=response):
        result = get_alert("a1")

    assert result == {"user_id": "u1", "base_code": "USD", "quote_code": "EUR"}


def test_get_alert_returns_none_when_not_found():
    response = MagicMock()
    response.json.return_value = []
    response.raise_for_status.return_value = None
    with patch("app.notifications.supabase_rest.httpx.get", return_value=response):
        result = get_alert("missing")

    assert result is None


def test_get_notification_settings_returns_row():
    response = MagicMock()
    response.json.return_value = [
        {
            "telegram_chat_id": "12345",
            "telegram_link_code": None,
            "telegram_link_code_expires_at": None,
        }
    ]
    response.raise_for_status.return_value = None
    with patch(
        "app.notifications.supabase_rest.httpx.get", return_value=response
    ) as mock_get:
        result = get_notification_settings("u1")

    assert result["telegram_chat_id"] == "12345"
    assert mock_get.call_args.kwargs["params"]["user_id"] == "eq.u1"


def test_get_notification_settings_returns_none_when_no_row():
    response = MagicMock()
    response.json.return_value = []
    response.raise_for_status.return_value = None
    with patch("app.notifications.supabase_rest.httpx.get", return_value=response):
        result = get_notification_settings("u1")

    assert result is None


def test_link_telegram_returns_true_when_code_matches():
    response = MagicMock()
    response.json.return_value = [{"user_id": "u1"}]
    response.raise_for_status.return_value = None
    with patch(
        "app.notifications.supabase_rest.httpx.patch", return_value=response
    ) as mock_patch:
        result = link_telegram("ABC123", "98765")

    assert result is True
    params = mock_patch.call_args.kwargs["params"]
    assert params["telegram_link_code"] == "eq.ABC123"
    assert "telegram_link_code_expires_at" in params
    body = mock_patch.call_args.kwargs["json"]
    assert body["telegram_chat_id"] == "98765"
    assert body["telegram_link_code"] is None
    assert body["telegram_link_code_expires_at"] is None


def test_link_telegram_returns_false_when_no_match():
    response = MagicMock()
    response.json.return_value = []
    response.raise_for_status.return_value = None
    with patch("app.notifications.supabase_rest.httpx.patch", return_value=response):
        result = link_telegram("EXPIRED", "98765")

    assert result is False


def test_mark_alert_event_notified_patches_notified_at():
    response = MagicMock()
    response.raise_for_status.return_value = None
    with patch(
        "app.notifications.supabase_rest.httpx.patch", return_value=response
    ) as mock_patch:
        mark_alert_event_notified(7)

    assert mock_patch.call_args.kwargs["params"]["id"] == "eq.7"
    assert "notified_at" in mock_patch.call_args.kwargs["json"]
