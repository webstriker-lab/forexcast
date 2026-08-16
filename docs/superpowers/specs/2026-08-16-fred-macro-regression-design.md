# ForexCast — FRED Interest-Rate-Differential Regression Layer (Design)

**Status:** Approved for planning
**Date:** 2026-08-16
**Scope:** Roadmap item 2b — extends the shipped prediction & backtesting engine (2a) with a regression adjustment driven by FRED interest-rate data. See [Deferred](#deferred) for what's explicitly excluded.

## 1. Goal

2a's baseline forecast (damped exponential smoothing off `rates_cache` alone) treats each currency pair as a pure price series, with no macroeconomic context. Textbook interest-rate parity — and the well-documented ways real forex markets deviate from it — suggests the gap between a currency's short-term interest rate and USD's carries real predictive signal. This task fits that relationship empirically, per currency, from FRED data, and applies it as a correction on top of the existing baseline forecast, without changing anything downstream of `predictions` (recommendations, alerts, and the future dashboard all keep working unmodified).

## 2. Scope

**In scope:**
- Ingesting one FRED interest-rate series per currency (short-term interbank/policy rate), stored in a new `public.macro_rates` table.
- Extending the existing weekly backtest job to fit a per-(currency, horizon) linear regression of forecast error against the interest-rate differential (currency's rate − USD's rate), with a minimum-sample/significance quality gate.
- Extending the existing daily forecast job to apply that regression's adjustment to the baseline point forecast, when a currency/horizon has a fitted regression.
- A new scheduled GitHub Actions workflow for the FRED ingestion.

**Deferred:**
- **Inflation and GDP ingestion.** The roadmap line names these alongside interest rates, but no planned model logic consumes them — this task ingests interest rates only. Inflation/GDP ingestion is deferred to whenever a concrete consumer exists for them (the original Phase 1 spec's news-sentiment layer, 2c, or a future model iteration); revisit then rather than storing unused data now.
- **Surfacing "this forecast was macro-adjusted" to consumers.** `predictions` gains no new column marking whether a row used the regression adjustment. If the dashboard (item 6) wants to show this, it can be inferred from `backtest_stats.regression_slope is not null`, or added then — not needed by any consumer today.
- **Real-time data vintages (ALFRED).** FRED publishes revised series; this task uses the standard (latest-revision) API, which means the weekly backtest fits against data as it looks today, not as it was originally published at each historical date. This is a known simplification — a small look-ahead bias — accepted for a hobby-scale project, not silently assumed away.

## 3. Data Source & Ingestion

**FRED API:** `https://api.stlouisfed.org/fred/series/observations`, free with a self-service API key (`FRED_API_KEY`, new repo secret), rate-limited to 120 requests/minute — well within what ~30 series/run needs, no throttling logic required.

**Series selection:** one short-term interest-rate series per currency, keyed by a hardcoded `currency_code -> series_id` mapping in `backend/app/macro/series_map.py` (e.g. the OECD-sourced `IR3TIB01<country>M156N` family confirmed to exist for at least US/DE/JP/CH/Euro-Area during this design's research — the remaining ~24 currencies' exact series IDs must be individually verified against the live FRED API during implementation, not guessed). Not every currency in our 29-currency universe is expected to have a usable series (several — HKD, SGD, IDR, MYR, PHP, ZAR among them — aren't OECD members); a currency with no confirmed series is simply omitted from the mapping and skipped everywhere downstream, the same way AED was dropped when Frankfurter didn't support it.

**Storage:** new table `public.macro_rates (currency_code, as_of, series_id, rate)`, one row per currency per observation date — see §5. Monthly-granularity series across decades means each currency is only ~300-700 rows; the ingestion job re-fetches and upserts each mapped currency's **full** observation history every run (unlike `rates_cache`'s daily/backfill split, no incremental mode is needed here — the data volume doesn't justify the extra complexity).

**Cadence:** weekly, scheduled ahead of `predict.yml`'s existing Sunday backtest cron (`0 19 * * 0`) so a fresh backtest always sees current macro data. FRED series update roughly monthly, so weekly refresh keeps `macro_rates` current within days of any new print; the daily forecast job (which needs "today's differential") just reads whatever's latest in `macro_rates` — no daily macro fetch needed, since the underlying data itself doesn't change that often.

**Error handling for ingestion (per §8):** FRED unreachable, rate-limited, or any 5xx/timeout is unexpected and fails the job loudly. A specific series_id FRED doesn't recognize (HTTP 400) or returns zero observations for (HTTP 200, empty list) is an expected per-currency gap — logged and skipped, not an error.

## 4. Regression Fitting (extends the weekly backtest job)

`backend/app/prediction/backtest.py`'s `run_backtest` already walks rolling origins across a currency's rate history, spaced `ORIGIN_SPACING` (30) trading days apart after `MIN_HISTORY` (60) days of lead-in, computing each origin's relative forecast error `(actual - predicted) / predicted` per horizon. This task extends it to also collect, at each origin, that origin date's interest-rate differential (currency rate − USD rate, both as-of that origin date) when available:

```python
def run_backtest(
    rates: list[float],
    horizons: list[int],
    differentials: list[float | None] | None = None,
) -> dict[int, dict]:
    ...
```

`differentials` is parallel to `rates` (same length, oldest to newest) — the differential known as of each date, or `None` before FRED coverage begins for that currency. When `differentials` is omitted (or a currency has no mapped FRED series at all), `run_backtest` behaves exactly as it does today — this is a strictly additive extension, not a rewrite, and currencies with no macro coverage take the unchanged 2a code path automatically. When provided, each horizon's results additionally collect `differentials` samples in lock-step with `errors`, restricted to origins where a differential is known.

`summarize()` is extended to fit the regression when differential samples exist:

```python
def summarize(samples: dict) -> dict:
    errors = samples["errors"]
    diffs = samples.get("differentials")
    regression = fit_regression(errors, diffs) if diffs else None
    residuals = (
        [e - (regression["slope"] * d + regression["intercept"]) for e, d in zip(errors, diffs)]
        if regression else errors
    )
    return {
        "error_lower_pct": percentile(sorted(residuals), 10),
        "error_upper_pct": percentile(sorted(residuals), 90),
        "volatility_p90": percentile(sorted(samples["trailing_vols"]), 90),
        "sample_count": len(errors),
        "regression_slope": regression["slope"] if regression else None,
        "regression_intercept": regression["intercept"] if regression else None,
    }
```

`fit_regression(errors, differentials, min_samples=24, p_threshold=0.10) -> dict | None` fits an ordinary least-squares line (`relative_error ~ a + b * differential`, via `scipy.stats.linregress` — add `scipy` explicitly to `requirements.txt`; it's already a transitive `statsmodels` dependency but has not been pinned directly) and returns `{"slope": b, "intercept": a}` only when there are at least `min_samples` paired observations **and** the slope's p-value is below `p_threshold`; otherwise returns `None`, meaning "not enough evidence this currency's rate differential predicts anything — don't adjust it."

**Critically, `error_lower_pct`/`error_upper_pct` are recomputed from the *post-adjustment residuals* when a regression is fit**, not the raw baseline errors — the same rigor as 2a's relative-vs-absolute-error fix. If the confidence band were left keyed to the unadjusted baseline's error distribution while the point forecast itself became more accurate, the band would misrepresent the adjusted model's real historical accuracy (most likely: too wide, since raw baseline error already includes the systematic component the regression now corrects for).

`backend/app/prediction/jobs.py`'s `run_backtest_job` is extended to fetch the currency's aligned differential series (§6) before calling `run_backtest`, and to pass `regression_slope`/`regression_intercept` through to `upsert_backtest_stats`.

## 5. New / Modified Schema

```sql
-- One FRED interest-rate observation per currency per date. Internal
-- computation state only, like backtest_stats -- no consumer outside
-- the prediction pipeline reads this directly.
create table public.macro_rates (
    currency_code text not null references public.currencies (code),
    as_of date not null,
    series_id text not null,
    rate numeric not null,
    primary key (currency_code, as_of)
);

alter table public.macro_rates enable row level security;
-- Deliberately no select policy: only the service role (which bypasses
-- RLS) reads or writes this table, matching backtest_stats' convention.

-- Nullable: NULL means "no regression fit for this currency/horizon --
-- use the unadjusted 2a baseline," which is the default/common case
-- until a currency both has FRED coverage and clears the quality gate.
alter table public.backtest_stats
    add column regression_slope numeric,
    add column regression_intercept numeric;
```

## 6. Applying the Adjustment (extends the daily forecast job)

`backend/app/prediction/jobs.py`'s `run_forecast` computes the baseline point forecast exactly as today (`forecast(rates, steps)`), then, if `get_backtest_stats` returns a non-null `regression_slope` for that currency/horizon, looks up today's current differential (`app.macro.supabase_rest.get_latest_macro_rate(quote_code)` minus the same for `'USD'`, when both exist) and applies:

```python
predicted_rate = baseline_predicted_rate
if stats["regression_slope"] is not None and current_differential is not None:
    predicted_rate *= 1 + (stats["regression_slope"] * current_differential + stats["regression_intercept"])
```

`lower_bound`/`upper_bound` are computed exactly as today (`predicted_rate * (1 + error_lower_pct/upper_pct)`) — no change to that code path, since `error_lower_pct`/`upper_pct` already reflect the right residual distribution per §4 regardless of whether this currency/horizon has a regression. This keeps every downstream table (`predictions`, `recommendations`, `alerts`) completely unaware that this task exists — the adjustment is fully contained inside the prediction package.

**Date alignment (`backend/app/macro/align.py`):** FRED data is monthly; `rates_cache` dates are daily. A pure function `align_as_of(dates: list[str], observations: list[tuple[str, float]]) -> list[float | None]` forward-fills each `observations` value onto every `dates` entry from that observation's date onward (most-recent-value-as-of semantics), returning `None` for any `dates` entry before the first observation. Used both to build the `differentials` array `run_backtest_job` passes into `run_backtest`, and — trivially, as a single-element case — to resolve "today's" differential in `run_forecast`.

## 7. Components

- `backend/app/macro/fred_client.py` — I/O: `fetch_observations(series_id: str) -> list[tuple[str, float]] | None` (thin `httpx` wrapper around FRED's observations endpoint; returns `None` for an unrecognized series_id or an empty result, raises for network/5xx/timeout errors).
- `backend/app/macro/series_map.py` — the `currency_code -> series_id` mapping constant (§3).
- `backend/app/macro/supabase_rest.py` — I/O: `upsert_macro_rates(rows) -> None`, `get_macro_rate_series(currency_code) -> list[tuple[str, float]]` (paginated like `app.prediction.supabase_rest.get_rate_series`), `get_latest_macro_rate(currency_code) -> float | None`. Mirrors the established `_headers()`/`BATCH_SIZE`/`PAGE_SIZE` conventions.
- `backend/app/macro/align.py` — pure computation: `align_as_of` (§6).
- `backend/app/macro/jobs.py` — orchestration: `run_macro_ingestion() -> int` (fetches + upserts every mapped currency's full history).
- `backend/app/macro/cli.py` — `python -m app.macro.cli` (single mode, no flags needed — this package only has one job).
- `.github/workflows/macro.yml` — weekly, scheduled ahead of `predict.yml`'s Sunday backtest.
- `backend/app/prediction/backtest.py` — modified: `run_backtest`/`summarize` extended per §4.
- `backend/app/prediction/jobs.py` — modified: `run_backtest_job`/`run_forecast` extended per §4/§6.
- `backend/app/prediction/supabase_rest.py` — modified: `get_backtest_stats`/`upsert_backtest_stats` include the two new columns.
- `backend/app/config.py` — modified: add `fred_api_key: str`.
- `supabase/migrations/0005_macro_rates.sql` — the schema from §5.

## 8. Error Handling

Same "fail loudly, skip only genuinely expected gaps" principle as every prior task:
- FRED unreachable, rate-limited, or a non-400 error during the scheduled ingestion job: fails loudly.
- A currency's series_id unrecognized by FRED, or returning zero observations: expected, logged, skipped — that currency's `macro_rates` simply stays empty, and every downstream step (differential alignment, regression fitting, adjustment application) already treats "no macro data" as "use the unadjusted baseline," not an error.
- A currency/horizon whose regression doesn't clear the `min_samples`/`p_threshold` gate: expected, not logged as a warning (this will be the common case for many currencies, especially early on) — `regression_slope`/`regression_intercept` simply stay `NULL`.

## 9. Testing

- `align.py`: pure-function unit tests for `align_as_of` — forward-fill correctness, `None` before first observation, exact-date matches, gaps.
- `backtest.py`: extend existing tests — `run_backtest` with/without `differentials` (confirming the no-`differentials` path is byte-for-byte identical to pre-2b behavior), `fit_regression` with synthetic data with a known true slope (assert recovered slope is close), and with pure-noise synthetic data (assert `None` is returned — the quality gate rejects it), `summarize` recomputing bounds from post-adjustment residuals when a regression is fit.
- `fred_client.py`: mocked-`httpx` tests — a valid series, an unrecognized series_id (400), an empty-observations response (200), a network/5xx error (propagates).
- `macro/supabase_rest.py`: mocked-`httpx` tests matching the established convention.
- `macro/jobs.py`/`cli.py`: orchestration tests with mocked dependencies.
- `prediction/jobs.py`: extended tests confirming a currency with a stored regression gets the adjusted `predicted_rate`, and a currency without one (either no macro coverage or gate not cleared) gets exactly the same baseline output as before this task.
- No live network or database calls in the automated suite. Live verification (real FRED data produces sane differentials, a real backtest run fits at least one currency's regression, a real forecast run shows an adjusted vs. unadjusted currency both producing sane numbers) happens as a manual step against the live project, same pattern as the two prior plans.

## Definition of Done

- `supabase/migrations/0005_macro_rates.sql` applied; `macro_rates` exists with its RLS policy, `backtest_stats` has the two new nullable columns.
- A scheduled `macro.yml` run populates `macro_rates` for every currency with a confirmed FRED series.
- The weekly backtest job runs against live data for every currency with FRED coverage and correctly leaves `regression_slope`/`regression_intercept` `NULL` wherever the quality gate isn't cleared — live verification confirms this logic runs end-to-end, not that any particular currency's differential turns out to be statistically significant (that's a property of the real data, not something this task can guarantee). If at least one currency does clear the gate on the live data available at verification time, additionally confirm the daily forecast job produces a correctly adjusted `predicted_rate` for it; if none do, confirm instead that a currency's `predicted_rate` is provably unchanged from what 2a alone would have produced (i.e. the fallback path is exercised and correct).
- The daily forecast job's output for a currency without a fitted regression (no coverage, or gate not cleared) is unchanged from 2a's behavior.
- Backend test suite (including new macro-package and extended prediction tests) passes with no live network calls.
- Roadmap doc's 2b entry is marked shipped, with inflation/GDP ingestion explicitly still noted as deferred (not silently dropped).
