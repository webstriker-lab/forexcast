# GDELT News-Sentiment Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the daily forecast job with a qualitative news-sentiment confidence flag — a real news shock (from GDELT, scored by a configurable LLM) pushes a currency's `confidence` to `"low"`, the same state 2a's volatility check already reaches, with no change to `predicted_rate`/`lower_bound`/`upper_bound` anywhere.

**Architecture:** A new `backend/app/news/` package handles all GDELT + LLM I/O independently of the prediction package. `backend/app/prediction/jobs.py`'s `run_forecast` gets one additive extension — an extra OR-condition in its existing confidence check — mirroring how 2b's regression layer composed with 2a without touching its core shape.

**Tech Stack:** Python 3.12, httpx (GDELT DOC 2.0 API + any of 4 OpenAI-compatible LLM providers + Supabase REST, matching every existing I/O module), GitHub Actions (new daily `news.yml` cron).

**Spec:** [docs/superpowers/specs/2026-08-16-gdelt-news-sentiment-design.md](../specs/2026-08-16-gdelt-news-sentiment-design.md)

## Global Constraints

- No live network or LLM calls in the automated test suite — every GDELT/LLM/Supabase call is mocked in tests. Live verification happens only in this plan's final manual task.
- A currency with fewer than 3 GDELT articles that day, or an LLM response that doesn't parse into `{"score": float, "summary": str}`, is an expected per-currency skip — logged, never an error, and never aborts the rest of the run.
- GDELT unreachable/5xx/timeout, and the configured LLM provider unreachable/5xx/timeout/auth-failure, both fail loudly (real infrastructure problems, not content issues).
- **Every new `Settings` field defaults to `""`.** 2b's final review found a required-with-no-default field broke the live Render API and three unrelated scheduled workflows on merge, because every entrypoint constructs `Settings()`. This plan adds three fields (`llm_api_key`, `llm_provider`, `openrouter_api_key`) — none may be required.
- Never interpolate `${{ }}` directly into a workflow's `run:` shell body — route every dynamic value through an `env:` block first.
- The sentiment signal never touches `predicted_rate`, `lower_bound`, or `upper_bound` — only the `confidence` enum, and only by adding one more way to reach the `"low"` state 2a already has.
- A sentiment reading only counts if it's from *today* — a stale reading from days ago (e.g. because a scheduled run failed) must not be treated as "today's shock." Apply this at the read layer (`get_latest_news_sentiment` returns `None` for anything not dated today), the same staleness-awareness lesson 2b's final review had to add after the fact for `macro_rates` — build it in from the start this time.

## Prerequisite (blocks Task 10, and Task 4's live model-name verification)

This plan needs a **new** OpenRouter API key — free, self-service, no card required, and it's the mandatory guaranteed-fallback baseline (used whenever `llm_api_key` isn't separately configured):

1. Sign up at https://openrouter.ai/keys (email or GitHub, no card needed) and generate an API key.
2. Add it to `backend/.env`: `OPENROUTER_API_KEY=<your key>`.
3. Also add it as a GitHub Actions repo secret named `OPENROUTER_API_KEY` — needed before Task 10's live workflow run, convenient to do now alongside step 2.

Optionally, if you want to force a specific provider instead of the free OpenRouter fallback, also obtain a key from one of DeepSeek/Groq/Gemini/OpenAI and set `LLM_API_KEY` + `LLM_PROVIDER` (one of `deepseek`/`groq`/`gemini`/`openai`) the same way — both locally and as repo secrets. This is optional; `OPENROUTER_API_KEY` alone is sufficient for every task in this plan, including live verification.

---

### Task 1: Schema and config

**Files:**
- Create: `supabase/migrations/0006_news_sentiment.sql`
- Modify: `backend/app/config.py`

**Interfaces:**
- Produces: `Settings.llm_api_key: str`, `Settings.llm_provider: str`, `Settings.openrouter_api_key: str` (all default `""`), consumed by Task 4's `llm_client.py`.
- Produces: `public.news_sentiment` table, consumed by Task 5.

