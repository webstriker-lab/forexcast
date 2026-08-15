# Prediction & Backtesting Engine (Statistical Baseline) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce real, honestly-uncertain forex forecasts (point estimate + confidence band derived from measured backtest error, not a guessed number) for all 29 USD-quoted currencies at 7/30/90/365-day horizons, refreshed daily, on free infrastructure.

**Architecture:** A new `backend/app/prediction/` package: a model-agnostic exponential-smoothing forecaster, a rolling-origin backtest harness that turns historical forecast errors into empirical confidence bands and a per-currency volatility threshold, a Supabase I/O layer, and daily/weekly orchestration wired to a new GitHub Actions workflow. All code and math verified against real execution (real `statsmodels` calls, real windowing arithmetic) while writing this plan — the exact numbers below are not estimates.

**Tech Stack:** Same backend (Python 3.12, `httpx`, pytest) plus `statsmodels==0.14.6` (new dependency — pulls in `pandas`/`numpy` transitively; neither is imported directly by this plan's code, so neither is added to `requirements.txt` separately).

**Spec:** `docs/superpowers/specs/2026-08-15-prediction-backtesting-engine-design.md`

## Global Constraints

- Every code task starts with a failing test before implementation (TDD).
- No live network calls in the automated test suite — all `httpx` calls are mocked. Live verification against the real Supabase project happens only in Task 9's manual steps.
- Scope is the 29 USD-quoted currencies only — no cross-pair predictions in this plan (see spec §2).
- `horizon_days` (7/30/90/365) are calendar days; forecasting/backtesting internally steps in trading days via `round(horizon_days * 5/7)`, applied identically everywhere a horizon becomes a step count.
- Confidence bands are empirical 10th/90th percentile of backtest forecast errors, never a normal/MAE approximation.
- `confidence` is `'low'` when a currency's current 30-day realized volatility exceeds the 90th percentile of *that currency's own* historical rolling volatility — never a fixed global threshold.
- `backtest_stats` has RLS enabled with no public read policy — internal state, service-role access only.
- GitHub Actions secrets `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are already configured on this repo (reused from the ingestion pipeline) — no new secrets needed.

---

### Task 1: `backtest_stats` migration

**Files:**
- Create: `supabase/migrations/0003_backtest_stats.sql`

**Interfaces:**
- Produces: `public.backtest_stats` table — consumed by Task 5's `get_backtest_stats`/`upsert_backtest_stats`.

- [ ] **Step 1: Write `supabase/migrations/0003_backtest_stats.sql`**

```sql
-- Backtest results per (currency, horizon), refreshed weekly. Internal
-- computation state only -- the frontend never queries this directly,
-- everything it needs is already in public.predictions.
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

alter table public.backtest_stats enable row level security;
-- Deliberately no select policy: only the service role (which bypasses
-- RLS) reads or writes this table.
```

- [ ] **Step 2: Apply the migration to the live Supabase project**

If `mcp__supabase__apply_migration` and `mcp__supabase__execute_sql` aren't already loaded: `ToolSearch(query="select:mcp__supabase__apply_migration,mcp__supabase__execute_sql")`.

`mcp__supabase__apply_migration(name="0003_backtest_stats", query=<the SQL from Step 1>)`
Expected: `{"success": true}`.

- [ ] **Step 3: Verify**

`mcp__supabase__execute_sql(query="select count(*) from public.backtest_stats")`
Expected: `0` (empty table exists).

`mcp__supabase__execute_sql(query="select relrowsecurity from pg_class where relname = 'backtest_stats'")`
Expected: `true`.

`mcp__supabase__execute_sql(query="select count(*) from pg_policies where tablename = 'backtest_stats'")`
Expected: `0` (no policies — confirms no public access exists).

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/0003_backtest_stats.sql
git commit -m "feat(db): add backtest_stats table for the prediction engine"
```

---

### Task 2: Exponential-smoothing model wrapper

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/prediction/__init__.py` (empty)
- Create: `backend/app/prediction/model.py`
- Test: `backend/tests/test_prediction_model.py`

**Interfaces:**
- Produces: `forecast(values: list[float], steps: int) -> float` in `app.prediction.model` — consumed by Task 4 (`backtest.py`) and Task 6 (`jobs.py`).

- [ ] **Step 1: Add the new dependency**

Add this line to `backend/requirements.txt`:

```
statsmodels==0.14.6
```

- [ ] **Step 2: Install it**

Run: `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`
Expected: installs without errors (pulls in `pandas`/`numpy`/`patsy` as transitive dependencies of `statsmodels` — none of these are imported directly by this plan's code).

- [ ] **Step 3: Create the empty package marker**

Create `backend/app/prediction/__init__.py` as an empty file.

- [ ] **Step 4: Write the failing test**

`backend/tests/test_prediction_model.py`:

```python
import pytest

from app.prediction.model import forecast


def test_forecast_returns_a_float_for_a_trending_series():
    values = [float(i) for i in range(1, 101)]  # steadily rising 1..100
    result = forecast(values, steps=5)
    assert isinstance(result, float)
    assert result > values[-1]


def test_forecast_flat_series_stays_near_flat():
    values = [100.0] * 50
    result = forecast(values, steps=10)
    assert result == pytest.approx(100.0, abs=0.5)


def test_damped_trend_does_not_extrapolate_linearly_forever():
    # A rising series' 50-step-ahead forecast should grow by less than a
    # *linear* (undamped) extrapolation of the same per-step slope would --
    # damping caps how far a detected trend is allowed to compound. This is
    # exactly the "falsely precise" failure mode the product spec warns
    # against at long horizons.
    values = [float(i) for i in range(1, 101)]
    slope = values[-1] - values[-2]
    forecast_50 = forecast(values, steps=50)
    undamped_linear_50 = values[-1] + slope * 50
    assert forecast_50 < undamped_linear_50
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `pytest backend/tests/test_prediction_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.prediction.model'`.

- [ ] **Step 6: Implement `backend/app/prediction/model.py`**

```python
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def forecast(values: list[float], steps: int) -> float:
    """Fits a damped additive-trend exponential smoothing model on `values`
    (ordered oldest to newest, no seasonality assumed) and returns the
    point forecast `steps` steps ahead.

    This is the sole model candidate for now. The backtest harness
    (app.prediction.backtest) and the daily job (app.prediction.jobs) both
    call this function by name rather than embedding model logic
    themselves, so adding a second candidate (e.g. ARIMA) later, and
    letting the backtest decide which wins per currency, means adding a
    function here -- not redesigning either caller.
    """
    model = ExponentialSmoothing(
        values,
        trend="add",
        damped_trend=True,
        seasonal=None,
        initialization_method="estimated",
    )
    fitted = model.fit()
    forecasts = fitted.forecast(steps)
    return float(forecasts[-1])
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `pytest backend/tests/test_prediction_model.py -v`
Expected: PASS (3 tests), pristine output (no warnings — verified while writing this plan: `ExponentialSmoothing` with `initialization_method="estimated"` produces no warnings on rising, flat, or mildly-trending series of the sizes used here and in Task 4's backtest).

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/app/prediction/__init__.py backend/app/prediction/model.py backend/tests/test_prediction_model.py
git commit -m "feat(backend): add exponential-smoothing model wrapper"
```

---

### Task 3: Horizon conversion and statistics utilities

**Files:**
- Create: `backend/app/prediction/horizons.py`
- Create: `backend/app/prediction/stats.py`
- Test: `backend/tests/test_horizons.py`
- Test: `backend/tests/test_prediction_stats.py`

**Interfaces:**
- Produces: `trading_day_steps(horizon_days: int) -> int` in `app.prediction.horizons`. `percentile(sorted_values: list[float], pct: float) -> float` and `realized_volatility(rates: list[float], end_index: int, window: int = 30) -> float` in `app.prediction.stats`. All three consumed by Task 4 (`backtest.py`); `realized_volatility` also consumed by Task 6 (`jobs.py`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_horizons.py`:

```python
from app.prediction.horizons import trading_day_steps


def test_trading_day_steps_for_each_product_horizon():
    # Verified by hand and by running the exact formula: round(days * 5/7).
    assert trading_day_steps(7) == 5
    assert trading_day_steps(30) == 21
    assert trading_day_steps(90) == 64
    assert trading_day_steps(365) == 261
```

`backend/tests/test_prediction_stats.py`:

```python
import pytest

from app.prediction.stats import percentile, realized_volatility


def test_percentile_linear_interpolation():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(values, 0) == 1.0
    assert percentile(values, 100) == 5.0
    assert percentile(values, 50) == 3.0


def test_percentile_raises_on_empty_list():
    with pytest.raises(ValueError):
        percentile([], 50)


def test_realized_volatility_zero_for_constant_series():
    rates = [100.0] * 40
    assert realized_volatility(rates, 40) == 0.0


def test_realized_volatility_positive_for_varying_series():
    rates = [100.0, 101.0, 99.0, 102.0, 98.0] * 10
    assert realized_volatility(rates, len(rates)) > 0.0


def test_realized_volatility_uses_only_trailing_window():
    # Wild values before the trailing window, flat values inside it --
    # volatility must reflect only the flat trailing window.
    rates = [1000.0, 1.0, 1000.0, 1.0] + [100.0] * 30
    result = realized_volatility(rates, len(rates), window=30)
    assert result == 0.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest backend/tests/test_horizons.py backend/tests/test_prediction_stats.py -v`
Expected: FAIL with `ModuleNotFoundError` for both `app.prediction.horizons` and `app.prediction.stats`.

- [ ] **Step 3: Implement `backend/app/prediction/horizons.py`**

```python
def trading_day_steps(horizon_days: int) -> int:
    """Converts a calendar-day horizon into the trading-day step count to
    actually forecast, since rates_cache only contains trading days
    (weekends and ECB holidays are absent). Must be used identically
    wherever a horizon becomes a forecast step count -- app.prediction
    .backtest and app.prediction.jobs both import this rather than
    redefining the conversion, or the backtest's confidence bands would
    stop describing what's actually being predicted.
    """
    return round(horizon_days * 5 / 7)
```

- [ ] **Step 4: Implement `backend/app/prediction/stats.py`**

```python
def percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile of an already-sorted list (the
    common "linear" method, matching e.g. numpy's default). `pct` is 0-100.
    """
    if not sorted_values:
        raise ValueError("cannot compute a percentile of an empty sample")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (pct / 100)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    fraction = rank - lower_index
    return (
        sorted_values[lower_index]
        + (sorted_values[upper_index] - sorted_values[lower_index]) * fraction
    )


def realized_volatility(rates: list[float], end_index: int, window: int = 30) -> float:
    """Standard deviation of daily returns over the `window` trading days
    ending just before `end_index` (rates[end_index] itself is excluded,
    matching Python slicing). Used both historically in the backtest
    (passing the origin's index, so only data known as of that origin is
    used -- no look-ahead) and for today's live volatility check (passing
    len(rates), so the most recent `window` days are used).
    """
    start = max(0, end_index - window)
    segment = rates[start:end_index]
    if len(segment) < 2:
        return 0.0
    returns = [
        (segment[i] - segment[i - 1]) / segment[i - 1] for i in range(1, len(segment))
    ]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return variance**0.5
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest backend/tests/test_horizons.py backend/tests/test_prediction_stats.py -v`
Expected: PASS (6 tests total).

- [ ] **Step 6: Commit**

```bash
git add backend/app/prediction/horizons.py backend/app/prediction/stats.py backend/tests/test_horizons.py backend/tests/test_prediction_stats.py
git commit -m "feat(backend): add horizon conversion and backtest statistics utilities"
```

---

### Task 4: Rolling-origin backtest harness

**Files:**
- Create: `backend/app/prediction/backtest.py`
- Test: `backend/tests/test_backtest.py`

**Interfaces:**
- Consumes: `forecast(values, steps)` from `app.prediction.model` (Task 2); `trading_day_steps(horizon_days)` from `app.prediction.horizons`, `percentile(sorted_values, pct)` and `realized_volatility(rates, end_index, window)` from `app.prediction.stats` (Task 3).
- Produces: `run_backtest(rates: list[float], horizons: list[int]) -> dict[int, dict]` (returns `{horizon_days: {"errors": [...], "trailing_vols": [...]}}`) and `summarize(samples: dict) -> dict` (returns `{"error_lower_pct": float, "error_upper_pct": float, "volatility_p90": float, "sample_count": int}`) in `app.prediction.backtest`. Both consumed by Task 6 (`jobs.py`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_backtest.py`:

```python
from unittest.mock import patch

from app.prediction.backtest import run_backtest, summarize


def test_run_backtest_produces_fewer_samples_for_longer_horizons():
    # 500 trading days of mildly-trending synthetic data. Verified by hand
    # and by running this exact scenario: with MIN_HISTORY=60 and
    # ORIGIN_SPACING=30, there are 15 origins usable for the 7-day horizon
    # (steps=5) and 6 for the 365-day horizon (steps=261), since a 365-day
    # origin needs a lot more trailing future data to score against.
    rates = [100.0 + 0.01 * i for i in range(500)]
    results = run_backtest(rates, horizons=[7, 365])
    assert len(results[7]["errors"]) == 15
    assert len(results[365]["errors"]) == 6


def test_run_backtest_fits_only_on_data_up_to_each_origin():
    # No-look-ahead check: capture exactly what `history` each origin
    # passes to forecast(), and confirm it's precisely rates[:origin+1] --
    # never anything from beyond that origin.
    rates = [100.0 + i for i in range(150)]
    captured_histories = []

    def fake_forecast(history, steps):
        captured_histories.append(list(history))
        return history[-1]

    with patch("app.prediction.backtest.forecast", side_effect=fake_forecast):
        run_backtest(rates, horizons=[7])

    expected_origins = [60, 90, 120]  # MIN_HISTORY=60, ORIGIN_SPACING=30, n=150
    assert len(captured_histories) == len(expected_origins)
    for origin, history in zip(expected_origins, captured_histories):
        assert history == rates[: origin + 1]


def test_summarize_computes_percentiles_and_sample_count():
    samples = {
        "errors": [-2.0, -1.0, 0.0, 1.0, 2.0],
        "trailing_vols": [0.01, 0.02, 0.03, 0.04, 0.05],
    }
    result = summarize(samples)
    assert result["sample_count"] == 5
    assert result["error_lower_pct"] < 0
    assert result["error_upper_pct"] > 0
    assert result["volatility_p90"] > 0.04
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest backend/tests/test_backtest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.prediction.backtest'`.

- [ ] **Step 3: Implement `backend/app/prediction/backtest.py`**

```python
from app.prediction.horizons import trading_day_steps
from app.prediction.model import forecast
from app.prediction.stats import percentile, realized_volatility

ORIGIN_SPACING = 30  # trading days between backtest origins
MIN_HISTORY = 60  # minimum trading days of lead-in before the first origin


def run_backtest(rates: list[float], horizons: list[int]) -> dict[int, dict]:
    """Rolling-origin backtest for one currency's USD-pivot rate series
    (`rates`, ordered oldest to newest). For each horizon, returns the raw
    forecast-error and trailing-volatility samples collected across every
    usable origin -- summarize() turns these into the stats actually
    stored in backtest_stats.

    Origins are spaced ORIGIN_SPACING trading days apart, starting after
    MIN_HISTORY days of lead-in so every fit has a reasonable amount of
    data. An origin only contributes a sample for a given horizon if
    enough future data exists to know the real outcome -- this is why
    longer horizons end up with fewer usable samples than shorter ones
    (see design spec Sec 5).
    """
    n = len(rates)
    results: dict[int, dict] = {h: {"errors": [], "trailing_vols": []} for h in horizons}

    for origin in range(MIN_HISTORY, n, ORIGIN_SPACING):
        history = rates[: origin + 1]
        trailing_vol = realized_volatility(rates, origin + 1)
        for horizon_days in horizons:
            steps = trading_day_steps(horizon_days)
            target_index = origin + steps
            if target_index >= n:
                continue
            predicted = forecast(history, steps)
            actual = rates[target_index]
            results[horizon_days]["errors"].append(actual - predicted)
            results[horizon_days]["trailing_vols"].append(trailing_vol)

    return results


def summarize(samples: dict) -> dict:
    """Turns one horizon's raw backtest samples into the stats stored in
    backtest_stats: empirical 10th/90th percentile forecast error (added
    to a fresh point forecast to build lower_bound/upper_bound), and the
    90th percentile of historically observed trailing volatility (the
    threshold today's live volatility is compared against for the
    confidence flag).
    """
    errors = sorted(samples["errors"])
    vols = sorted(samples["trailing_vols"])
    return {
        "error_lower_pct": percentile(errors, 10),
        "error_upper_pct": percentile(errors, 90),
        "volatility_p90": percentile(vols, 90),
        "sample_count": len(errors),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest backend/tests/test_backtest.py -v`
Expected: PASS (3 tests). This exact scenario (500-point series, `[7, 365]` horizons) was run for real while writing this plan and produced exactly 15 and 6 samples respectively — if your run produces different counts, something in the windowing logic has drifted from what's written above; don't adjust the test's expected numbers to match, find the discrepancy.

- [ ] **Step 5: Commit**

```bash
git add backend/app/prediction/backtest.py backend/tests/test_backtest.py
git commit -m "feat(backend): add rolling-origin backtest harness"
```

---

### Task 5: Prediction engine Supabase I/O layer

**Files:**
- Create: `backend/app/prediction/supabase_rest.py`
- Test: `backend/tests/test_prediction_supabase_rest.py`

**Interfaces:**
- Consumes: `get_settings()` from `app.config` (existing).
- Produces: `get_rate_series(quote_code: str) -> tuple[list[str], list[float]]`, `insert_predictions(rows: list[dict]) -> None`, `get_backtest_stats(quote_code: str, horizon_days: int) -> dict | None`, `upsert_backtest_stats(rows: list[dict]) -> None` in `app.prediction.supabase_rest`. All consumed by Task 6 (`jobs.py`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_prediction_supabase_rest.py`:

```python
from unittest.mock import MagicMock, patch

from app.prediction.supabase_rest import (
    get_backtest_stats,
    get_rate_series,
    insert_predictions,
    upsert_backtest_stats,
)


def test_get_rate_series_returns_parallel_date_and_rate_lists():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"as_of": "2020-01-01", "rate": 0.9},
        {"as_of": "2020-01-02", "rate": 0.91},
    ]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.prediction.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        dates, rates = get_rate_series("EUR")

    assert dates == ["2020-01-01", "2020-01-02"]
    assert rates == [0.9, 0.91]
    args, kwargs = mock_get.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/rates_cache"
    assert kwargs["params"] == {
        "select": "as_of,rate",
        "base_code": "eq.USD",
        "quote_code": "eq.EUR",
        "order": "as_of.asc",
    }


def test_insert_predictions_posts_batch():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {
            "base_code": "USD",
            "quote_code": "EUR",
            "horizon_days": 7,
            "predicted_rate": 0.87,
            "lower_bound": 0.85,
            "upper_bound": 0.89,
            "confidence": "normal",
        }
    ]
    with patch(
        "app.prediction.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        insert_predictions(rows)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/predictions"
    assert kwargs["json"] == rows


def test_get_backtest_stats_returns_stats_when_found():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"error_lower_pct": -0.02, "error_upper_pct": 0.03, "volatility_p90": 0.015}
    ]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.prediction.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_backtest_stats("EUR", 30)

    assert result == {
        "error_lower_pct": -0.02,
        "error_upper_pct": 0.03,
        "volatility_p90": 0.015,
    }
    args, kwargs = mock_get.call_args
    assert kwargs["params"] == {
        "select": "error_lower_pct,error_upper_pct,volatility_p90",
        "quote_code": "eq.EUR",
        "horizon_days": "eq.30",
    }


def test_get_backtest_stats_returns_none_when_not_found():
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None
    with patch("app.prediction.supabase_rest.httpx.get", return_value=mock_response):
        result = get_backtest_stats("EUR", 30)

    assert result is None


def test_upsert_backtest_stats_posts_with_merge_duplicates():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {
            "quote_code": "EUR",
            "horizon_days": 30,
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.015,
            "sample_count": 240,
        }
    ]
    with patch(
        "app.prediction.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        upsert_backtest_stats(rows)

    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/backtest_stats"
    assert kwargs["params"] == {"on_conflict": "quote_code,horizon_days"}
    assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates"
    assert kwargs["json"] == rows
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_prediction_supabase_rest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.prediction.supabase_rest'`.

- [ ] **Step 3: Implement `backend/app/prediction/supabase_rest.py`**

```python
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


def get_rate_series(quote_code: str) -> tuple[list[str], list[float]]:
    """Returns (dates, rates) for `quote_code`'s USD-pivot series, ordered
    oldest to newest -- the same values rates_cache stores for
    (base_code='USD', quote_code=<quote_code>).
    """
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/rates_cache",
        params={
            "select": "as_of,rate",
            "base_code": "eq.USD",
            "quote_code": f"eq.{quote_code}",
            "order": "as_of.asc",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    dates = [row["as_of"] for row in rows]
    rates = [float(row["rate"]) for row in rows]
    return dates, rates


def insert_predictions(rows: list[dict]) -> None:
    """Appends a batch of prediction rows. Plain insert, not upsert --
    `predictions` has no unique constraint (unlike rates_cache and
    backtest_stats), so each day's run adds a fresh, generated_at-stamped
    batch rather than replacing prior predictions in place. A future
    consumer looking for "today's" prediction for a pair+horizon should
    query for the most recent generated_at.
    """
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/predictions",
            headers=_headers(),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()


def get_backtest_stats(quote_code: str, horizon_days: int) -> dict | None:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/backtest_stats",
        params={
            "select": "error_lower_pct,error_upper_pct,volatility_p90",
            "quote_code": f"eq.{quote_code}",
            "horizon_days": f"eq.{horizon_days}",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    return {
        "error_lower_pct": float(results[0]["error_lower_pct"]),
        "error_upper_pct": float(results[0]["error_upper_pct"]),
        "volatility_p90": float(results[0]["volatility_p90"]),
    }


def upsert_backtest_stats(rows: list[dict]) -> None:
    settings = get_settings()
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/backtest_stats",
        params={"on_conflict": "quote_code,horizon_days"},
        headers=_headers(prefer="resolution=merge-duplicates"),
        json=rows,
        timeout=60.0,
    )
    response.raise_for_status()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_prediction_supabase_rest.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/prediction/supabase_rest.py backend/tests/test_prediction_supabase_rest.py
git commit -m "feat(backend): add prediction engine Supabase I/O layer"
```

---

### Task 6: Daily forecast and weekly backtest orchestration

**Files:**
- Create: `backend/app/prediction/jobs.py`
- Test: `backend/tests/test_jobs.py`

**Interfaces:**
- Consumes: `get_active_currencies()` from `app.ingestion.supabase_rest` (existing, shipped in the data ingestion pipeline). `forecast(values, steps)` from `app.prediction.model` (Task 2). `trading_day_steps(horizon_days)` from `app.prediction.horizons`, `realized_volatility(rates, end_index)` from `app.prediction.stats` (Task 3). `run_backtest(rates, horizons)`, `summarize(samples)` from `app.prediction.backtest` (Task 4). `get_rate_series`, `insert_predictions`, `get_backtest_stats`, `upsert_backtest_stats` from `app.prediction.supabase_rest` (Task 5).
- Produces: `run_forecast() -> int` and `run_backtest_job() -> int` in `app.prediction.jobs` (both return the number of rows written). Consumed by Task 7 (`cli.py`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_jobs.py`:

```python
from unittest.mock import patch

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
        },
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        count = run_forecast()

    assert count == 4  # one row per horizon (7/30/90/365) for the one non-USD currency
    rows = mock_insert.call_args[0][0]
    assert all(r["base_code"] == "USD" and r["quote_code"] == "EUR" for r in rows)
    assert all(r["confidence"] == "normal" for r in rows)  # 0.01 vol < 0.02 p90
    first = rows[0]
    assert first["predicted_rate"] == 0.91
    assert first["lower_bound"] == 0.91 + (-0.02)
    assert first["upper_bound"] == 0.91 + 0.03


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
        },
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
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        count = run_forecast()

    assert count == 0
    mock_insert.assert_called_once_with([])


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
        "app.prediction.jobs.run_backtest", return_value=fake_results
    ), patch("app.prediction.jobs.upsert_backtest_stats") as mock_upsert:
        count = run_backtest_job()

    assert count == 1  # horizon 30 skipped (no samples), only horizon 7 written
    rows = mock_upsert.call_args[0][0]
    assert rows[0]["quote_code"] == "EUR"
    assert rows[0]["horizon_days"] == 7
    assert rows[0]["sample_count"] == 3
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.prediction.jobs'`.

- [ ] **Step 3: Implement `backend/app/prediction/jobs.py`**

```python
from app.ingestion.supabase_rest import get_active_currencies
from app.prediction.backtest import run_backtest, summarize
from app.prediction.horizons import trading_day_steps
from app.prediction.model import forecast
from app.prediction.stats import realized_volatility
from app.prediction.supabase_rest import (
    get_backtest_stats,
    get_rate_series,
    insert_predictions,
    upsert_backtest_stats,
)

PIVOT = "USD"
HORIZONS = [7, 30, 90, 365]


def _predictable_currencies() -> list[str]:
    return [code for code in get_active_currencies() if code != PIVOT]


def run_forecast() -> int:
    """Daily job: for every USD-quoted currency, fit today's model and
    forecast each horizon, building a confidence band from that pair's
    most recent backtest_stats and flagging low-confidence when current
    volatility exceeds its own historical 90th percentile. A (currency,
    horizon) with no backtest_stats yet (e.g. before the first weekly
    backtest has run) is skipped for that row only, not treated as an
    error.
    """
    rows = []
    for quote_code in _predictable_currencies():
        _dates, rates = get_rate_series(quote_code)
        if len(rates) < 2:
            continue
        current_vol = realized_volatility(rates, len(rates))
        for horizon_days in HORIZONS:
            stats = get_backtest_stats(quote_code, horizon_days)
            if stats is None:
                continue
            steps = trading_day_steps(horizon_days)
            predicted_rate = forecast(rates, steps)
            confidence = "low" if current_vol > stats["volatility_p90"] else "normal"
            rows.append(
                {
                    "base_code": PIVOT,
                    "quote_code": quote_code,
                    "horizon_days": horizon_days,
                    "predicted_rate": predicted_rate,
                    "lower_bound": predicted_rate + stats["error_lower_pct"],
                    "upper_bound": predicted_rate + stats["error_upper_pct"],
                    "confidence": confidence,
                }
            )
    insert_predictions(rows)
    return len(rows)


def run_backtest_job() -> int:
    """Weekly job: re-runs the rolling-origin backtest for every USD-quoted
    currency and refreshes backtest_stats. A (currency, horizon) with no
    usable backtest samples is skipped for that row only.
    """
    rows = []
    for quote_code in _predictable_currencies():
        _dates, rates = get_rate_series(quote_code)
        results = run_backtest(rates, HORIZONS)
        for horizon_days, samples in results.items():
            if not samples["errors"]:
                continue
            summary = summarize(samples)
            rows.append(
                {
                    "quote_code": quote_code,
                    "horizon_days": horizon_days,
                    "error_lower_pct": summary["error_lower_pct"],
                    "error_upper_pct": summary["error_upper_pct"],
                    "volatility_p90": summary["volatility_p90"],
                    "sample_count": summary["sample_count"],
                }
            )
    upsert_backtest_stats(rows)
    return len(rows)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_jobs.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/prediction/jobs.py backend/tests/test_jobs.py
git commit -m "feat(backend): add daily forecast and weekly backtest orchestration"
```

---

### Task 7: CLI entrypoint

**Files:**
- Create: `backend/app/prediction/cli.py`
- Test: `backend/tests/test_prediction_cli.py`

**Interfaces:**
- Consumes: `run_forecast() -> int`, `run_backtest_job() -> int` from `app.prediction.jobs` (Task 6).
- Produces: `main(argv: list[str] | None = None) -> None` in `app.prediction.cli`, runnable as `python -m app.prediction.cli --mode forecast` or `--mode backtest`. Consumed by Task 8's GitHub Actions workflow.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_prediction_cli.py`:

```python
from unittest.mock import patch

from app.prediction.cli import main


def test_forecast_mode_calls_run_forecast():
    with patch(
        "app.prediction.cli.run_forecast", return_value=116
    ) as mock_forecast, patch("app.prediction.cli.run_backtest_job") as mock_backtest:
        main(["--mode", "forecast"])

    mock_forecast.assert_called_once()
    mock_backtest.assert_not_called()


def test_backtest_mode_calls_run_backtest_job():
    with patch("app.prediction.cli.run_forecast") as mock_forecast, patch(
        "app.prediction.cli.run_backtest_job", return_value=116
    ) as mock_backtest:
        main(["--mode", "backtest"])

    mock_backtest.assert_called_once()
    mock_forecast.assert_not_called()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_prediction_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.prediction.cli'`.

- [ ] **Step 3: Implement `backend/app/prediction/cli.py`**

```python
import argparse

from app.prediction.jobs import run_backtest_job, run_forecast


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ForexCast prediction engine")
    parser.add_argument("--mode", choices=["forecast", "backtest"], required=True)
    args = parser.parse_args(argv)

    if args.mode == "forecast":
        count = run_forecast()
    else:
        count = run_backtest_job()

    print(f"Wrote {count} rows ({args.mode})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_prediction_cli.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full backend suite to confirm nothing broke**

Run: `pytest backend/tests -v`
Expected: PASS (all tests — everything from the foundation and ingestion plans, plus this plan's new prediction-engine tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/prediction/cli.py backend/tests/test_prediction_cli.py
git commit -m "feat(backend): add prediction engine CLI entrypoint"
```

---

### Task 8: GitHub Actions scheduled workflow

**Files:**
- Create: `.github/workflows/predict.yml`

**Interfaces:**
- Consumes: `backend/requirements.txt` (Task 2), `python -m app.prediction.cli` (Task 7).
- Produces: none consumed by later tasks — leaf task.

- [ ] **Step 1: Create `.github/workflows/predict.yml`**

```yaml
name: Generate predictions

on:
  schedule:
    # Daily forecast: 18:00 UTC, an hour after the rates-ingestion cron
    # (17:00 UTC) so today's rate is already in rates_cache.
    - cron: '0 18 * * *'
    # Weekly backtest: Sundays at 19:00 UTC.
    - cron: '0 19 * * 0'
  workflow_dispatch:
    inputs:
      mode:
        description: 'Prediction mode (leave as auto to infer from schedule, or force one)'
        required: true
        default: 'forecast'
        type: choice
        options:
          - forecast
          - backtest

jobs:
  predict:
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
      - name: Determine mode
        id: mode
        env:
          DISPATCH_MODE: ${{ github.event.inputs.mode }}
          CRON_SCHEDULE: ${{ github.event.schedule }}
        run: |
          if [ -n "$DISPATCH_MODE" ]; then
            echo "mode=$DISPATCH_MODE" >> "$GITHUB_OUTPUT"
          elif [ "$CRON_SCHEDULE" = "0 19 * * 0" ]; then
            echo "mode=backtest" >> "$GITHUB_OUTPUT"
          else
            echo "mode=forecast" >> "$GITHUB_OUTPUT"
          fi
      - name: Run prediction job
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
          MODE: ${{ steps.mode.outputs.mode }}
        run: python -m app.prediction.cli --mode "$MODE"
```

Note: all dynamic values flow through `env:` blocks and are referenced as shell variables (`$MODE`, etc.) — never interpolated directly into the `run:` script body via `${{ }}`. This avoids the script-injection anti-pattern a final review caught (and a fix wave had to close) in the ingestion pipeline's original workflow — applying that lesson here from the start rather than needing a second fix round.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/predict.yml
git commit -m "ci: add scheduled GitHub Actions workflow for predictions"
```

---

### Task 9: Live verification

No new GitHub Actions secrets are needed — `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are already configured from the ingestion pipeline.

- [ ] **Step 1: Trigger a manual backtest run first**

Backtest must run before forecast, or `run_forecast()` will find no `backtest_stats` rows yet and write nothing (it skips gracefully rather than failing, per Task 6 — but the point of this task is to see real populated data).

On GitHub: repo → Actions → "Generate predictions" → Run workflow → mode = `backtest` → Run workflow. Wait for a green checkmark.

- [ ] **Step 2: Verify `backtest_stats` populated**

If `mcp__supabase__execute_sql` isn't already loaded: `ToolSearch(query="select:mcp__supabase__execute_sql")`.

`mcp__supabase__execute_sql(query="select count(*) as rows, count(distinct quote_code) as currencies from public.backtest_stats")`
Expected: `currencies` = 29, `rows` up to 116 (29 currencies × 4 horizons — could be fewer if any currency+horizon combination didn't have enough backtest samples, which is fine and expected, not a failure).

- [ ] **Step 3: Trigger a manual forecast run**

On GitHub: repo → Actions → "Generate predictions" → Run workflow → mode = `forecast` → Run workflow. Wait for a green checkmark.

- [ ] **Step 4: Verify `predictions` populated**

`mcp__supabase__execute_sql(query="select count(*) as rows, count(distinct quote_code) as currencies, count(distinct horizon_days) as horizons from public.predictions")`
Expected: `horizons` = 4 (7/30/90/365), `currencies` up to 29, `rows` up to 116.

`mcp__supabase__execute_sql(query="select quote_code, horizon_days, predicted_rate, lower_bound, upper_bound, confidence from public.predictions order by generated_at desc limit 5")`
Expected: 5 rows with sane-looking numbers — `lower_bound < predicted_rate < upper_bound` for each row, `confidence` is `'normal'` or `'low'`.

- [ ] **Step 5: Run the full backend test suite one more time**

Run: `pytest backend/tests -v`
Expected: PASS, all tests, no live network calls in the suite itself.

- [ ] **Step 6: Confirm nothing is left uncommitted**

Run: `git status --short`
Expected: clean.

## Definition of Done

- `public.backtest_stats` exists with RLS enabled and no public read policy.
- `pytest backend/tests -v` passes, including all new prediction-engine tests, with zero live network calls.
- A manual `workflow_dispatch` backtest run completes successfully and populates `backtest_stats` for (up to) all 29 currencies × 4 horizons.
- A manual `workflow_dispatch` forecast run completes successfully and populates `predictions` with sane bands (`lower_bound < predicted_rate < upper_bound`) and a valid `confidence` value.
- The scheduled triggers (daily forecast, weekly backtest) are present in the committed workflow file — no further action needed for them to run automatically going forward.
- 2b (FRED regression) and 2c (GDELT + LLM sentiment) remain tracked in the foundation plan's roadmap note as explicit follow-ups.
