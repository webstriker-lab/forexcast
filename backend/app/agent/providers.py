import time

import httpx

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5

# The five providers llm_settings.provider's check constraint allows.
# All expose an OpenAI-compatible /chat/completions endpoint with
# tools/tool_calls support -- including Gemini, via its documented
# openai-compatibility endpoint -- so one request shape covers all
# five; only base_url and the default model differ per provider.
PROVIDERS = {
    "openai": {"base_url": "https://api.openai.com/v1", "default_model": "gpt-4o-mini"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-chat"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "default_model": "llama-3.3-70b-versatile"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "default_model": "openai/gpt-oss-20b:free"},
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.0-flash",
    },
}


def call_chat_completion(
    provider: str, api_key: str, model: str | None, messages: list[dict], tools: list[dict]
) -> dict:
    """POSTs an OpenAI-compatible chat-completions request to `provider`.
    Retries a 429 up to MAX_RETRIES times with linear backoff -- the
    same pattern already live-verified in app.news.llm_client, kept as
    a separate copy rather than a shared import since this call site is
    genuinely different: a per-user provider choice with no OpenRouter
    fallback -- if a user's own configured provider is down, that's
    surfaced to them directly, not silently swapped for another model.

    Returns the raw parsed JSON response body; interpreting
    choices[0].message (which may itself carry tool_calls) is the
    orchestrator's job, not this function's.

    Raises ValueError for an unknown `provider` name. Any HTTP failure
    that survives the retries propagates via raise_for_status() -- a
    real infrastructure/auth problem, not a content issue.
    """
    config = PROVIDERS.get(provider)
    if config is None:
        raise ValueError(f"Unknown provider: {provider!r}")
    url = f"{config['base_url']}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model or config["default_model"],
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
    }
    response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
    for attempt in range(MAX_RETRIES):
        if response.status_code != 429:
            break
        time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
    response.raise_for_status()
    return response.json()
