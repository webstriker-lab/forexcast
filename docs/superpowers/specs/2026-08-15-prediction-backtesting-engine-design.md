# ForexCast — Prediction & Backtesting Engine, Statistical Baseline (Design)

**Status:** Approved for planning
**Date:** 2026-08-15
**Scope:** Sub-project 2a of the roadmap's "Prediction & backtesting engine" item — the statistical baseline model and backtesting harness only. See [Deferred](#deferred-2b--2c) below.

## 1. Goal

Produce real, honestly-uncertain forex rate forecasts — a point estimate plus a confidence band derived from *measured* historical error, not a guessed number — for every USD-quoted currency pair already in `rates_cache`, at 7/30/90/365-day (calendar) horizons, refreshed daily, on entirely free infrastructure.

## 2. Scope

**In scope:**
- One statistical model (exponential smoothing) fit per currency against its USD-pivot rate history.
- A rolling-origin backtesting harness that measures real historical forecast error and turns it into empirical confidence bands.
- Low-confidence/volatile flagging based on current volatility relative to a currency's own historical range.
- Writing to the existing `predictions` table; a new `backtest_stats` table to persist backtest results between runs.
- Two GitHub Actions schedules: daily forecast, weekly backtest.

**Deferred — 2b / 2c:**
The original roadmap item bundled a FRED-based interest-rate regression adjustment and a GDELT+LLM news-sentiment adjustment into this same task. Both are deferred to their own follow-up tasks (2b, 2c — see `docs/superpowers/plans/2026-08-13-forexcast-foundation.md`'s roadmap note) for the same reason GDELT/FRED were originally deferred out of the rates-ingestion pipeline: neither has a real consumer until this baseline model exists to be adjusted. 2c additionally needs at least a narrow LLM-calling capability that doesn't exist yet.

**Deferred — cross-pair predictions:**
Only the 29 USD-quoted pairs get real, independently-backtested predictions in this task. A non-USD pair like EUR→INR is not predicted directly — deriving it by dividing two independent USD-quoted forecasts would produce a defensible point estimate but not a rigorously backtested confidence band (unlike current-rate lookups via `cross_rate()`, which are exact because they're the same real-valued snapshot; two independent forecasts each carry their own separately-modeled error). Broader pair coverage is a future increment, not part of this task.

## 3. Model

**Method:** Holt's exponential smoothing with a damped additive trend, no seasonal component (`statsmodels.tsa.holtwinters.ExponentialSmoothing`, `trend="add"`, `damped_trend=True`, `seasonal=None`).

**Why exponential smoothing over ARIMA:** forex rates are close enough to a random walk (the well-established "Meese-Rogoff" finding) that ARIMA's autoregressive/moving-average terms mostly fit noise on liquid currency pairs, and safely automating ARIMA's per-series order selection across 29 currencies run nightly, unsupervised, is failure-prone. Damped exponential smoothing is closer to "random walk with a fading trend," a more honest match to the data, and more robust when automated. The backtest harness (§5) is deliberately model-agnostic — a candidate is just a function that fits and forecasts — so adding ARIMA or any other candidate later, and letting the backtest itself decide per currency, is a small addition rather than a redesign.

**Why damped trend specifically:** an undamped trend model extrapolated to a 365-day horizon can run away to an implausible number — exactly the "falsely precise" failure mode the Phase 1 design spec warns against. Damping caps how far a detected trend is allowed to compound.

**One fit per currency, not one per (currency, horizon):** `ExponentialSmoothing.fit().forecast(steps)` produces a forecast at any step count from a single fit, so one fit per currency yields all 4 horizons. 29 fits/day, not 116.

## 4. Horizon Definition — Calendar Days, Converted to Trading-Day Steps

`predictions.horizon_days` (7/30/90/365) represents **calendar days** — matching how a user actually thinks about "in 30 days." `rates_cache` only contains trading days (Frankfurter/ECB skip weekends and holidays), so a model fit on the plain ordered sequence of observations and asked to forecast "N steps ahead" is stepping in *trading* days, not calendar days. Converting naively (`steps = horizon_days`) would silently make the "30-day" prediction actually look ~42 calendar days ahead.

**Conversion:** `trading_day_steps = round(horizon_days * 5 / 7)` — e.g. 30 calendar days → 21 trading-day steps, 365 → 261. This conversion is applied identically in both the daily forecast job and the backtest harness; if it drifted between the two, the confidence bands computed by the backtest would no longer describe what the daily job is actually predicting.

## 5. Backtesting — Rolling-Origin, Monthly Re-Origin, Weekly Run

**Method:** for each currency, walk backward through its full rate history, picking an origin point every ~30 days (not every day — see below). At each origin, fit the model on data up to that point only (no look-ahead), forecast forward by each horizon's trading-day step count, and compare the forecast to the actual rate that materialized at that future date. This produces a distribution of real historical forecast errors per (currency, horizon) — on the order of 240+ samples per horizon over 20 years of monthly origins, comfortably enough for a stable empirical quantile estimate.

Two honesty notes on that sample count: it shrinks somewhat for longer horizons, since a 365-day-horizon origin needs a full year of *future* data after it to score against, so origins from the most recent year aren't usable for that horizon yet — with ~27 years of history this still leaves several hundred usable origins even at 365 days, just not quite as many as at 7 days. And the errors from adjacent monthly origins at long horizons overlap in the data they cover, so they're representative historical samples rather than statistically independent ones — still far more grounded than an assumed error distribution, just not a claim of full independence.

**Why monthly re-origin instead of daily:** daily re-origination over ~27 years × 29 currencies × 4 horizons would mean refitting the model at thousands of origins nightly — needless compute for statistics that don't meaningfully shift day to day. Monthly re-origin keeps the sample size large enough for a stable estimate while keeping the job's runtime bounded regardless of how much history accumulates.

**Why the backtest itself runs weekly, not daily:** the backtest computes a *statistical property of the data* (how wrong has this model historically been, at this horizon, for this currency) — a slow-moving quantity that doesn't need daily refreshing. The daily job still recomputes today's actual point forecast every day using the latest rate; it just reads the most recent backtest results (§6) to build that forecast's confidence band, rather than recomputing the whole historical error distribution itself.

**Confidence band:** `lower_bound` / `upper_bound` are the predicted rate adjusted by the **10th and 90th percentile of the currency's historical forecast errors at that horizon** (empirical quantiles from the backtest), not a normal-distribution approximation like ±k×MAE. Forex forecast errors are often fat-tailed, especially at longer horizons, and a normal approximation risks understating real tail risk — empirical quantiles make no assumption about the error distribution's shape, matching the Phase 1 design spec's "measured error, not a guessed number" principle directly.

## 6. Low-Confidence / Volatile Flagging

`predictions.confidence` is `'low'` when the currency's **current realized volatility is unusually high relative to its own historical range** — not a fixed global threshold. Method: compute trailing 30-day realized volatility (standard deviation of daily returns) both currently and at each historical backtest origin, building a per-currency historical distribution of that same rolling volatility measure. If current volatility exceeds roughly the 90th percentile of a currency's own historical volatility distribution, flag `'low'`; otherwise `'normal'`.

This is self-calibrating per currency: a currency that's always more volatile than others (e.g. TRY vs. CHF) isn't flagged constantly just for being itself — only genuine deviation from *its own* norm triggers the flag, matching the spec's "recent volatility is far outside historical norms" language exactly.

## 7. New Schema — `backtest_stats`

Persists the weekly backtest's results so the daily job can build bands without re-running the backtest itself.

```sql
create table public.backtest_stats (
    id bigserial primary key,
    quote_code text not null references public.currencies (code),
    horizon_days integer not null,
    error_lower_pct numeric not null,
    error_upper_pct numeric not null,
    volatility_p90 numeric not null,
    sample_count integer not null,
    computed_at timestamptz not null default now(),
    unique (quote_code, horizon_days)
);
```

Column naming here deliberately mirrors `rates_cache`'s own convention: base is always `'USD'` (the pivot) and doesn't need its own column since it never varies; `quote_code` is the currency actually being predicted (e.g. `'EUR'`), matching `rates_cache.quote_code`'s meaning exactly. Predictions written by this task follow the same convention: `predictions.base_code = 'USD'`, `predictions.quote_code = <currency>` — the same series `rates_cache` already stores for that pair, so the model fits and forecasts the literal values already on hand, no inversion anywhere. RLS enabled on `backtest_stats`, no public read policy — this is internal computation state the frontend never queries directly; only the service role (which bypasses RLS) reads and writes it. Everything the frontend needs is already in `predictions`.

## 8. Components

- `backend/app/prediction/model.py` — model-agnostic fit/forecast interface; the exponential-smoothing implementation.
- `backend/app/prediction/backtest.py` — rolling-origin windowing, empirical error quantile computation, volatility-percentile computation.
- `backend/app/prediction/supabase_rest.py` — reads `rates_cache` rate series per currency; reads/writes `backtest_stats`; writes `predictions`. Mirrors `app.ingestion.supabase_rest`'s pattern (thin `httpx` + service-role key wrapper) but is its own module, since it touches different tables.
- `backend/app/prediction/forecast.py` — daily orchestration: fit today's model per currency, convert horizons, build bands from cached `backtest_stats`, check volatility flag, upsert `predictions`.
- `backend/app/prediction/cli.py` — `python -m app.prediction.cli --mode forecast` (daily) / `--mode backtest` (weekly).
- `.github/workflows/predict.yml` — daily forecast trigger at 18:00 UTC (an hour after the rates-ingestion cron, so same-day rates are available), weekly backtest trigger (Sunday).
- `supabase/migrations/0003_backtest_stats.sql` — the new table from §7.

## 9. Error Handling

Same principle as the ingestion pipeline: a failed job fails loudly (uncaught exception → non-zero exit → red GitHub Actions run), not silently. If a currency has too little history for a meaningful backtest (shouldn't occur given the full 1999+ backfill, but a defensive check is cheap), that currency is skipped for that run with a clear log line rather than crashing the whole batch — matching the ingestion pipeline's "skip what's missing, don't fail the batch" precedent for genuinely expected gaps, while still failing hard on unexpected errors (network, Supabase writes, model-fitting exceptions on data that should be well-formed).

## 10. Testing

- `model.py`: unit tests on small synthetic series verifying fit/forecast shape and that damping actually bounds the trend.
- `backtest.py`: unit tests on synthetic data for the rolling-origin windowing logic (correct origins, no look-ahead), the horizon-to-trading-day-steps conversion (§4), empirical quantile computation, and volatility-percentile computation — all pure functions, fully testable without any network or database access.
- `supabase_rest.py`: mocked-`httpx` tests matching `app.ingestion.supabase_rest`'s existing test conventions.
- `forecast.py` / `cli.py`: orchestration tests with mocked dependencies, same pattern as `app.ingestion.rates`/`cli`.
- No live network or database calls anywhere in the automated suite. Live verification (does a real backtest run against real Supabase data produce sane numbers) happens as a manual step against the live project, same as the ingestion pipeline's Task 8.

## Definition of Done

- `supabase/migrations/0003_backtest_stats.sql` applied; `backtest_stats` table exists with RLS enabled and no public read policy.
- Weekly backtest job runs successfully against live data and populates `backtest_stats` for all 29 USD-quoted currencies × 4 horizons.
- Daily forecast job runs successfully and populates `predictions` for all 29 currencies × 4 horizons, with bands sourced from `backtest_stats` and `confidence` set by the volatility check.
- Backend test suite (including new prediction-engine tests) passes with no live network calls.
- 2b (FRED regression) and 2c (GDELT + LLM sentiment) remain tracked in the foundation plan's roadmap note as explicit follow-ups, not silently dropped.
