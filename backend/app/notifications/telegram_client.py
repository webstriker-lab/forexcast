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
