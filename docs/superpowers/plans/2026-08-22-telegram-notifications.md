# Telegram Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A scheduled job that links a user's Telegram account via a one-time code and delivers a Telegram message for every alert firing item 3's `run_alert_evaluation` already records to `alert_events`.

**Architecture:** A new `backend/app/notifications/` package: a thin Telegram Bot API client, a message-formatting function shared with a future email channel, Supabase accessors, and one job entrypoint (`run_notifications`) run every 5 minutes by a new GitHub Actions cron. No new backend routes — the one-time linking code is a plain user-owned row the (future) frontend writes directly via existing `notification_settings` RLS, and Telegram's own `getUpdates` offset mechanism is the linking-poll's state store.

**Tech Stack:** Python 3.12, httpx (Telegram Bot API + Supabase REST, matching every existing I/O module), GitHub Actions (new 5-minute cron).

**Spec:** [docs/superpowers/specs/2026-08-22-telegram-notifications-design.md](../specs/2026-08-22-telegram-notifications-design.md)

## Global Constraints

- No live network calls in the automated test suite — every Telegram/Supabase call is mocked. Live verification happens only in this plan's final manual task.
- **`Settings.telegram_bot_token` defaults to `""`.** A required-with-no-default field has broken the live Render API before (a past incident) because every entrypoint constructs `Settings()`.
- A `dispatch_pending_alerts` iteration for a user with no `telegram_chat_id` linked yet is a normal skip (not an error), and the event's `notified_at` stays `null` so a later link doesn't lose it.
- A single failing Telegram send doesn't block other pending alert_events in the same run — collect errors, continue the loop, raise once at the end if any occurred (mirrors `app/recommendations/jobs.py`'s `run_alert_evaluation`).
- `process_telegram_links` needs no persisted offset across runs — Telegram's `getUpdates(offset=...)` call itself is the acknowledgment/state mechanism (see spec §3).
- Never interpolate `${{ }}` directly into a workflow's `run:` shell body — route every dynamic value through an `env:` block first.

## Prerequisite (blocks Task 6's live verification, but not Tasks 1-5)

This plan needs a **new** Telegram bot — free, self-service, no card required:

1. Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow the prompts (choose any name and a unique username ending in `bot`).
2. BotFather replies with an API token like `123456789:AAH...`. Add it to `backend/.env`: `TELEGRAM_BOT_TOKEN=<your token>`.
3. Also add it as a GitHub Actions repo secret named `TELEGRAM_BOT_TOKEN` — needed before Task 6's live workflow run, convenient to do now alongside step 2.

---

### Task 1: Config

**Files:**
- Modify: `backend/app/config.py`

**Interfaces:**
- Produces: `Settings.telegram_bot_token: str` (default `""`), consumed by Task 2's `telegram_client.py`.

No new application logic — plumbing every later task depends on. This plan adds no migration file: `alert_events.notified_at` and `notification_settings.telegram_link_code`/`telegram_link_code_expires_at` are applied directly via `mcp__supabase__apply_migration` in this task, matching how prior plans (2b, 2c) handled additive schema changes.

- [ ] **Step 1: Add the new `Settings` field**

In `backend/app/config.py`, add alongside the existing fields:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_service_key: str
    frontend_origin: str = "http://localhost:5173"
    fred_api_key: str = ""
    llm_api_key: str = ""
    llm_provider: str = ""
    openrouter_api_key: str = ""
    llm_settings_private_key: str = ""
    telegram_bot_token: str = ""
```

- [ ] **Step 2: Run the full suite to confirm nothing broke**

Run: `cd backend && python -m pytest -q`
Expected: PASS, same count as before this task.

- [ ] **Step 3: Apply the schema changes to the live Supabase project**

If `mcp__supabase__apply_migration` isn't already loaded: `ToolSearch(query="select:mcp__supabase__apply_migration")`.

```sql
alter table public.alert_events
    add column notified_at timestamptz;

