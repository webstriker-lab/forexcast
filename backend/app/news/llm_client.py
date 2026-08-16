import json

import httpx

from app.config import get_settings

PROVIDER_CONFIG = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
    },
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
}
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Verified live 2026-08-16 against https://openrouter.ai/api/v1/models --
# the draft's "deepseek/deepseek-chat-v3.1:free" 404s (no longer listed).
# This is OpenRouter's current free-tier catalog; re-check periodically.
OPENROUTER_FREE_MODEL = "openai/gpt-oss-20b:free"

SYSTEM_PROMPT = (
    "You are a financial news analyst. Given a list of recent news headlines "
    "about a country's economy, judge which headlines are genuinely relevant "
    "to that country's currency outlook (ignore anything tangential), then "
    "respond with ONLY a JSON object of the exact shape "
    '{"score": <float between -1 and 1, negative=bad for the currency, '
    'positive=good for the currency>, "summary": "<one or two sentence '
    'explanation>"}. No markdown, no extra text -- just the JSON object.'
)


def _build_prompt(articles: list[dict]) -> str:
    headlines = "\n".join(f"- {a['title']}" for a in articles)
    return f"Recent headlines:\n{headlines}"


def _call_chat_completion(base_url: str, api_key: str, model: str, articles: list[dict]) -> str:
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(articles)},
            ],
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _parse_response(content: str) -> dict | None:
    text = _strip_code_fence(content)
    try:
        parsed = json.loads(text)
        score = float(parsed["score"])
        summary = str(parsed["summary"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    if not -1.0 <= score <= 1.0:
        return None
    return {"score": score, "summary": summary}


def score_sentiment(articles: list[dict]) -> dict | None:
    """Scores a currency's recent news sentiment via the configured LLM
    provider. If Settings.llm_api_key/llm_provider are both set, that
    provider is used directly -- and if that call fails (auth,
    rate-limit, 5xx, timeout), it propagates rather than silently
    falling back to a different model, since a deliberately-configured
    provider failing is a real problem the caller should know about, not
    something to paper over. Otherwise falls back to
    Settings.openrouter_api_key via a free-tier OpenRouter model. Raises
    ValueError if neither path is configured -- a genuine setup gap.
    Returns None (not raising) when the LLM's response doesn't parse
    into the expected {"score": float in [-1,1], "summary": str} shape
    -- that's a per-currency content problem, not an infrastructure
    failure.
    """
    settings = get_settings()
    if settings.llm_api_key and settings.llm_provider:
        provider = PROVIDER_CONFIG.get(settings.llm_provider)
        if provider is None:
            raise ValueError(f"Unknown llm_provider: {settings.llm_provider!r}")
        content = _call_chat_completion(
            provider["base_url"], settings.llm_api_key, provider["model"], articles
        )
    elif settings.openrouter_api_key:
        content = _call_chat_completion(
            OPENROUTER_BASE_URL, settings.openrouter_api_key, OPENROUTER_FREE_MODEL, articles
        )
    else:
        raise ValueError(
            "No LLM provider configured -- set llm_api_key+llm_provider, "
            "or openrouter_api_key as the guaranteed fallback"
        )
    return _parse_response(content)
