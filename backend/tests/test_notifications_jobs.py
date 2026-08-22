# backend/tests/test_notifications_jobs.py
from unittest.mock import patch

from app.notifications.jobs import (
    dispatch_pending_alerts,
    process_telegram_links,
    run_notifications,
)


def test_process_telegram_links_matches_start_code_and_acks_offset():
    updates = [
        {"update_id": 100, "message": {"chat": {"id": 555}, "text": "/start ABC123"}},
    ]
    with patch(
        "app.notifications.jobs.get_updates", side_effect=[updates, []]
    ) as mock_get_updates, patch(
        "app.notifications.jobs.link_telegram", return_value=True
    ) as mock_link:
        linked = process_telegram_links()

    assert linked == 1
    mock_link.assert_called_once_with("ABC123", "555")
    assert mock_get_updates.call_args_list[1].kwargs.get("offset") == 101


def test_process_telegram_links_ignores_non_start_messages():
    updates = [{"update_id": 100, "message": {"chat": {"id": 555}, "text": "hello there"}}]
    with patch("app.notifications.jobs.get_updates", side_effect=[updates, []]), patch(
        "app.notifications.jobs.link_telegram"
    ) as mock_link:
        linked = process_telegram_links()

    assert linked == 0
    mock_link.assert_not_called()


def test_process_telegram_links_returns_zero_and_skips_ack_when_no_updates():
    with patch("app.notifications.jobs.get_updates", return_value=[]) as mock_get_updates:
        linked = process_telegram_links()

    assert linked == 0
    assert mock_get_updates.call_count == 1


def test_dispatch_pending_alerts_skips_user_without_telegram_linked():
    events = [{"id": 1, "alert_id": "a1", "details": {}}]
    with patch(
        "app.notifications.jobs.get_unnotified_alert_events", return_value=events
    ), patch(
        "app.notifications.jobs.get_alert",
        return_value={"user_id": "u1", "base_code": "USD", "quote_code": "EUR"},
    ), patch(
        "app.notifications.jobs.get_notification_settings",
        return_value={"telegram_chat_id": None},
    ), patch("app.notifications.jobs.send_message") as mock_send, patch(
        "app.notifications.jobs.mark_alert_event_notified"
    ) as mock_mark:
        sent = dispatch_pending_alerts()

    assert sent == 0
    mock_send.assert_not_called()
    mock_mark.assert_not_called()


def test_dispatch_pending_alerts_sends_and_marks_for_linked_user():
    events = [
        {
            "id": 1,
            "alert_id": "a1",
            "details": {
                "alert_type": "threshold",
                "current_rate": 1.04,
                "threshold_rate": 1.05,
                "direction": "below",
            },
        }
    ]
    with patch(
        "app.notifications.jobs.get_unnotified_alert_events", return_value=events
    ), patch(
        "app.notifications.jobs.get_alert",
        return_value={"user_id": "u1", "base_code": "USD", "quote_code": "EUR"},
    ), patch(
        "app.notifications.jobs.get_notification_settings",
        return_value={"telegram_chat_id": "555"},
    ), patch("app.notifications.jobs.send_message") as mock_send, patch(
        "app.notifications.jobs.mark_alert_event_notified"
    ) as mock_mark:
        sent = dispatch_pending_alerts()

    assert sent == 1
    assert mock_send.call_args.args[0] == "555"
    mock_mark.assert_called_once_with(1)


def test_dispatch_pending_alerts_isolates_one_failure_but_raises_at_end():
    events = [
        {
            "id": 1,
            "alert_id": "a1",
            "details": {
                "alert_type": "threshold",
                "current_rate": 1.0,
                "threshold_rate": 1.0,
                "direction": "below",
            },
        },
        {
            "id": 2,
            "alert_id": "a2",
            "details": {
                "alert_type": "threshold",
                "current_rate": 2.0,
                "threshold_rate": 2.0,
                "direction": "below",
            },
        },
    ]

    def fake_get_alert(alert_id):
        return {"user_id": "u1", "base_code": "USD", "quote_code": "EUR"}

    def fake_send(chat_id, text):
        if chat_id == "fail":
            raise RuntimeError("boom")

    with patch(
        "app.notifications.jobs.get_unnotified_alert_events", return_value=events
    ), patch("app.notifications.jobs.get_alert", side_effect=fake_get_alert), patch(
        "app.notifications.jobs.get_notification_settings",
        side_effect=[{"telegram_chat_id": "fail"}, {"telegram_chat_id": "ok"}],
    ), patch("app.notifications.jobs.send_message", side_effect=fake_send), patch(
        "app.notifications.jobs.mark_alert_event_notified"
    ) as mock_mark:
        try:
            dispatch_pending_alerts()
            assert False, "expected ValueError to propagate"
        except ValueError as exc:
            assert "alert_event 1" in str(exc)

    mock_mark.assert_called_once_with(2)


def test_run_notifications_returns_summary():
    with patch("app.notifications.jobs.process_telegram_links", return_value=2), patch(
        "app.notifications.jobs.dispatch_pending_alerts", return_value=3
    ):
        result = run_notifications()

    assert result == {"linked": 2, "sent": 3}