alter table public.notification_settings
    add column telegram_link_code text,
    add column telegram_link_code_expires_at timestamptz;
```

`mcp__supabase__apply_migration(name="notification_dispatch_state", query="<the exact SQL above>")`

Verify: `mcp__supabase__execute_sql(query="select column_name from information_schema.columns where table_name = 'alert_events' order by ordinal_position")` includes `notified_at`; the same query for `notification_settings` includes `telegram_link_code` and `telegram_link_code_expires_at`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add telegram_bot_token config for the notifications job"
```

---

### Task 2: Telegram Bot API client

**Files:**
- Create: `backend/app/notifications/__init__.py` (empty)
- Create: `backend/app/notifications/telegram_client.py`
- Test: `backend/tests/test_notifications_telegram_client.py`

**Interfaces:**
- Produces: `send_message(chat_id: str, text: str) -> None`, `get_updates(offset: int | None = None) -> list[dict]`, both consumed by Task 5's `jobs.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_notifications_telegram_client.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_notifications_telegram_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.notifications'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/notifications/__init__.py
```

```python
# backend/app/notifications/telegram_client.py
import httpx

from app.config import get_settings

TELEGRAM_API_BASE = "https://api.telegram.org"


def send_message(chat_id: str, text: str) -> None:
    """Sends a plain-text message to a Telegram chat via the Bot API.
    Propagates any non-2xx response (bad token, blocked bot, etc.) as a
    real HTTP failure -- callers decide whether to isolate it per-alert
    or let it fail the whole run.
    """
    settings = get_settings()
    response = httpx.post(
        f"{TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30.0,
    )
    response.raise_for_status()