No new application logic to unit-test — schema plus config plumbing every later task depends on. Verify by confirming the **existing** full test suite still passes unchanged (since all three new fields default to `""`, no `conftest.py` change is needed this time — unlike 2b's `fred_api_key`, nothing here can break an unrelated entrypoint).

- [ ] **Step 1: Write the migration**

```sql
-- supabase/migrations/0006_news_sentiment.sql

-- One LLM-scored sentiment reading per currency per day. Internal
-- computation state only, like backtest_stats/macro_rates -- no
-- consumer outside the prediction pipeline reads this directly yet.
create table public.news_sentiment (
    currency_code text not null references public.currencies (code),
    as_of date not null,
    score numeric not null,
    summary text not null,
    article_count integer not null,
    generated_at timestamptz not null default now(),
    primary key (currency_code, as_of)
);

alter table public.news_sentiment enable row level security;
-- Deliberately no select policy: only the service role (which bypasses
-- RLS) reads or writes this table, matching backtest_stats/macro_rates'
-- convention.
```

- [ ] **Step 2: Add the three new `Settings` fields**

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
```

- [ ] **Step 3: Run the full suite to confirm nothing broke**

Run: `cd backend && python -m pytest -q`
Expected: PASS, same count as before this task.

- [ ] **Step 4: Apply the migration to the live Supabase project**

If `mcp__supabase__apply_migration` isn't already loaded: `ToolSearch(query="select:mcp__supabase__apply_migration")`.

`mcp__supabase__apply_migration(name="news_sentiment", query="<the exact SQL from Step 1>")`

Verify: `mcp__supabase__execute_sql(query="select column_name from information_schema.columns where table_name = 'news_sentiment' order by ordinal_position")` returns `currency_code, as_of, score, summary, article_count, generated_at`.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/0006_news_sentiment.sql backend/app/config.py
git commit -m "feat(db): add news_sentiment table and LLM provider config"
```

---

### Task 2: GDELT client

**Files:**
- Create: `backend/app/news/__init__.py` (empty)
- Create: `backend/app/news/gdelt_client.py`
- Test: `backend/tests/test_news_gdelt_client.py`

**Interfaces:**
- Produces: `fetch_articles(country_query: str) -> list[dict]`, consumed by Task 6's `jobs.py`.

GDELT needs no API key, so its real response shape can and must be checked directly before writing mocked tests against a guessed shape — the exact JSON field names (`articles`, `title`, etc.) and the `timespan` parameter's accepted format are being treated as provisional in this plan's draft and need confirming against the live endpoint.

- [ ] **Step 1: Check GDELT's real response shape live**

```bash
curl -s "https://api.gdeltproject.org/api/v2/doc/doc?query=(theme:ECON_CURRENCY)%20Turkey&mode=artlist&format=json&maxrecords=5&timespan=48h" | head -c 2000
```

Confirm: the response is valid JSON, the article list's top-level key (expected `articles`, confirm or correct), and each article's field names (expected at least `title`; note whether a short excerpt/snippet field exists too, and what it's called if so — if none exists, the LLM prompt in Task 4 works from titles only, which is fine). If `timespan=48h` is rejected or behaves unexpectedly, try `timespan=2d` as an alternative and use whichever one actually works. Record what you found — the implementation in Step 4 must match the *real* shape, not the placeholder above.

- [ ] **Step 2: Write the failing tests, using the real shape confirmed in Step 1**

```python
# backend/tests/test_news_gdelt_client.py
from unittest.mock import MagicMock, patch

from app.news.gdelt_client import fetch_articles


def test_fetch_articles_returns_article_list():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "articles": [
            {"title": "Turkey central bank holds rates steady", "seendate": "20260816120000"},
            {"title": "Lira weakens against dollar amid inflation concerns", "seendate": "20260816110000"},
        ]
    }
    with patch(
        "app.news.gdelt_client.httpx.get", return_value=mock_response
    ) as mock_get:
        result = fetch_articles("Turkey")

    assert len(result) == 2
    assert result[0]["title"] == "Turkey central bank holds rates steady"
    args, kwargs = mock_get.call_args
    assert args[0] == "https://api.gdeltproject.org/api/v2/doc/doc"
    assert "Turkey" in kwargs["params"]["query"]
    assert "theme:ECON_CURRENCY" in kwargs["params"]["query"]
    assert kwargs["params"]["mode"] == "artlist"
    assert kwargs["params"]["format"] == "json"


def test_fetch_articles_returns_empty_list_for_no_results():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"articles": []}
    with patch("app.news.gdelt_client.httpx.get", return_value=mock_response):
        result = fetch_articles("SomeObscureRegion")

    assert result == []


def test_fetch_articles_handles_missing_articles_key():
    # GDELT can return a bare {} for a query with zero matches in some
    # cases, not always an explicit empty "articles" list.
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {}
    with patch("app.news.gdelt_client.httpx.get", return_value=mock_response):
        result = fetch_articles("SomeObscureRegion")

    assert result == []


def test_fetch_articles_propagates_server_errors():
    import httpx

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=mock_response
    )
    with patch("app.news.gdelt_client.httpx.get", return_value=mock_response):
        try:
            fetch_articles("Turkey")
            assert False, "expected HTTPStatusError to propagate"
        except httpx.HTTPStatusError:
            pass
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_news_gdelt_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.news'`

- [ ] **Step 4: Create the package and implement `gdelt_client.py`**

```bash
touch backend/app/news/__init__.py
```

```python
# backend/app/news/gdelt_client.py
import httpx

GDELT_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
ECON_THEMES = ["ECON_CURRENCY", "ECON_CENTRALBANK", "ECON_INTERESTRATES", "ECON_INFLATION"]
MAX_RECORDS = 30


def fetch_articles(country_query: str) -> list[dict]:
    """Fetches recent (last ~48h) GDELT news articles relevant to a
    currency's country/region: filtered by GDELT's own documented
    ECON_* theme taxonomy combined with a plain keyword for the
    country's proper name. Returns [] for zero results -- GDELT
    returning nothing for a given day/country is a normal outcome, not
    an error. Network failures, rate-limiting, and any non-2xx response
    propagate -- those are unexpected and should fail the job loudly.
    """
    theme_filter = " OR ".join(f"theme:{t}" for t in ECON_THEMES)
    query = f"({theme_filter}) {country_query}"
    response = httpx.get(
        GDELT_BASE_URL,
        params={
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": MAX_RECORDS,
            "timespan": "48h",
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("articles", [])
```

(If Step 1 found a different `timespan` value works, or a different top-level JSON key than `articles`, use what you actually confirmed — this code must match the real API, not this draft.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_news_gdelt_client.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/news/__init__.py backend/app/news/gdelt_client.py backend/tests/test_news_gdelt_client.py
git commit -m "feat(backend): add GDELT news client"
```

---

### Task 3: Currency-to-country mapping

**Files:**
- Create: `backend/app/news/country_map.py`
- Test: `backend/tests/test_news_country_map.py`

**Interfaces:**
- Produces: `COUNTRY_NAMES: dict[str, str]` (currency_code -> country/region proper name), consumed by Task 6's `jobs.py`.

Unlike 2b's FRED series IDs, this mapping has no "wrong ID" failure mode to guard against — a currency with genuinely sparse GDELT coverage for its country name just produces a low article count and a normal skip (Task 6's `MIN_ARTICLES` gate). So this is drafted directly, no live-verification loop needed.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_news_country_map.py
from app.news.country_map import COUNTRY_NAMES


def test_country_names_is_nonempty():
    assert len(COUNTRY_NAMES) > 0


def test_country_names_keys_and_values_are_strings():
    for currency_code, country_name in COUNTRY_NAMES.items():
        assert isinstance(currency_code, str) and len(currency_code) == 3
        assert isinstance(country_name, str) and len(country_name) > 0


def test_country_names_covers_all_29_non_usd_currencies():
    expected = {
        "EUR", "GBP", "INR", "JPY", "AUD", "CAD", "CHF", "CNY", "SGD", "NZD",
        "BRL", "CZK", "DKK", "HKD", "HUF", "IDR", "ILS", "ISK", "KRW", "MXN",
        "MYR", "NOK", "PHP", "PLN", "RON", "SEK", "THB", "TRY", "ZAR",
    }
    assert set(COUNTRY_NAMES.keys()) == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_news_country_map.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.news.country_map'`

- [ ] **Step 3: Implement `country_map.py`**

```python
# backend/app/news/country_map.py
# currency_code -> country/region proper name, used as a GDELT search
# keyword (see app.news.gdelt_client). Drafted directly, not verified
# against a live API the way app.macro.series_map's FRED IDs were --
# there's no "wrong mapping" failure mode here, since a currency with
# genuinely sparse GDELT coverage for its country name just produces a
# low article count and a normal skip (app.news.jobs' MIN_ARTICLES
# gate), not an error. Covers all 29 non-USD currencies this app
# tracks (USD itself is excluded, matching _predictable_currencies()
# in app.prediction.jobs -- there's no "USD's own sentiment" needed).
COUNTRY_NAMES: dict[str, str] = {
    "EUR": "Eurozone",
    "GBP": "United Kingdom",
    "INR": "India",
    "JPY": "Japan",
    "AUD": "Australia",
    "CAD": "Canada",
    "CHF": "Switzerland",
    "CNY": "China",
    "SGD": "Singapore",
    "NZD": "New Zealand",
    "BRL": "Brazil",
    "CZK": "Czech Republic",
    "DKK": "Denmark",
    "HKD": "Hong Kong",
    "HUF": "Hungary",
    "IDR": "Indonesia",
    "ILS": "Israel",
    "ISK": "Iceland",
    "KRW": "South Korea",
    "MXN": "Mexico",
    "MYR": "Malaysia",
    "NOK": "Norway",
    "PHP": "Philippines",
    "PLN": "Poland",
    "RON": "Romania",
    "SEK": "Sweden",
    "THB": "Thailand",
    "TRY": "Turkey",
    "ZAR": "South Africa",
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_news_country_map.py -v`
Expected: PASS, all 3 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/news/country_map.py backend/tests/test_news_country_map.py
git commit -m "feat(backend): add currency-to-country mapping for news search"
```

---

### Task 4: LLM client (provider selection + response scoring)

**Files:**
- Create: `backend/app/news/llm_client.py`
- Test: `backend/tests/test_news_llm_client.py`

**Interfaces:**
- Consumes: `app.config.get_settings().llm_api_key`/`llm_provider`/`openrouter_api_key` (Task 1).
- Produces: `score_sentiment(articles: list[dict]) -> dict | None`, consumed by Task 6's `jobs.py`.

This is the most consequential task in the plan — get the provider-selection priority and the fail-loud-vs-skip boundary exactly right. All four candidate providers (DeepSeek, Groq, Gemini, OpenAI) plus OpenRouter expose an OpenAI-compatible `chat/completions` endpoint, confirmed during this plan's design research, so one shared HTTP call function handles all of them.

**Model names below are provisional** — LLM provider catalogs and model IDs shift over time. Before finalizing, verify each one you can actually test (you have a real `OPENROUTER_API_KEY` from the Prerequisite section) against a live call; if a model name is rejected, pick the current equivalent from that provider's own model list and use the real one instead of the draft below.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_news_llm_client.py
import json
from unittest.mock import MagicMock, patch

from app.news.llm_client import score_sentiment


def _mock_completion_response(content: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return mock_response


def test_score_sentiment_uses_forced_provider_when_configured():
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post",
        return_value=_mock_completion_response(
            json.dumps({"score": 0.3, "summary": "Mildly positive outlook."})
        ),
    ) as mock_post:
        mock_settings.return_value.llm_api_key = "forced-key"
        mock_settings.return_value.llm_provider = "groq"
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}])

    assert result == {"score": 0.3, "summary": "Mildly positive outlook."}
    args, kwargs = mock_post.call_args
    assert "groq.com" in args[0]
    assert kwargs["headers"]["Authorization"] == "Bearer forced-key"


def test_score_sentiment_falls_back_to_openrouter_when_forced_provider_unset():
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post",
        return_value=_mock_completion_response(
            json.dumps({"score": -0.8, "summary": "Significant negative development."})
        ),
    ) as mock_post:
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}])

    assert result == {"score": -0.8, "summary": "Significant negative development."}
    args, kwargs = mock_post.call_args
    assert "openrouter.ai" in args[0]
    assert kwargs["headers"]["Authorization"] == "Bearer fallback-key"


def test_score_sentiment_raises_when_nothing_configured():
    with patch("app.news.llm_client.get_settings") as mock_settings:
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = ""
        try:
            score_sentiment([{"title": "Some headline"}])
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_score_sentiment_returns_none_for_unparseable_json():
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post",
        return_value=_mock_completion_response("This is not JSON at all."),
    ):
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}])

    assert result is None


def test_score_sentiment_strips_markdown_code_fence():
    fenced = '```json\n{"score": 0.1, "summary": "Neutral-ish."}\n```'
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post",
        return_value=_mock_completion_response(fenced),
    ):
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}])

    assert result == {"score": 0.1, "summary": "Neutral-ish."}


def test_score_sentiment_returns_none_for_out_of_range_score():
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post",
        return_value=_mock_completion_response(
            json.dumps({"score": 5.0, "summary": "Nonsense score."})
        ),
    ):
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        result = score_sentiment([{"title": "Some headline"}])

    assert result is None


def test_score_sentiment_propagates_server_errors():
    import httpx

    error_response = MagicMock()
    error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=error_response
    )
    with patch("app.news.llm_client.get_settings") as mock_settings, patch(
        "app.news.llm_client.httpx.post", return_value=error_response
    ):
        mock_settings.return_value.llm_api_key = ""
        mock_settings.return_value.llm_provider = ""
        mock_settings.return_value.openrouter_api_key = "fallback-key"
        try:
            score_sentiment([{"title": "Some headline"}])
            assert False, "expected HTTPStatusError to propagate"
        except httpx.HTTPStatusError:
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_news_llm_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.news.llm_client'`

- [ ] **Step 3: Implement `llm_client.py`**

```python
# backend/app/news/llm_client.py
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
OPENROUTER_FREE_MODEL = "deepseek/deepseek-chat-v3.1:free"

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
```

- [ ] **Step 4: Verify each provider's base URL/model name live**

For each provider you can test with a real key (at minimum, OpenRouter — you have `OPENROUTER_API_KEY` from the Prerequisite), run a real call:

```bash
cd backend && python -c "
from app.news.llm_client import _call_chat_completion, OPENROUTER_BASE_URL, OPENROUTER_FREE_MODEL
from app.config import get_settings
key = get_settings().openrouter_api_key
result = _call_chat_completion(OPENROUTER_BASE_URL, key, OPENROUTER_FREE_MODEL, [{'title': 'Test headline about the economy'}])
print(result)
"
```

If this fails because `OPENROUTER_FREE_MODEL`'s exact ID isn't current, check OpenRouter's live free-models list (`https://openrouter.ai/models?max_price=0` or the models API) and update the constant to a real, currently-live `:free`-suffixed model ID. If you have keys for any of the other four providers, repeat this check against their `PROVIDER_CONFIG` entries too and correct any rejected model name to that provider's current equivalent. Do not skip this step even though the automated tests (Step 2) all pass with mocks — mocked tests can't catch a stale model ID, only a real call can.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_news_llm_client.py -v`
Expected: PASS, all 7 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/news/llm_client.py backend/tests/test_news_llm_client.py
git commit -m "feat(backend): add configurable multi-provider LLM sentiment client"
```

---

### Task 5: News Supabase I/O

**Files:**
- Create: `backend/app/news/supabase_rest.py`
- Test: `backend/tests/test_news_supabase_rest.py`

**Interfaces:**
- Produces: `upsert_news_sentiment(rows: list[dict]) -> None`, `get_latest_news_sentiment(currency_code: str) -> dict | None`, consumed by Task 6's `jobs.py` and Task 9's `prediction/jobs.py`.

`get_latest_news_sentiment` deliberately only returns a result when the most recent row's `as_of` is literally today's date — a stale reading from a prior day (e.g. because a scheduled run failed) must not be treated as "today's shock." This is the same staleness lesson 2b's final review had to retrofit onto `macro_rates`/`align_as_of` after the fact; it's built in from the start here.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_news_supabase_rest.py
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.news.supabase_rest import get_latest_news_sentiment, upsert_news_sentiment


def test_upsert_news_sentiment_posts_with_merge_duplicates():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {
            "currency_code": "TRY",
            "as_of": "2026-08-16",
            "score": -0.6,
            "summary": "Rate hike expected.",
            "article_count": 12,
        }
    ]
    with patch(
        "app.news.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        upsert_news_sentiment(rows)

    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/news_sentiment"
    assert kwargs["params"] == {"on_conflict": "currency_code,as_of"}
    assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates"
    assert kwargs["json"] == rows


def test_get_latest_news_sentiment_returns_todays_row():
    today = date.today().isoformat()
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [
        {"score": -0.6, "summary": "Rate hike expected.", "as_of": today}
    ]
    with patch(
        "app.news.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_latest_news_sentiment("TRY")

    assert result == {"score": -0.6, "summary": "Rate hike expected."}
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["order"] == "as_of.desc"
    assert kwargs["params"]["limit"] == 1


def test_get_latest_news_sentiment_returns_none_for_stale_row():
    stale = (date.today() - timedelta(days=3)).isoformat()
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = [
        {"score": -0.6, "summary": "Old news.", "as_of": stale}
    ]
    with patch("app.news.supabase_rest.httpx.get", return_value=mock_response):
        result = get_latest_news_sentiment("TRY")

    assert result is None


def test_get_latest_news_sentiment_returns_none_when_no_data():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = []
    with patch("app.news.supabase_rest.httpx.get", return_value=mock_response):
        result = get_latest_news_sentiment("TRY")

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_news_supabase_rest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.news.supabase_rest'`

- [ ] **Step 3: Implement `supabase_rest.py`**

```python
# backend/app/news/supabase_rest.py
from datetime import date

import httpx

from app.config import get_settings

BATCH_SIZE = 500


def _headers(prefer: str | None = None) -> dict:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def upsert_news_sentiment(rows: list[dict]) -> None:
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/news_sentiment",
            params={"on_conflict": "currency_code,as_of"},
            headers=_headers(prefer="resolution=merge-duplicates"),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()


def get_latest_news_sentiment(currency_code: str) -> dict | None:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/news_sentiment",
        params={
            "select": "score,summary,as_of",
            "currency_code": f"eq.{currency_code}",
            "order": "as_of.desc",
            "limit": 1,
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None
    row = rows[0]
    if row["as_of"] != date.today().isoformat():
        return None
    return {"score": float(row["score"]), "summary": row["summary"]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_news_supabase_rest.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/news/supabase_rest.py backend/tests/test_news_supabase_rest.py
git commit -m "feat(backend): add news sentiment Supabase I/O layer"
```

---

### Task 6: News sentiment orchestration

**Files:**
- Create: `backend/app/news/jobs.py`
- Test: `backend/tests/test_news_jobs.py`

**Interfaces:**
- Consumes: `COUNTRY_NAMES` (Task 3), `fetch_articles` (Task 2), `score_sentiment` (Task 4), `upsert_news_sentiment` (Task 5).
- Produces: `run_news_sentiment() -> int`, consumed by Task 7's `cli.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_news_jobs.py
from unittest.mock import patch

from app.news.jobs import run_news_sentiment


def test_run_news_sentiment_scores_and_upserts_currencies_with_enough_coverage():
    # dict insertion order is preserved in Python 3.7+, so COUNTRY_NAMES
    # iterates TRY then EUR -- the two side_effect lists below rely on
    # that call order, not on inspecting which articles were passed.
    fake_countries = {"TRY": "Turkey", "EUR": "Eurozone"}
    fake_articles = [{"title": f"headline {i}"} for i in range(5)]
    fake_scores = [
        {"score": -0.6, "summary": "Negative."},
        {"score": 0.1, "summary": "Neutral."},
    ]
    with patch("app.news.jobs.COUNTRY_NAMES", fake_countries), patch(
        "app.news.jobs.fetch_articles", return_value=fake_articles
    ), patch(
        "app.news.jobs.score_sentiment", side_effect=fake_scores
    ), patch("app.news.jobs.upsert_news_sentiment") as mock_upsert:
        count = run_news_sentiment()

    assert count == 2
    rows = mock_upsert.call_args[0][0]
    try_row = next(r for r in rows if r["currency_code"] == "TRY")
    assert try_row["score"] == -0.6
    assert try_row["summary"] == "Negative."
    assert try_row["article_count"] == 5


def test_run_news_sentiment_skips_currency_with_too_few_articles():
    fake_countries = {"TRY": "Turkey"}
    with patch("app.news.jobs.COUNTRY_NAMES", fake_countries), patch(
        "app.news.jobs.fetch_articles", return_value=[{"title": "only one"}]
    ), patch("app.news.jobs.score_sentiment") as mock_score, patch(
        "app.news.jobs.upsert_news_sentiment"
    ) as mock_upsert:
        count = run_news_sentiment()

    assert count == 0
    mock_score.assert_not_called()
    mock_upsert.assert_called_once_with([])


def test_run_news_sentiment_skips_currency_with_unparseable_llm_response_but_continues():
    fake_countries = {"TRY": "Turkey", "EUR": "Eurozone"}
    fake_articles = {c: [{"title": f"h{i}"} for i in range(5)] for c in fake_countries.values()}

    def fake_score(articles):
        # First call (Turkey) returns None; second call (Eurozone) succeeds.
        if fake_score.calls == 0:
            fake_score.calls += 1
            return None
        return {"score": 0.2, "summary": "Fine."}
    fake_score.calls = 0

    with patch("app.news.jobs.COUNTRY_NAMES", fake_countries), patch(
        "app.news.jobs.fetch_articles", side_effect=lambda q: fake_articles[q]
    ), patch("app.news.jobs.score_sentiment", side_effect=fake_score), patch(
        "app.news.jobs.upsert_news_sentiment"
    ) as mock_upsert:
        count = run_news_sentiment()

    assert count == 1  # TRY skipped (unparseable), EUR still written
    rows = mock_upsert.call_args[0][0]
    assert len(rows) == 1
    assert rows[0]["currency_code"] == "EUR"


def test_run_news_sentiment_propagates_unexpected_errors():
    fake_countries = {"TRY": "Turkey"}
    with patch("app.news.jobs.COUNTRY_NAMES", fake_countries), patch(
        "app.news.jobs.fetch_articles", side_effect=RuntimeError("boom")
    ), patch("app.news.jobs.upsert_news_sentiment") as mock_upsert:
        try:
            run_news_sentiment()
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass
    mock_upsert.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_news_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.news.jobs'`

- [ ] **Step 3: Implement `jobs.py`**

```python
# backend/app/news/jobs.py
import logging
from datetime import date

from app.news.country_map import COUNTRY_NAMES
from app.news.gdelt_client import fetch_articles
from app.news.llm_client import score_sentiment
from app.news.supabase_rest import upsert_news_sentiment

logger = logging.getLogger(__name__)

MIN_ARTICLES = 3


def run_news_sentiment() -> int:
    """Daily job: for every currency with a mapped country/region name,
    fetches recent GDELT news and scores sentiment via the configured
    LLM. A currency with fewer than MIN_ARTICLES articles that day is
    skipped -- insufficient signal, not an error, and score_sentiment is
    never even called for it. A malformed/unparseable LLM response for
    one currency is also skipped (logged), but does not abort the rest
    of the run -- one bad completion shouldn't starve every other
    currency, matching the recommendation-engine plan's per-alert
    isolation fix.
    """
    rows = []
    today = date.today().isoformat()
    for currency_code, country_name in COUNTRY_NAMES.items():
        articles = fetch_articles(country_name)
        if len(articles) < MIN_ARTICLES:
            logger.info(
                "Skipping %s: only %d articles found (need >= %d)",
                currency_code,
                len(articles),
                MIN_ARTICLES,
            )
            continue
        result = score_sentiment(articles)
        if result is None:
            logger.warning(
                "Skipping %s: LLM response did not parse into the expected shape",
                currency_code,
            )
            continue
        rows.append(
            {
                "currency_code": currency_code,
                "as_of": today,
                "score": result["score"],
                "summary": result["summary"],
                "article_count": len(articles),
            }
        )
    upsert_news_sentiment(rows)
    return len(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_news_jobs.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/news/jobs.py backend/tests/test_news_jobs.py
git commit -m "feat(backend): add news sentiment orchestration"
```

---

### Task 7: News CLI

**Files:**
- Create: `backend/app/news/cli.py`
- Test: `backend/tests/test_news_cli.py`

**Interfaces:**
- Consumes: `run_news_sentiment` (Task 6).
- Produces: `main() -> None`, invoked by Task 8's `news.yml` as `python -m app.news.cli`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_news_cli.py
from unittest.mock import patch

from app.news.cli import main


def test_main_calls_run_news_sentiment():
    with patch("app.news.cli.run_news_sentiment", return_value=17) as mock_run:
        main()

    mock_run.assert_called_once()


def test_main_propagates_errors():
    with patch("app.news.cli.run_news_sentiment", side_effect=RuntimeError("boom")):
        try:
            main()
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_news_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.news.cli'`

- [ ] **Step 3: Implement `cli.py`**

```python
# backend/app/news/cli.py
from app.news.jobs import run_news_sentiment


def main() -> None:
    count = run_news_sentiment()
    print(f"Scored {count} currencies")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_news_cli.py -v`
Expected: PASS, both tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/news/cli.py backend/tests/test_news_cli.py
git commit -m "feat(backend): add news sentiment CLI entrypoint"
```

---

### Task 8: News sentiment GitHub Actions workflow

**Files:**
- Create: `.github/workflows/news.yml`

**Interfaces:**
- Consumes: `python -m app.news.cli` (Task 7), repo secrets `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (existing), `OPENROUTER_API_KEY` (new — see Prerequisite), `LLM_API_KEY`/`LLM_PROVIDER` (new, optional).

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/news.yml
name: Score news sentiment

on:
  schedule:
    # Daily, 17:45 UTC -- 15 minutes before predict.yml's daily forecast
    # cron (18:00 UTC), so today's sentiment is already in
    # news_sentiment when run_forecast reads it.
    - cron: '45 17 * * *'
  workflow_dispatch:

jobs:
  score-news:
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
      - name: Run news sentiment job
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
          LLM_PROVIDER: ${{ secrets.LLM_PROVIDER }}
        run: python -m app.news.cli
```

Note this workflow has no `${{ }}` anywhere inside a shell `run:` body (the single-line `run:` here is a plain command, not shell-interpolated) — every dynamic value flows through `env:`, consistent with every prior workflow's fix for this exact class of injection risk. `LLM_API_KEY`/`LLM_PROVIDER` reference secrets that may not exist in the repo yet (if you haven't set up a forced provider) — GitHub Actions resolves an unset secret reference to an empty string, which is exactly the "fall back to OpenRouter" case `llm_client.py` already handles, not a workflow error.

- [ ] **Step 2: Validate the YAML**

Run: `cd .github/workflows && python -c "import yaml; yaml.safe_load(open('news.yml'))" && echo "valid"`
Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/news.yml
git commit -m "ci: add scheduled GitHub Actions workflow for news sentiment"
```

---

### Task 9: Wire sentiment into the daily forecast's confidence flag

**Files:**
- Modify: `backend/app/prediction/jobs.py`
- Test: `backend/tests/test_jobs.py`

**Interfaces:**
- Consumes: `get_latest_news_sentiment` (Task 5).
- Produces: `run_forecast() -> int` (same signature as before — this task changes its body only, nothing outside `app.prediction` needs to change).

`backend/app/prediction/jobs.py` has already been extended twice (by 2b's plan and that plan's own final-review fix-wave) — its current `run_forecast` computes `current_vol`/`current_differential` once per currency (outside the horizon loop) and applies the interest-rate regression per horizon. This task adds one more per-currency value (`news_shock`) computed the same way, and one more OR-condition in the existing confidence line — nothing else in the function changes.

- [ ] **Step 1: Replace the entire test file with the version below**

`get_latest_news_sentiment` is patched by its string target (`"app.prediction.jobs.get_latest_news_sentiment"`) without being imported into the test file, matching how `get_latest_macro_rate` already is. Every existing `run_forecast` test gets that one extra `patch(..., return_value=None)` — "no sentiment signal today" — which must leave that test's existing assertions completely unchanged; the two `run_backtest_job` tests are untouched since they don't call `run_forecast`. Two new tests are added at the end for the sentiment-driven confidence path. Replace the full contents of `backend/tests/test_jobs.py`:

```python
# backend/tests/test_jobs.py
from unittest.mock import patch

from app.prediction.backtest import summarize
from app.prediction.jobs import run_backtest_job, run_forecast


def test_run_forecast_builds_prediction_rows_from_backtest_stats():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": None,
            "regression_intercept": None,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        count = run_forecast()

    assert count == 4  # one row per horizon (7/30/90/365) for the one non-USD currency
    rows = mock_insert.call_args[0][0]
    assert all(r["base_code"] == "USD" and r["quote_code"] == "EUR" for r in rows)
    assert all(r["confidence"] == "normal" for r in rows)  # 0.01 vol < 0.02 p90
    first = rows[0]
    assert first["predicted_rate"] == 0.91
    assert first["lower_bound"] == 0.91 * (1 + (-0.02))
    assert first["upper_bound"] == 0.91 * (1 + 0.03)


def test_run_forecast_flags_low_confidence_when_volatility_exceeds_p90():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.05
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": None,
            "regression_intercept": None,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    assert all(r["confidence"] == "low" for r in rows)


def test_run_forecast_skips_horizon_with_no_backtest_stats_yet():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        count = run_forecast()

    assert count == 0
    mock_insert.assert_called_once_with([])


def test_run_forecast_applies_regression_when_stored_and_current_differential_known():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": 0.004,
            "regression_intercept": -0.01,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate",
        side_effect=lambda code: 0.06 if code == "EUR" else 0.01,  # differential = 0.05
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    expected_predicted = 0.91 * (1 + (0.004 * 0.05 + -0.01))
    assert rows[0]["predicted_rate"] == expected_predicted
    assert rows[0]["lower_bound"] == expected_predicted * (1 + (-0.02))
    assert rows[0]["upper_bound"] == expected_predicted * (1 + 0.03)


def test_run_forecast_skips_adjustment_when_current_differential_unknown():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": 0.004,
            "regression_intercept": -0.01,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    assert rows[0]["predicted_rate"] == 0.91  # unadjusted -- no current differential


def test_run_backtest_job_summarizes_and_upserts_per_currency_and_horizon():
    fake_results = {
        7: {"errors": [-0.01, 0.0, 0.01], "trailing_vols": [0.01, 0.02, 0.03]},
        30: {"errors": [], "trailing_vols": []},
    }
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.get_macro_rate_series", return_value=[]
    ), patch(
        "app.prediction.jobs.run_backtest", return_value=fake_results
    ), patch("app.prediction.jobs.upsert_backtest_stats") as mock_upsert:
        count = run_backtest_job()

    assert count == 1  # horizon 30 skipped (no samples), only horizon 7 written
    rows = mock_upsert.call_args[0][0]
    assert rows[0]["quote_code"] == "EUR"
    assert rows[0]["horizon_days"] == 7
    assert rows[0]["sample_count"] == 3
    assert rows[0]["regression_slope"] is None
    assert rows[0]["regression_intercept"] is None


def test_run_backtest_job_aligns_and_passes_differentials():
    captured = {}

    def fake_run_backtest(rates, horizons, differentials=None):
        captured["differentials"] = differentials
        return {h: {"errors": [], "trailing_vols": []} for h in horizons}

    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01", "2020-01-02"], [0.9, 0.91]),
    ), patch(
        "app.prediction.jobs.get_macro_rate_series",
        side_effect=lambda code: [("2020-01-01", 0.05)] if code == "EUR" else [("2020-01-01", 0.01)],
    ), patch(
        "app.prediction.jobs.run_backtest", side_effect=fake_run_backtest
    ), patch("app.prediction.jobs.upsert_backtest_stats"):
        run_backtest_job()

    assert captured["differentials"] == [0.04, 0.04]  # 0.05 - 0.01, forward-filled


def test_backtest_and_forecast_regression_contract_are_compatible():
    """Integration check: the dict run_backtest_job would write to
    backtest_stats (built from a REAL summarize() call, not a mock) and
    the dict run_forecast reads back via get_backtest_stats must be the
    same shape, and a real fitted regression must genuinely be picked up
    and applied -- not just individually plausible in each function's
    own isolated unit tests.
    """
    import random

    random.seed(42)
    differentials = [i * 0.2 - 2.0 for i in range(30)]
    errors = [0.004 * d - 0.01 + random.uniform(-0.002, 0.002) for d in differentials]
    samples = {
        "errors": errors,
        "trailing_vols": [0.01] * 30,
        "differentials": differentials,
    }
    summary = summarize(samples)
    assert summary["regression_slope"] is not None  # sanity: fixture actually fits

    stats_dict_shape = {
        "error_lower_pct": summary["error_lower_pct"],
        "error_upper_pct": summary["error_upper_pct"],
        "volatility_p90": summary["volatility_p90"],
        "regression_slope": summary["regression_slope"],
        "regression_intercept": summary["regression_intercept"],
    }

    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats", return_value=stats_dict_shape
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate",
        side_effect=lambda code: 0.06 if code == "EUR" else 0.01,  # differential = 0.05
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    expected_predicted = 0.91 * (
        1 + (summary["regression_slope"] * 0.05 + summary["regression_intercept"])
    )
    assert rows[0]["predicted_rate"] == expected_predicted


def test_run_forecast_skips_adjustment_when_multiplier_is_non_positive():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": -100.0,  # engineered to force a non-positive multiplier
            "regression_intercept": -0.01,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate",
        side_effect=lambda code: 0.06 if code == "EUR" else 0.01,  # differential = 0.05
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    assert rows[0]["predicted_rate"] == 0.91  # unadjusted -- multiplier would've been negative


def test_run_forecast_flags_low_confidence_on_news_shock_even_with_normal_volatility():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": None,
            "regression_intercept": None,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment",
        return_value={"score": -0.85, "summary": "Major shock event."},
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    assert all(r["confidence"] == "low" for r in rows)  # 0.01 vol is normal, but |-0.85| >= 0.7


def test_run_forecast_stays_normal_confidence_for_mild_sentiment():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": None,
            "regression_intercept": None,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment",
        return_value={"score": 0.2, "summary": "Routine coverage."},
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    assert all(r["confidence"] == "normal" for r in rows)  # |0.2| < 0.7, volatility also normal
```

- [ ] **Step 2: Run tests to verify the new/modified ones fail**

Run: `cd backend && python -m pytest tests/test_jobs.py -v`
Expected: the modified existing tests FAIL (extra `patch()` target doesn't exist as an importable attribute yet — `get_latest_news_sentiment` isn't imported into `app.prediction.jobs`, so `patch("app.prediction.jobs.get_latest_news_sentiment", ...)` raises `AttributeError`). The two new tests also FAIL for the same reason.

- [ ] **Step 3: Implement the extension**

In `backend/app/prediction/jobs.py`, add the import:

```python
from app.news.supabase_rest import get_latest_news_sentiment
```

alongside the existing `from app.macro.supabase_rest import get_latest_macro_rate, get_macro_rate_series` line. Then in `run_forecast`, add the sentiment lookup alongside the existing per-currency `current_differential` computation, and extend the confidence line:

```python
        current_vol = realized_volatility(rates, len(rates))

        foreign_rate = get_latest_macro_rate(quote_code)
        current_differential = (
            foreign_rate - usd_rate
            if foreign_rate is not None and usd_rate is not None
            else None
        )

        sentiment = get_latest_news_sentiment(quote_code)
        news_shock = sentiment is not None and abs(sentiment["score"]) >= 0.7
```

and change:

```python
            confidence = "low" if current_vol > stats["volatility_p90"] else "normal"
```

to:

```python
            confidence = (
                "low" if (current_vol > stats["volatility_p90"] or news_shock) else "normal"
            )
```

Update `run_forecast`'s docstring to mention the new condition (one sentence is enough — the existing docstring already documents the regression-adjustment addition from 2b in the same style).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_jobs.py -v`
Expected: PASS, all tests (7 existing + 2 new = 9).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS, every test in the suite (this is the first point where all of Tasks 1-9's changes are exercised together).

- [ ] **Step 6: Commit**

```bash
git add backend/app/prediction/jobs.py backend/tests/test_jobs.py
git commit -m "feat(backend): flag forecast confidence low on a news sentiment shock"
```

---

### Task 10: Live verification

No new GitHub Actions secrets beyond `OPENROUTER_API_KEY` (and optionally `LLM_API_KEY`/`LLM_PROVIDER`, already added per the Prerequisite section) are needed — `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are already configured.

**Be mindful of the unauthenticated GitHub REST API's 60-requests/hour rate limit** when polling workflow status — space out checks (e.g. every 2-3 minutes, not every 20-30 seconds), and if a poll returns a rate-limit error, check `https://api.github.com/rate_limit`'s `X-RateLimit-Reset` header for when it actually resets rather than continuing to retry.

- [ ] **Step 1: Trigger the news sentiment workflow**

On GitHub: repo → Actions → "Score news sentiment" → Run workflow → Run workflow. Wait for a green checkmark.

- [ ] **Step 2: Verify `news_sentiment` populated**

If `mcp__supabase__execute_sql` isn't already loaded: `ToolSearch(query="select:mcp__supabase__execute_sql")`.

`mcp__supabase__execute_sql(query="select count(*) as rows, count(distinct currency_code) as currencies from public.news_sentiment where as_of = current_date")`
Expected: a nonzero row count (some currencies may have been skipped for insufficient GDELT coverage that day — that's expected, not a failure).

`mcp__supabase__execute_sql(query="select currency_code, score, summary, article_count from public.news_sentiment where as_of = current_date order by abs(score) desc limit 5")`
Expected: plausible scores in `[-1, 1]`, non-empty summaries that actually relate to the currency's real current news (spot-check one or two by eye), sane `article_count` values (at least 3, per `MIN_ARTICLES`).

- [ ] **Step 3: Trigger the daily forecast**

On GitHub: repo → Actions → "Generate predictions" → Run workflow → mode = `forecast` → Run workflow. Wait for a green checkmark.

- [ ] **Step 4: Verify the confidence flag reflects sentiment**

`mcp__supabase__execute_sql(query="select p.quote_code, p.horizon_days, p.confidence, n.score as sentiment_score from public.predictions p left join public.news_sentiment n on n.currency_code = p.quote_code and n.as_of = current_date where p.generated_at = (select max(generated_at) from public.predictions) order by abs(coalesce(n.score, 0)) desc limit 10")`

For any row where `abs(sentiment_score) >= 0.7`, confirm `confidence = 'low'`. For rows with a mild or null `sentiment_score`, confirm `confidence` reflects only the pre-existing volatility check (unaffected by this plan). If no currency's live sentiment score happens to reach 0.7 today, that's fine — it means no real shock existed today, not a bug; confirm instead that `predicted_rate`/`lower_bound`/`upper_bound` values across the board are unchanged in shape/sanity from before this plan (proving the "never touches the rate math" claim holds in production, not just in mocked tests).

- [ ] **Step 5: Run the full backend test suite one more time**

Run: `cd backend && python -m pytest -q`
Expected: PASS, every test, no live network or LLM calls in the suite itself.

- [ ] **Step 6: Confirm nothing is left uncommitted**

Run: `git status --short`
Expected: clean.

## Definition of Done

- `supabase/migrations/0006_news_sentiment.sql` applied; `news_sentiment` exists with its RLS policy.
- `OPENROUTER_API_KEY` is set both in `backend/.env` and as a GitHub Actions repo secret; the LLM client falls back to it correctly whenever `LLM_API_KEY`/`LLM_PROVIDER` aren't set.
- A scheduled `news.yml` run populates `news_sentiment` for currencies with adequate GDELT coverage that day; currencies with sparse coverage are skipped, not errored.
- The daily forecast job correctly flags `confidence="low"` for a currency with a real shock-magnitude sentiment score, and leaves every currency's `predicted_rate`/`lower_bound`/`upper_bound` completely unchanged from pre-2c behavior.
- Backend test suite (including all new `news`-package tests and the extended `test_jobs.py` tests) passes with no live network or LLM calls.
- Roadmap doc's 2c entry is marked shipped, with the numeric-adjustment deferral (spec §2) noted explicitly, not silently dropped.
