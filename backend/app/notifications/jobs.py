# backend/app/notifications/jobs.py
import logging

from app.notifications.message import build_message
from app.notifications.supabase_rest import (
    get_alert,
    get_notification_settings,
    get_unnotified_alert_events,
    link_telegram,
    mark_alert_event_notified,
)
from app.notifications.telegram_client import get_updates, send_message

logger = logging.getLogger(__name__)


def process_telegram_links() -> int:
    """Polls Telegram for pending /start <code> messages and links each
    matching, unexpired code to its notification_settings row. Needs no
    persisted offset -- see telegram_client.get_updates' docstring. If
    there's nothing pending, skips the acknowledgment call entirely
    (nothing to acknowledge). Returns the number of accounts linked.
    """
    updates = get_updates()
    if not updates:
        return 0
    linked = 0
    highest_update_id = 0
    for update in updates:
        highest_update_id = max(highest_update_id, update["update_id"])
        message = update.get("message")
        if not message:
            continue
        text = message.get("text", "")
        if not text.startswith("/start "):
            continue
        code = text.removeprefix("/start ").strip()
        chat_id = str(message["chat"]["id"])
        if link_telegram(code, chat_id):
            linked += 1
    get_updates(offset=highest_update_id + 1)
    return linked


def dispatch_pending_alerts() -> int:
    """Sends a Telegram message for every not-yet-notified alert_event
    whose user has linked Telegram, then marks it notified. A user with
    no telegram_chat_id yet is skipped without marking the event
    notified -- it stays pending so linking later doesn't lose it. One
    failing send doesn't block the rest of the run (collect errors,
    raise once at the end), matching
    app.recommendations.jobs.run_alert_evaluation's existing pattern.
    """
    sent = 0
    errors = []
    for event in get_unnotified_alert_events():
        try:
            alert = get_alert(event["alert_id"])
            if alert is None:
                logger.warning(
                    "Skipping alert_event %s: parent alert no longer exists", event["id"]
                )
                continue
            settings_row = get_notification_settings(alert["user_id"])
            if settings_row is None or not settings_row.get("telegram_chat_id"):
                continue
            text = build_message(alert, event["details"])
            send_message(settings_row["telegram_chat_id"], text)
            mark_alert_event_notified(event["id"])
            sent += 1
        except Exception as exc:
            errors.append(f"alert_event {event['id']}: {exc}")

    if errors:
        raise ValueError(
            f"{len(errors)} alert event(s) failed to dispatch: " + "; ".join(errors)
        )
    return sent


def run_notifications() -> dict:
    """Every-5-minutes job: link any pending Telegram accounts, then
    dispatch any pending alert notifications.
    """
    linked = process_telegram_links()
    sent = dispatch_pending_alerts()
    return {"linked": linked, "sent": sent}
