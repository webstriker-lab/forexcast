# backend/app/notifications/supabase_rest.py
from datetime import datetime, timezone

import httpx

from app.config import get_settings


def _headers(prefer: str | None = None) -> dict:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def get_unnotified_alert_events() -> list[dict]:
    """Returns every alert_events row not yet dispatched."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/alert_events",
        params={
            "select": "id,alert_id,fired_at,details",
            "notified_at": "is.null",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def get_alert(alert_id: str) -> dict | None:
    """Returns the parent alert's user_id/base_code/quote_code, or None
    if it no longer exists (defensive -- alerts are only deactivated on
    fire, never deleted, so this should always find a row in practice).
    """
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/alerts",
        params={
            "select": "user_id,base_code,quote_code",
            "id": f"eq.{alert_id}",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def get_notification_settings(user_id: str) -> dict | None:
    """Returns a user's notification_settings row, or None if they have
    none yet (never began linking anything).
    """
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/notification_settings",
        params={
            "select": "telegram_chat_id,telegram_link_code,telegram_link_code_expires_at",
            "user_id": f"eq.{user_id}",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def link_telegram(link_code: str, chat_id: str) -> bool:
    """Finds the notification_settings row whose telegram_link_code
    matches `link_code` and hasn't expired, sets telegram_chat_id/
    telegram_linked_at, and clears both code columns. Returns True if a
    row was updated, False if nothing matched (already consumed, never
    existed, or expired) -- a normal no-op, not an error.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc).isoformat()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/notification_settings",
        params={
            "telegram_link_code": f"eq.{link_code}",
            "telegram_link_code_expires_at": f"gt.{now}",
        },
        headers=_headers(prefer="return=representation"),
        json={
            "telegram_chat_id": chat_id,
            "telegram_linked_at": now,
            "telegram_link_code": None,
            "telegram_link_code_expires_at": None,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    return len(response.json()) > 0


def mark_alert_event_notified(event_id: int) -> None:
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/alert_events",
        params={"id": f"eq.{event_id}"},
        headers=_headers(),
        json={"notified_at": datetime.now(timezone.utc).isoformat()},
        timeout=30.0,
    )
    response.raise_for_status()
