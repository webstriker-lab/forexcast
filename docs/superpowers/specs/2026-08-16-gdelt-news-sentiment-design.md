# ForexCast — GDELT + LLM News-Sentiment Layer (Design)

**Status:** Approved for planning
**Date:** 2026-08-16
**Scope:** Roadmap item 2c — extends the shipped prediction engine (2a) and interest-rate regression layer (2b) with a daily news-sentiment signal. See [Deferred](#deferred) for what's explicitly excluded.

## 1. Goal

Turn GDELT's global news coverage into a daily per-currency sentiment signal via an LLM call, and use it to flag currencies whose forecast shouldn't be trusted blindly right now — a real news shock (sanctions, a coup, a market panic) should push that currency's confidence to `volatile`, the same way 2a's existing volatility-based flag already does. This is deliberately **not** a numeric adjustment to `predicted_rate`: unlike 2b's interest-rate differential, a sentiment score can't be honestly backtested (see §2), so this increment ships only what can be validated — the LLM correctly recognizing "this is significant, negative/positive news," not "this is worth exactly X% on the rate."

## 2. Why This Differs From 2b's Shape

2b's regression was fitted against decades of clean, free, bulk-fetchable FRED data — hundreds of historical samples per currency, cheap to backtest. GDELT's practical query API is oriented around recent news search (its DOC 2.0 API's typical window is recent-to-live, not an efficient bulk historical archive), and even where historical articles exist, scoring them requires an LLM call *per data point* — fitting a real regression would mean thousands of paid LLM calls just to validate one relationship. That's not a "narrow LLM-calling slice" (the roadmap's own framing for this item); it's a research budget this project doesn't have.

So sentiment ships as a **qualitative confidence flag** this round: reliable, honestly-scoped, and it composes cleanly with 2a's existing `confidence` enum rather than inventing new prediction-table semantics. A future increment can revisit a numeric adjustment once enough live `news_sentiment` history has accumulated to actually check whether score sign/magnitude correlates with subsequent price moves — that validation is impossible before real data exists, so it's explicitly deferred, not designed around a guess.

## 3. Data Flow

Daily job, one pass over the 29 non-USD currencies (mirrors 2a/2b's `_predictable_currencies()`):

1. **Retrieval.** Query GDELT's DOC 2.0 API (`https://api.gdeltproject.org/api/v2/doc/doc?query=...&mode=artlist&format=json`, free, no key). GDELT's `query` parameter is a single search string combining a `theme:` filter (GDELT's own documented `ECON_*` taxonomy — `ECON_CURRENCY`, `ECON_CENTRALBANK`, `ECON_INTERESTRATES`, `ECON_INFLATION`, broadly, not narrowed further) with a plain keyword for that currency's country/region's own proper name (e.g. `theme:ECON_CURRENCY Turkey`, or `theme:ECON_CURRENCY Eurozone` for EUR — a single objective fact, not an invented phrase list), restricted to the last ~48 hours (GDELT's `date:` range syntax), capped at the top ~30 results by relevance/recency (`maxrecords`). This keeps behavior identical regardless of which LLM provider ends up handling the request (§4) — the retrieval step is provider-independent, and 30 headlines fits comfortably in even a modest free-tier context window, so a bigger configured model gains no different behavior from this step (more raw GDELT volume is mostly duplicate wire coverage of the same story, not more signal, at typical daily volumes for one country's economic news).
2. **Quality gate.** Fewer than 3 articles found → skip this currency for today (expected gap, not an error — same as an early currency with no `backtest_stats` yet).
3. **Scoring.** Send the retrieved headlines (title + short snippet each, not full article text) to the configured LLM (§4) in one call, with an explicit instruction to judge which headlines are genuinely relevant to that currency's economic outlook and score sentiment only from those — the LLM does the relevance judgment, not a keyword pre-filter. Requested response: strict JSON, `{"score": <float, -1..1>, "summary": "<one/two sentences>"}`.
4. **Storage.** Upsert one row to `news_sentiment` (§6) per currency per day.

## 4. LLM Provider (configurable, system-level — not item 4's future per-user adapter)

This is a backend batch job with no per-user context, so it needs its own system-level key story, distinct from the original spec's §6 user-configured chat-agent keys (item 4, not built yet). Three new optional `Settings` fields (all default `""` — see §8's note on why none of them are required-with-no-default):

- `llm_api_key` / `llm_provider` — set together to force a specific provider. `llm_provider` is one of `deepseek`, `groq`, `gemini`, `openai`.
- `openrouter_api_key` — the guaranteed fallback, used automatically whenever `llm_api_key` is unset, via a free-tier (`:free`-suffixed) OpenRouter model.

All four candidate providers expose an OpenAI-compatible `chat/completions` endpoint (confirmed during this design's research — DeepSeek at `https://api.deepseek.com/v1`, Gemini at `https://generativelanguage.googleapis.com/v1beta/openai/`, Groq at `https://api.groq.com/openai/v1`, OpenRouter at `https://openrouter.ai/api/v1`), so one shared client function handles the actual HTTP call for all of them — provider choice only changes the base URL, key, and model name, never the prompt or the expected response shape. If `llm_api_key` is configured but that call fails (auth, rate-limit, 5xx), it fails loudly rather than silently falling back to OpenRouter — a silent fallback would mask a real problem with the user's own configured key without them knowing their preferred provider isn't actually being used.

Default model names per provider (`deepseek-chat`, `llama-3.3-70b-versatile`, `gemini-2.0-flash`, `gpt-4o-mini`, and a specific OpenRouter `:free` model) are provisional — model catalogs and IDs shift over time, so the implementation plan verifies each one against a live test call before finalizing, the same "verify, don't guess" discipline 2b applied to FRED series IDs.

## 5. Confidence Integration

`backend/app/prediction/jobs.py`'s `run_forecast` already computes `confidence = "low" if current_vol > stats["volatility_p90"] else "normal"`. Extended to:

```python
sentiment = get_latest_news_sentiment(quote_code)
news_shock = sentiment is not None and abs(sentiment["score"]) >= 0.7
confidence = "low" if (current_vol > stats["volatility_p90"] or news_shock) else "normal"
```

No change to `predicted_rate`, `lower_bound`, or `upper_bound` math anywhere — this is purely an additional way to reach the same existing `"low"` state 2a already has. `0.7` (on the `-1..1` scale) is a deliberately conservative "this is a real shock, not routine coverage" threshold — a currency showing up in ordinary daily economic news shouldn't flip to volatile; something genuinely notable should.

## 6. New Schema

```sql
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
-- convention. A future dashboard wanting to show `summary` as an
-- explanation can add a read policy then -- no current consumer needs it.
```

Stored as a full daily history (not overwritten in place beyond the upsert's own day) so a future increment can walk back through real `news_sentiment` rows against what `rates_cache`/`predictions` actually did next, to honestly evaluate whether a numeric adjustment would ever have been justified — see §2.

## 7. Components

- `backend/app/news/gdelt_client.py` — I/O: `fetch_articles(country_query: str) -> list[dict]` (thin `httpx` wrapper around GDELT's DOC 2.0 API, theme + keyword filtered per §3; returns `[]` for zero results, no error — GDELT returning nothing for a query is a normal, expected outcome, not a failure).
- `backend/app/news/country_map.py` — the `currency_code -> country/region proper name` mapping constant (drafted directly, not live-verified against an API the way 2b's FRED series IDs were, since a currency with genuinely sparse GDELT coverage just produces a low article count and a normal skip — there's no "wrong series ID" failure mode here to guard against).
- `backend/app/news/llm_client.py` — I/O: `score_sentiment(articles: list[dict]) -> dict | None` (the provider-selection logic from §4, the prompt, and defensive JSON parsing — including stripping markdown code fences, a common LLM response quirk — returning `None` for a response that doesn't parse as the expected shape, rather than raising).
- `backend/app/news/supabase_rest.py` — I/O: `upsert_news_sentiment(rows) -> None`, `get_latest_news_sentiment(currency_code) -> dict | None`. Mirrors the established `_headers()`/upsert conventions from the sibling `supabase_rest.py` modules.
- `backend/app/news/jobs.py` — orchestration: `run_news_sentiment() -> int`.
- `backend/app/news/cli.py` — `python -m app.news.cli` (single mode, no flags).
- `.github/workflows/news.yml` — daily, scheduled ahead of `predict.yml`'s daily forecast cron (18:00 UTC).
- `backend/app/prediction/jobs.py` — modified: `run_forecast` extended per §5.
- `backend/app/config.py` — modified: add `llm_api_key`, `llm_provider`, `openrouter_api_key` (all optional, default `""`).
- `supabase/migrations/0006_news_sentiment.sql` — the schema from §6.

## 8. Error Handling

Same "fail loudly, skip only genuinely expected gaps" principle as every prior task, plus one hard-won lesson from 2b's final review carried forward explicitly: **no new `Settings` field is required-with-no-default.** 2b shipped a `fred_api_key: str` with no default that broke the live Render API and three unrelated scheduled workflows on merge, because every entrypoint constructs `Settings()` and none of the unrelated ones had a reason to supply that value. All three new fields here default to `""`; the "is any LLM path actually configured" check happens inside `llm_client.py` at call-time (raising a clear, scoped error only when this job actually runs and finds neither `llm_api_key` nor `openrouter_api_key` set), not at `Settings` construction.

- GDELT unreachable, rate-limited, or any 5xx/timeout during the scheduled job: fails loudly.
- Zero or GDELT returning a normal empty/small result for a currency: expected, logged, skipped.
- The configured LLM provider unreachable, rate-limited, or returning a real API error (auth failure, 5xx, timeout): fails loudly — this is a real infrastructure problem, not a per-currency content issue.
- The LLM returning a response that doesn't parse into the expected `{"score", "summary"}` shape for one currency: expected-but-unwanted, logged, that currency is skipped for the day — not aborting the whole run, matching the recommendation-engine plan's per-alert isolation fix (one bad completion shouldn't starve the other 28 currencies).
- Neither `llm_api_key` nor `openrouter_api_key` configured when the job actually runs: fails loudly with a clear message — this is a genuine setup gap, not a per-currency content issue.

## 9. Testing

- `gdelt_client.py`: mocked-`httpx` tests — a normal result set, an empty result set, a network/5xx error propagating.
- `country_map.py`: a lightweight sanity test (nonempty, string keys/values, USD present) — mirrors 2b's `series_map.py` test shape, no live verification needed per §7.
- `llm_client.py`: mocked-`httpx` tests per provider-selection branch (forced provider via `llm_api_key`/`llm_provider`, fallback to OpenRouter when unset, the "neither configured" error case), plus response-parsing tests (clean JSON, JSON wrapped in markdown fences, genuinely malformed content returning `None`).
- `news/supabase_rest.py`: mocked-`httpx` tests matching the established convention.
- `news/jobs.py`/`cli.py`: orchestration tests with mocked dependencies, including the "fewer than 3 articles, skip" and "malformed LLM response, skip and continue" paths.
- `prediction/jobs.py`: extended tests confirming a currency with a stored high-magnitude sentiment score gets `confidence="low"` even when volatility alone wouldn't have triggered it, and that a currency with no sentiment row (or a normal-magnitude score) is unaffected — output identical to pre-2c behavior.
- No live network or LLM calls in the automated suite. Live verification (a real GDELT query returns real articles, a real LLM call returns a sane score/summary, the daily forecast correctly flags a currency when a real shock-magnitude score is present) happens as a manual step against the live project, same pattern as 2b.

## Definition of Done

- `supabase/migrations/0006_news_sentiment.sql` applied; `news_sentiment` exists with its RLS policy.
- A scheduled `news.yml` run populates `news_sentiment` for currencies with adequate GDELT coverage that day; currencies with sparse coverage are skipped, not errored.
- The configured LLM path (forced provider, or the OpenRouter fallback) produces a real score/summary for at least one currency during live verification, and provider selection is confirmed to follow the priority rule from §4.
- The daily forecast job correctly flags `confidence="low"` for a currency with a shock-magnitude sentiment score, and leaves every other currency's output unchanged from pre-2c behavior.
- Backend test suite (including new `news`-package tests and the extended `prediction/jobs.py` tests) passes with no live network or LLM calls.
- Roadmap doc's 2c entry is marked shipped, with the numeric-adjustment deferral (§2) noted explicitly, not silently dropped.