def get_updates(offset: int | None = None) -> list[dict]:
    """Fetches pending Telegram updates (messages sent to the bot).
    Calling with no `offset` returns every update Telegram hasn't seen
    acknowledged yet; calling again with `offset = <highest update_id
    seen> + 1` acknowledges (clears) them from Telegram's server-side
    queue -- this app persists no offset of its own, see
    app.notifications.jobs.process_telegram_links for how the two calls
    are used together.
    """
    settings = get_settings()
    params: dict = {"timeout": 0}
    if offset is not None:
        params["offset"] = offset
    response = httpx.get(
        f"{TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/getUpdates",
        params=params,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json().get("result", [])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_notifications_telegram_client.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```bash
git add backend/app/notifications/__init__.py backend/app/notifications/telegram_client.py backend/tests/test_notifications_telegram_client.py
git commit -m "feat: add Telegram Bot API client"
```

---

### Task 3: Message formatting

**Files:**
- Create: `backend/app/notifications/message.py`
- Test: `backend/tests/test_notifications_message.py`

**Interfaces:**
- Produces: `build_message(alert: dict, details: dict) -> str`, consumed by Task 5's `jobs.py` (and, per the design spec, reusable verbatim by a future email channel).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_notifications_message.py
from app.notifications.message import build_message


def test_build_message_formats_threshold_alert():
    alert = {"base_code": "USD", "quote_code": "EUR"}
    details = {
        "alert_type": "threshold",
        "current_rate": 1.0487,
        "threshold_rate": 1.05,
        "direction": "below",
    }
    result = build_message(alert, details)

    assert "USD/EUR" in result
    assert "below" in result
    assert "1.05" in result
    assert "1.0487" in result


def test_build_message_formats_recommendation_change_alert():
    alert = {"base_code": "USD", "quote_code": "INR"}
    details = {"alert_type": "recommendation_change", "latest": "act_now", "previous": "wait"}
    result = build_message(alert, details)

    assert "USD/INR" in result
    assert "wait" in result
    assert "act_now" in result


def test_build_message_raises_for_unknown_alert_type():
    alert = {"base_code": "USD", "quote_code": "INR"}
    details = {"alert_type": "something_else"}
    try:
        build_message(alert, details)
        assert False, "expected ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_notifications_message.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.notifications.message'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/notifications/message.py

def build_message(alert: dict, details: dict) -> str:
    """Formats a human-readable notification line from an alert_events
    row's `details` jsonb (written by app.recommendations.jobs,
    unchanged by this module) plus its parent alert's currency pair.

    `recommendation_change` details are trusted to always carry a
    non-null `previous` -- app.recommendations.alerts.recommendation_changed()
    returns False (so no event is ever recorded) whenever `previous` is
    None, so this formatter never needs to guard against that case.
    """
    pair = f"{alert['base_code']}/{alert['quote_code']}"
    alert_type = details.get("alert_type")
    if alert_type == "threshold":
        return (
            f"\U0001F514 {pair} crossed {details['direction']} "
            f"{details['threshold_rate']}: currently {details['current_rate']}"
        )
    if alert_type == "recommendation_change":
        return (
            f"\U0001F4CA {pair} recommendation changed: "
            f"{details['previous']} → {details['latest']}"
        )
    raise ValueError(f"unknown alert_type in details: {alert_type!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_notifications_message.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add backend/app/notifications/message.py backend/tests/test_notifications_message.py
git commit -m "feat: add notification message formatting"
```

---

### Task 4: Supabase accessors

**Files:**
- Create: `backend/app/notifications/supabase_rest.py`
- Test: `backend/tests/test_notifications_supabase_rest.py`

**Interfaces:**
- Produces: `get_unnotified_alert_events() -> list[dict]`, `get_alert(alert_id: str) -> dict | None`, `get_notification_settings(user_id: str) -> dict | None`, `link_telegram(link_code: str, chat_id: str) -> bool`, `mark_alert_event_notified(event_id: int) -> None` — all consumed by Task 5's `jobs.py`.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_notifications_supabase_rest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.notifications.supabase_rest'`

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_notifications_supabase_rest.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add backend/app/notifications/supabase_rest.py backend/tests/test_notifications_supabase_rest.py
git commit -m "feat: add notification Supabase accessors"
```

---

### Task 5: Job entrypoint and CLI

**Files:**
- Create: `backend/app/notifications/jobs.py`
- Create: `backend/app/notifications/cli.py`
- Test: `backend/tests/test_notifications_jobs.py`
- Test: `backend/tests/test_notifications_cli.py`

**Interfaces:**
- Consumes: `send_message`, `get_updates` (Task 2); `build_message` (Task 3); `get_alert`, `get_notification_settings`, `get_unnotified_alert_events`, `link_telegram`, `mark_alert_event_notified` (Task 4).
- Produces: `process_telegram_links() -> int`, `dispatch_pending_alerts() -> int`, `run_notifications() -> dict`, consumed by `cli.py` and Task 6's GitHub Actions workflow.

- [ ] **Step 1: Write the failing tests**

```python
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
```

```python
# backend/tests/test_notifications_cli.py
from unittest.mock import patch

from app.notifications.cli import main


def test_main_calls_run_notifications():
    with patch(
        "app.notifications.cli.run_notifications", return_value={"linked": 1, "sent": 2}
    ) as mock_run:
        main()

    mock_run.assert_called_once()


def test_main_propagates_errors():
    with patch(
        "app.notifications.cli.run_notifications", side_effect=RuntimeError("boom")
    ):
        try:
            main()
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_notifications_jobs.py tests/test_notifications_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.notifications.jobs'`

- [ ] **Step 3: Write the implementation**

```python
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
```

```python
# backend/app/notifications/cli.py
from app.notifications.jobs import run_notifications


def main() -> None:
    result = run_notifications()
    print(f"Linked {result['linked']} Telegram account(s), sent {result['sent']} notification(s)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_notifications_jobs.py tests/test_notifications_cli.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS, all tests (prior count + 25 new from this plan)

- [ ] **Step 6: Commit**

```bash
git add backend/app/notifications/jobs.py backend/app/notifications/cli.py backend/tests/test_notifications_jobs.py backend/tests/test_notifications_cli.py
git commit -m "feat: add notifications job entrypoint and CLI"
```

---

### Task 6: GitHub Actions workflow and live verification

**Files:**
- Create: `.github/workflows/notify.yml`

**Interfaces:** None (wires the finished job to a schedule; no application code).

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/notify.yml
name: Send notifications

on:
  schedule:
    # Every 5 minutes -- tighter than this repo's other daily jobs,
    # deliberately: a user actively linking Telegram in Settings expects
    # near-immediate confirmation, and notified_at-gated dispatch means
    # an idle run with nothing pending costs nothing extra.
    - cron: '*/5 * * * *'
  workflow_dispatch:

jobs:
  notify:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - name: Run notifications job
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
        run: python -m app.notifications.cli
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/notify.yml
git commit -m "feat: add notify.yml GitHub Actions cron"
```

- [ ] **Step 3: Push, then trigger the workflow manually**

Push this branch/PR so the workflow file exists on the default branch (GitHub Actions only picks up `workflow_dispatch`-triggerable workflows once they're present there), then trigger a manual run via the GitHub UI (Actions → "Send notifications" → Run workflow) or `gh workflow run notify.yml` if the `gh` CLI is available.

- [ ] **Step 4: Link a real Telegram account**

Using `mcp__supabase__execute_sql`, insert a linking code directly for your own account (simulating what item 6's frontend will eventually do):

```sql
update public.notification_settings
set telegram_link_code = 'TESTCODE123', telegram_link_code_expires_at = now() + interval '10 minutes'
where user_id = '<your-user-id>';
```

If no row exists yet for your user, insert one instead:

```sql
insert into public.notification_settings (user_id, telegram_link_code, telegram_link_code_expires_at)
values ('<your-user-id>', 'TESTCODE123', now() + interval '10 minutes');
```

Then open Telegram, search for your bot by the username you chose with BotFather, and send it: `/start TESTCODE123`

Wait up to 5 minutes for the next scheduled run (or trigger `workflow_dispatch` again immediately for a faster check), then verify:

```sql
select telegram_chat_id, telegram_linked_at, telegram_link_code from public.notification_settings where user_id = '<your-user-id>';
```

Expected: `telegram_chat_id` is now populated with your Telegram chat id, `telegram_linked_at` is set, `telegram_link_code` is `null` again.

- [ ] **Step 5: Fire a real alert and confirm delivery**

Create a threshold alert that will definitely fire immediately (pick a currency with a current rate you can check via `rates_cache`, and set a threshold trivially crossed):

```sql
select rate from public.rates_cache where base_code = 'USD' and quote_code = 'EUR' order by as_of desc limit 1;
-- note the current rate, then:
insert into public.alerts (user_id, base_code, quote_code, alert_type, threshold_rate, direction)
values ('<your-user-id>', 'USD', 'EUR', 'threshold', 999, 'below');
-- a threshold of 999 with direction 'below' will be crossed by any real EUR rate
```

Trigger `predict.yml`'s recommendation-evaluation path if it isn't already covered by a recent run (or simply wait for its next scheduled run — `run_alert_evaluation` needs to run once to record the `alert_events` row for this new alert), then wait for `notify.yml`'s next run (or trigger it manually). Confirm the message actually arrives in your Telegram chat with the bot, and verify in Supabase:

```sql
select id, alert_id, fired_at, notified_at, details from public.alert_events where alert_id = (select id from public.alerts where user_id = '<your-user-id>' and quote_code = 'EUR' and threshold_rate = 999);
```

Expected: one row, `notified_at` populated, `details` showing `current_rate`/`threshold_rate`/`direction`.

- [ ] **Step 6: Clean up the test alert (optional)**

```sql
delete from public.alerts where user_id = '<your-user-id>' and quote_code = 'EUR' and threshold_rate = 999;
```
