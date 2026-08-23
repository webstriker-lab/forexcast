# Accuracy Validation & Date Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the backtest with accuracy metrics, surface them on a new /accuracy page, add a date-interpolation feature to the dashboard, write a calibration pytest test, and stand up a Playwright E2E suite.

**Architecture:** Backend `summarize()` gains four new fields (es_mae, naive_mae, mae_improvement_pct, calibration_coverage); a DB migration adds those columns to backtest_stats; the frontend reads them directly from Supabase in a new /accuracy page. The date picker calls a new `interpolatePrediction()` utility in `predictionMath.ts`; Playwright tests run against a local Vite dev server with real Supabase credentials.

**Tech Stack:** Python 3.11 / pytest (backend), React 18 / TypeScript / Vitest / Tailwind (frontend), Supabase (DB), Playwright (E2E), Frankfurter API (fixture fetch only).

**Spec:** `docs/superpowers/specs/2026-08-23-accuracy-testing-design.md`

## Global Constraints

- Backend tests run with `pytest backend/tests/` from repo root — no SUPABASE env vars needed for the calibration test (fixture is local JSON).
- Frontend unit tests run with `npm test` inside `frontend/`.
- Playwright tests run with `npm run test:e2e` inside `frontend/` and require `frontend/.env.test` with `VITE_TEST_EMAIL` and `VITE_TEST_PASSWORD` for a live Supabase test user.
- All new Python code must be compatible with existing imports (`from app.prediction.backtest import ...`).
- All new TypeScript must pass `tsc -b` (strict mode already enabled in tsconfig).
- No new npm dependencies except `@playwright/test` (Task 8).
- Row color coding: green = `model_selected === 'exponential_smoothing'`; gray = `model_selected === 'naive'`.
- MAE values from backtest are stored as raw fractions (e.g. 0.0082 = 0.82%); multiply by 100 before displaying as %.

---

## File Map

**Modified:**
- `backend/app/prediction/backtest.py` — `summarize()` returns four new keys
- `backend/app/prediction/jobs.py` — `run_backtest_job()` row dict includes new keys
- `frontend/src/lib/predictionMath.ts` — `interpolatePrediction()` added, `InterpolatedPrediction` type exported
- `frontend/src/lib/predictionMath.test.ts` — five new test cases
- `frontend/src/pages/Dashboard.tsx` — date picker state + `DatePredictionCard` wiring
- `frontend/src/App.tsx` — `/accuracy` route
- `frontend/src/components/Layout.tsx` — "Accuracy" nav link
- `frontend/package.json` — `test:e2e` script
- `frontend/.gitignore` — `e2e/.auth/` entry

**Created:**
- `backend/scripts/fetch_fixture.py` — one-off script to download EUR/USD fixture (not in test suite)
- `backend/tests/fixtures/eurusd_rates.json` — committed fixture (~500 rows)
- `backend/tests/test_accuracy_calibration.py` — calibration pytest
- `frontend/src/lib/accuracyData.ts` — Supabase query for backtest_stats
- `frontend/src/hooks/useAccuracyStats.ts` — hook grouping stats by horizon
- `frontend/src/pages/Accuracy.tsx` — accuracy page component
- `frontend/src/components/DatePredictionCard.tsx` — interpolated prediction display card
- `frontend/playwright.config.ts` — Playwright config
- `frontend/e2e/global-setup.ts` — login once, save storage state
- `frontend/e2e/auth.spec.ts` — auth E2E tests
- `frontend/e2e/dashboard.spec.ts` — dashboard E2E tests
- `frontend/e2e/accuracy.spec.ts` — accuracy page E2E tests

---

## Task 1: Extend `summarize()` with accuracy metrics

**Files:**
- Modify: `backend/app/prediction/backtest.py` (function `summarize`, lines 165–224)
- Create: `backend/tests/test_prediction_backtest.py`

**Interfaces:**
- Produces: `summarize(samples) -> dict` now includes keys `es_mae: float | None`, `naive_mae: float | None`, `mae_improvement_pct: float | None`, `calibration_coverage: float`

- [ ] **Step 1: Write failing tests for the four new keys**

Create `backend/tests/test_prediction_backtest.py`:

```python
import pytest
from app.prediction.backtest import summarize


def _samples(errors, naive_errors=None, trailing_vols=None):
    return {
        "errors": errors,
        "naive_errors": naive_errors if naive_errors is not None else [],
        "trailing_vols": trailing_vols or [0.01] * len(errors),
    }


def test_summarize_es_mae_is_mean_abs_error():
    # errors = [0.1, -0.1] → MAE = 0.1
    s = summarize(_samples([0.1, -0.1], naive_errors=[0.2, -0.2]))
    assert s["es_mae"] == pytest.approx(0.1)


def test_summarize_naive_mae_is_mean_abs_naive_error():
    # naive errors = [0.2, -0.2] → naive MAE = 0.2
    s = summarize(_samples([0.1, -0.1], naive_errors=[0.2, -0.2]))
    assert s["naive_mae"] == pytest.approx(0.2)


def test_summarize_mae_improvement_positive_when_es_wins():
    # es_mae=0.1, naive_mae=0.2 → (0.2-0.1)/0.2*100 = 50%
    s = summarize(_samples([0.1, -0.1], naive_errors=[0.2, -0.2]))
    assert s["mae_improvement_pct"] == pytest.approx(50.0, abs=0.01)


def test_summarize_mae_improvement_negative_when_naive_wins():
    # es_mae=0.2, naive_mae=0.1 → (0.1-0.2)/0.1*100 = -100%
    s = summarize(_samples([0.2, -0.2], naive_errors=[0.1, -0.1]))
    assert s["mae_improvement_pct"] == pytest.approx(-100.0, abs=0.01)


def test_summarize_mae_improvement_none_when_no_naive_errors():
    s = summarize(_samples([0.1, -0.1]))
    assert s["mae_improvement_pct"] is None
    assert s["naive_mae"] is None


def test_summarize_calibration_coverage_between_zero_and_one():
    errors = [float(i) * 0.01 for i in range(-5, 6)]  # -0.05..0.05
    s = summarize(_samples(errors, naive_errors=errors[:]))
    assert 0.0 <= s["calibration_coverage"] <= 1.0


def test_summarize_calibration_coverage_near_eighty_percent_for_uniform_errors():
    # 10 evenly spaced errors: p10=min+0.9*range, p90=max-0.9*range
    # 8 of 10 should fall within [p10, p90]
    errors = [float(i) for i in range(1, 11)]
    s = summarize(_samples(errors, naive_errors=errors[:]))
    assert s["calibration_coverage"] >= 0.70
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd D:/FOREX-RATE-PREDICTING-APP && python -m pytest backend/tests/test_prediction_backtest.py -v
```

Expected: all seven tests FAIL with `KeyError: 'es_mae'` or similar.

- [ ] **Step 3: Extend `summarize()` in `backtest.py`**

In `backend/app/prediction/backtest.py`, replace the `return` statement at the end of `summarize()` (currently lines 215–224) with:

```python
    # Accuracy metrics — computed from raw ES errors and raw naive errors
    # so the comparison is always ES vs naive regardless of which model won.
    es_mae: float | None = sum(abs(e) for e in errors) / len(errors) if errors else None
    naive_mae: float | None = (
        sum(abs(e) for e in naive_errors) / len(naive_errors) if naive_errors else None
    )
    if es_mae is not None and naive_mae is not None and naive_mae != 0:
        mae_improvement_pct: float | None = (naive_mae - es_mae) / naive_mae * 100
    else:
        mae_improvement_pct = None

    error_lower = percentile(sorted(residuals), 10)
    error_upper = percentile(sorted(residuals), 90)
    calibration_coverage = (
        sum(1 for r in residuals if error_lower <= r <= error_upper) / len(residuals)
        if residuals
        else 0.0
    )

    return {
        "model_selected": model_selected,
        "error_lower_pct": error_lower,
        "error_upper_pct": error_upper,
        "volatility_p90": percentile(sorted(samples["trailing_vols"]), 90),
        "sample_count": len(selected_errors),
        "regression_factor": regression_factor,
        "regression_slope": regression["slope"] if regression else None,
        "regression_intercept": regression["intercept"] if regression else None,
        "es_mae": es_mae,
        "naive_mae": naive_mae,
        "mae_improvement_pct": mae_improvement_pct,
        "calibration_coverage": calibration_coverage,
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest backend/tests/test_prediction_backtest.py -v
```

Expected: all seven PASS.

- [ ] **Step 5: Confirm existing backtest tests still pass**

```bash
python -m pytest backend/tests/ -v --ignore=backend/tests/test_accuracy_calibration.py
```

Expected: all pre-existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/prediction/backtest.py backend/tests/test_prediction_backtest.py
git commit -m "feat: add es_mae, naive_mae, mae_improvement_pct, calibration_coverage to summarize()"
```

---

## Task 2: DB migration + `jobs.py` row update

**Files:**
- DB migration (apply via Supabase MCP)
- Modify: `backend/app/prediction/jobs.py` — row dict in `run_backtest_job()`

**Interfaces:**
- Consumes: `summarize()` now returns `es_mae`, `naive_mae`, `mae_improvement_pct`, `calibration_coverage` (from Task 1)
- Produces: `backtest_stats` table has four new nullable float columns; `upsert_backtest_stats` receives rows that include them

- [ ] **Step 1: Apply the DB migration**

Use the Supabase MCP tool (`mcp__supabase__apply_migration`) with this SQL:

```sql
ALTER TABLE backtest_stats
  ADD COLUMN IF NOT EXISTS es_mae FLOAT,
  ADD COLUMN IF NOT EXISTS naive_mae FLOAT,
  ADD COLUMN IF NOT EXISTS mae_improvement_pct FLOAT,
  ADD COLUMN IF NOT EXISTS calibration_coverage FLOAT;
```

Verify with: `SELECT column_name FROM information_schema.columns WHERE table_name = 'backtest_stats';` — the four new columns must appear.

- [ ] **Step 2: Update `run_backtest_job()` in `jobs.py`**

In `backend/app/prediction/jobs.py`, find the `rows.append({...})` block inside `run_backtest_job()` (currently the dict ends at `"regression_intercept": summary["regression_intercept"]`). Add the four new keys:

```python
            rows.append(
                {
                    "quote_code": quote_code,
                    "horizon_days": horizon_days,
                    "model_selected": summary["model_selected"],
                    "error_lower_pct": summary["error_lower_pct"],
                    "error_upper_pct": summary["error_upper_pct"],
                    "volatility_p90": summary["volatility_p90"],
                    "sample_count": summary["sample_count"],
                    "regression_factor": summary["regression_factor"],
                    "regression_slope": summary["regression_slope"],
                    "regression_intercept": summary["regression_intercept"],
                    "es_mae": summary["es_mae"],
                    "naive_mae": summary["naive_mae"],
                    "mae_improvement_pct": summary["mae_improvement_pct"],
                    "calibration_coverage": summary["calibration_coverage"],
                }
            )
```

- [ ] **Step 3: Run full backend test suite to confirm nothing broke**

```bash
python -m pytest backend/tests/ -v --ignore=backend/tests/test_accuracy_calibration.py
```

Expected: all PASS. (`test_accuracy_calibration.py` doesn't exist yet — ignore it.)

- [ ] **Step 4: Commit**

```bash
git add backend/app/prediction/jobs.py
git commit -m "feat: pass accuracy metrics through to backtest_stats upsert"
```

---

## Task 3: EUR/USD fixture + backend calibration test

**Files:**
- Create: `backend/scripts/fetch_fixture.py`
- Create: `backend/tests/fixtures/eurusd_rates.json`
- Create: `backend/tests/test_accuracy_calibration.py`

**Interfaces:**
- Consumes: `run_backtest(rates, horizons)` and `summarize(samples)` from `app.prediction.backtest`
- Produces: passing pytest that proves calibration is structurally sound on real EUR/USD history

- [ ] **Step 1: Create the one-off fixture fetch script**

Create `backend/scripts/fetch_fixture.py`:

```python
"""One-off script: fetch ~2 years of USD/EUR daily rates from Frankfurter
and write them to backend/tests/fixtures/eurusd_rates.json.
Run once from the repo root: python backend/scripts/fetch_fixture.py
"""
import json
import pathlib
import urllib.request

URL = "https://api.frankfurter.app/2024-01-01..2026-08-22?from=USD&to=EUR"

response = urllib.request.urlopen(URL)
data = json.loads(response.read())

rows = [
    {"date": date, "rate": rates["EUR"]}
    for date, rates in sorted(data["rates"].items())
]

out = pathlib.Path(__file__).parent.parent / "tests" / "fixtures" / "eurusd_rates.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(rows, indent=2))
print(f"Wrote {len(rows)} rows to {out}")
```

- [ ] **Step 2: Run the script to generate the fixture**

```bash
python backend/scripts/fetch_fixture.py
```

Expected output: `Wrote NNN rows to backend/tests/fixtures/eurusd_rates.json` where NNN ≥ 400.

Verify the first few rows look like:
```json
[
  {"date": "2024-01-02", "rate": 0.9116},
  {"date": "2024-01-03", "rate": 0.9073},
  ...
]
```

- [ ] **Step 3: Write the calibration test**

Create `backend/tests/test_accuracy_calibration.py`:

```python
"""Calibration test: proves summarize()'s output is structurally sound on
real EUR/USD history loaded from a committed fixture file. Runs with no
network access and no SUPABASE env vars.

Does NOT assert ES beats naive — that would violate ADR-0001 (the app
uses whichever model wins the backtest per pair/horizon). Only asserts
structural properties: enough samples, bands straddle zero, coverage ≥ 70%,
MAEs are positive floats, model_selected is a recognised string.
"""
import json
import pathlib

import pytest

from app.prediction.backtest import run_backtest, summarize

HORIZONS = [7, 30, 90, 365]


@pytest.fixture(scope="module")
def eurusd_rates() -> list[float]:
    path = pathlib.Path(__file__).parent / "fixtures" / "eurusd_rates.json"
    rows = json.loads(path.read_text())
    return [float(r["rate"]) for r in rows]


@pytest.fixture(scope="module")
def summaries(eurusd_rates) -> dict[int, dict]:
    results = run_backtest(eurusd_rates, horizons=HORIZONS)
    return {h: summarize(results[h]) for h in HORIZONS}


@pytest.mark.parametrize("horizon", HORIZONS)
def test_sample_count_is_sufficient(summaries, horizon):
    assert summaries[horizon]["sample_count"] >= 10, (
        f"horizon={horizon}d has only {summaries[horizon]['sample_count']} backtest origins — "
        "fixture may be too short"
    )


@pytest.mark.parametrize("horizon", HORIZONS)
def test_confidence_band_straddles_zero(summaries, horizon):
    s = summaries[horizon]
    assert s["error_lower_pct"] < 0, (
        f"horizon={horizon}d: error_lower_pct={s['error_lower_pct']} is not negative — "
        "confidence band doesn't reach below the point forecast"
    )
    assert s["error_upper_pct"] > 0, (
        f"horizon={horizon}d: error_upper_pct={s['error_upper_pct']} is not positive — "
        "confidence band doesn't reach above the point forecast"
    )


@pytest.mark.parametrize("horizon", HORIZONS)
def test_calibration_coverage_at_least_seventy_percent(summaries, horizon):
    cov = summaries[horizon]["calibration_coverage"]
    assert cov >= 0.70, (
        f"horizon={horizon}d: calibration_coverage={cov:.2%} < 70% — "
        "fewer actuals than expected fell inside the stated confidence band"
    )


@pytest.mark.parametrize("horizon", HORIZONS)
def test_mae_values_are_positive_floats(summaries, horizon):
    s = summaries[horizon]
    assert isinstance(s["es_mae"], float) and s["es_mae"] > 0, (
        f"horizon={horizon}d: es_mae={s['es_mae']} is not a positive float"
    )
    assert isinstance(s["naive_mae"], float) and s["naive_mae"] > 0, (
        f"horizon={horizon}d: naive_mae={s['naive_mae']} is not a positive float"
    )


@pytest.mark.parametrize("horizon", HORIZONS)
def test_model_selected_is_valid(summaries, horizon):
    ms = summaries[horizon]["model_selected"]
    assert ms in ("exponential_smoothing", "naive"), (
        f"horizon={horizon}d: model_selected={ms!r} is not a recognised value"
    )
```

- [ ] **Step 4: Run the calibration test**

```bash
python -m pytest backend/tests/test_accuracy_calibration.py -v
```

Expected: all 20 tests (5 assertions × 4 horizons) PASS. If `calibration_coverage` fails on the 365d horizon, investigate whether the fixture has enough data — the 365d horizon needs `MIN_HISTORY (60) + 365 = 425+` trading days in the fixture. The fetch window (2024-01-01 to 2026-08-22) covers ~650 trading days so this should be fine.

- [ ] **Step 5: Commit fixture and test**

```bash
git add backend/scripts/fetch_fixture.py backend/tests/fixtures/eurusd_rates.json backend/tests/test_accuracy_calibration.py
git commit -m "test: add EUR/USD calibration fixture and accuracy calibration pytest"
```

---

## Task 4: Accuracy data layer (frontend)

**Files:**
- Create: `frontend/src/lib/accuracyData.ts`
- Create: `frontend/src/hooks/useAccuracyStats.ts`

**Interfaces:**
- Consumes: Supabase `backtest_stats` table (must have RLS allowing authenticated reads — same as `predictions` and `rates_cache`)
- Produces:
  - `fetchAccuracyStats(): Promise<BacktestStat[]>`
  - `BacktestStat` interface (exported)
  - `useAccuracyStats(): { statsByHorizon: Map<number, BacktestStat[]>, loading: boolean, error: string | null }`

- [ ] **Step 1: Verify `backtest_stats` RLS allows authenticated reads**

In the Supabase dashboard (or via MCP), confirm `backtest_stats` has a SELECT policy for `authenticated` role. If not, add:

```sql
CREATE POLICY "authenticated users can read backtest_stats"
ON backtest_stats FOR SELECT
TO authenticated
USING (true);
```

- [ ] **Step 2: Create `accuracyData.ts`**

Create `frontend/src/lib/accuracyData.ts`:

```typescript
import { supabase } from './supabaseClient'

export interface BacktestStat {
  quote_code: string
  horizon_days: number
  model_selected: 'exponential_smoothing' | 'naive'
  es_mae: number | null
  naive_mae: number | null
  mae_improvement_pct: number | null
  calibration_coverage: number | null
  sample_count: number
}

export async function fetchAccuracyStats(): Promise<BacktestStat[]> {
  const { data, error } = await supabase
    .from('backtest_stats')
    .select(
      'quote_code, horizon_days, model_selected, es_mae, naive_mae, mae_improvement_pct, calibration_coverage, sample_count',
    )
    .order('quote_code', { ascending: true })

  if (error) throw new Error(error.message)
  return (data ?? []) as BacktestStat[]
}
```

- [ ] **Step 3: Create `useAccuracyStats.ts`**

Create `frontend/src/hooks/useAccuracyStats.ts`:

```typescript
import { useEffect, useState } from 'react'
import { fetchAccuracyStats, type BacktestStat } from '../lib/accuracyData'

export type StatsByHorizon = Map<number, BacktestStat[]>

export function useAccuracyStats() {
  const [statsByHorizon, setStatsByHorizon] = useState<StatsByHorizon>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchAccuracyStats()
      .then((rows) => {
        const grouped = new Map<number, BacktestStat[]>()
        for (const row of rows) {
          const existing = grouped.get(row.horizon_days) ?? []
          grouped.set(row.horizon_days, [...existing, row])
        }
        setStatsByHorizon(grouped)
        setError(null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [])

  return { statsByHorizon, loading, error }
}
```

- [ ] **Step 4: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors on the two new files.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/accuracyData.ts frontend/src/hooks/useAccuracyStats.ts
git commit -m "feat: add accuracyData Supabase query and useAccuracyStats hook"
```

---

## Task 5: Accuracy page + routing

**Files:**
- Create: `frontend/src/pages/Accuracy.tsx`
- Modify: `frontend/src/App.tsx` — add `/accuracy` route
- Modify: `frontend/src/components/Layout.tsx` — add "Accuracy" nav link

**Interfaces:**
- Consumes: `useAccuracyStats()` from Task 4, `BacktestStat` type, `Layout` component
- Produces: `/accuracy` page accessible to authenticated users

- [ ] **Step 1: Create `Accuracy.tsx`**

Create `frontend/src/pages/Accuracy.tsx`:

```tsx
import { useState } from 'react'
import { Layout } from '../components/Layout'
import { useAccuracyStats } from '../hooks/useAccuracyStats'
import type { BacktestStat } from '../lib/accuracyData'

const HORIZONS = [7, 30, 90, 365]
const HORIZON_LABELS: Record<number, string> = { 7: '7d', 30: '30d', 90: '90d', 365: '365d' }

function pct(n: number | null, decimals = 2): string {
  if (n === null) return '—'
  return `${(n * 100).toFixed(decimals)}%`
}

function ImprovementCell({ value }: { value: number | null }) {
  if (value === null || value <= 0) return <span className="text-gray-400">—</span>
  return <span className="text-green-700 font-medium">+{value.toFixed(1)}%</span>
}

function StatRow({ stat }: { stat: BacktestStat }) {
  const isES = stat.model_selected === 'exponential_smoothing'
  return (
    <tr className={isES ? 'bg-green-50' : 'bg-gray-50'}>
      <td className="px-4 py-2 text-sm font-medium text-gray-900">
        USD/{stat.quote_code}
      </td>
      <td className="px-4 py-2 text-sm text-gray-700">
        {isES ? 'ES' : 'Naive'}
      </td>
      <td className="px-4 py-2 text-sm text-gray-700">{pct(stat.es_mae)}</td>
      <td className="px-4 py-2 text-sm text-gray-700">{pct(stat.naive_mae)}</td>
      <td className="px-4 py-2 text-sm">
        <ImprovementCell value={stat.mae_improvement_pct} />
      </td>
      <td className="px-4 py-2 text-sm text-gray-700">
        {stat.calibration_coverage !== null
          ? `${(stat.calibration_coverage * 100).toFixed(0)}%`
          : '—'}
      </td>
      <td className="px-4 py-2 text-sm text-gray-500">{stat.sample_count}</td>
    </tr>
  )
}

export default function Accuracy() {
  const { statsByHorizon, loading, error } = useAccuracyStats()
  const [activeHorizon, setActiveHorizon] = useState(7)

  const rows = statsByHorizon.get(activeHorizon) ?? []
  const esBeatCount = rows.filter((r) => r.model_selected === 'exponential_smoothing').length
  const avgCalib =
    rows.length > 0
      ? rows.reduce((sum, r) => sum + (r.calibration_coverage ?? 0), 0) / rows.length
      : 0

  return (
    <Layout>
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Prediction Accuracy</h1>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center text-gray-400 py-12">Loading accuracy stats…</div>
        ) : (
          <>
            {/* Summary strip */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-800">
              <span className="font-semibold">
                {esBeatCount} of {rows.length} pairs
              </span>{' '}
              beat the naive baseline · avg calibration coverage:{' '}
              <span className="font-semibold">{(avgCalib * 100).toFixed(0)}%</span>
            </div>

            {/* Horizon tabs */}
            <div className="flex gap-2">
              {HORIZONS.map((h) => (
                <button
                  key={h}
                  onClick={() => setActiveHorizon(h)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeHorizon === h
                      ? 'bg-blue-600 text-white'
                      : 'bg-white text-gray-600 border border-gray-200 hover:border-blue-300'
                  }`}
                >
                  {HORIZON_LABELS[h]}
                </button>
              ))}
            </div>

            {/* Table */}
            <div className="bg-white rounded-lg shadow overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-gray-200">
                    {['Pair', 'Model', 'ES MAE', 'Naive MAE', 'Improvement', 'Calibration', 'Samples'].map(
                      (h) => (
                        <th
                          key={h}
                          className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide"
                        >
                          {h}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-gray-400 text-sm">
                        No backtest stats available yet. Run the weekly backtest job to populate
                        this page.
                      </td>
                    </tr>
                  ) : (
                    rows.map((stat) => <StatRow key={stat.quote_code} stat={stat} />)
                  )}
                </tbody>
              </table>
            </div>

            <p className="text-xs text-gray-400 text-center">
              ⚠️ Calibration coverage is in-sample (~80% expected). MAE is mean absolute % error
              across rolling backtest origins.
            </p>
          </>
        )}
      </div>
    </Layout>
  )
}
```

- [ ] **Step 2: Add route to `App.tsx`**

In `frontend/src/App.tsx`, after the existing `import Achievements from './pages/Achievements'` line, add:

```tsx
import Accuracy from './pages/Accuracy'
```

Inside the `<Routes>` block, after the `achievements` route, add:

```tsx
<Route path="/accuracy" element={<ProtectedRoute><Accuracy /></ProtectedRoute>} />
```

- [ ] **Step 3: Add nav link to `Layout.tsx`**

In `frontend/src/components/Layout.tsx`, find the `navItems` array and add `{ path: '/accuracy', label: 'Accuracy' }`:

```tsx
const navItems = [
  { path: '/dashboard', label: 'Dashboard' },
  { path: '/planner', label: 'Planner' },
  { path: '/alerts', label: 'Alerts' },
  { path: '/chat', label: 'Chat' },
  { path: '/accuracy', label: 'Accuracy' },
  { path: '/settings', label: 'Settings' },
]
```

- [ ] **Step 4: Type-check and run unit tests**

```bash
cd frontend && npx tsc --noEmit && npm test -- --run
```

Expected: no type errors, all existing tests pass.

- [ ] **Step 5: Start the dev server and manually verify the page**

```bash
cd frontend && npm run dev
```

Navigate to `http://localhost:5173/accuracy` while logged in. Confirm:
- "Prediction Accuracy" heading renders
- Horizon tabs 7d/30d/90d/365d render
- If `backtest_stats` has rows with the new columns populated, the table shows them; if rows are empty (new columns still NULL), the "No backtest stats" message shows
- Clicking horizon tabs switches the active tab

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Accuracy.tsx frontend/src/App.tsx frontend/src/components/Layout.tsx
git commit -m "feat: add /accuracy page with per-pair backtest stats table"
```

---

## Task 6: `interpolatePrediction()` + unit tests

**Files:**
- Modify: `frontend/src/lib/predictionMath.ts` — add `InterpolatedPrediction` type and `interpolatePrediction()` export
- Modify: `frontend/src/lib/predictionMath.test.ts` — five new test cases

**Interfaces:**
- Produces:
  ```typescript
  export interface InterpolatedPrediction extends RawPrediction {
    source_lower_days: number  // horizon used as the lower bound (or snap target)
    source_upper_days: number  // horizon used as the upper bound (or snap target)
  }
  export function interpolatePrediction(
    predictions: RawPrediction[],
    targetDays: number,
  ): InterpolatedPrediction
  ```

- [ ] **Step 1: Write failing tests**

Add to the bottom of `frontend/src/lib/predictionMath.test.ts`:

```typescript
import { interpolatePrediction } from './predictionMath'

// Helper — the `pred()` function already exists at the top of this file

describe('interpolatePrediction', () => {
  const p7 = pred({ horizon_days: 7, predicted_rate: 1.0, lower_bound: 0.9, upper_bound: 1.1, confidence: 'normal' })
  const p30 = pred({ horizon_days: 30, predicted_rate: 1.2, lower_bound: 1.1, upper_bound: 1.3, confidence: 'normal' })
  const p90 = pred({ horizon_days: 90, predicted_rate: 1.5, lower_bound: 1.3, upper_bound: 1.7, confidence: 'normal' })

  it('midpoint between 7d and 30d gives average of the two', () => {
    // t = (18-7)/(30-7) = 11/23; predicted = 1.0*(1-t) + 1.2*t
    const t = (18 - 7) / (30 - 7)
    const result = interpolatePrediction([p7, p30, p90], 18)
    expect(result.predicted_rate).toBeCloseTo(1.0 * (1 - t) + 1.2 * t, 10)
    expect(result.horizon_days).toBe(18)
    expect(result.source_lower_days).toBe(7)
    expect(result.source_upper_days).toBe(30)
  })

  it('exact horizon match returns that horizon unchanged', () => {
    const result = interpolatePrediction([p7, p30, p90], 30)
    expect(result.predicted_rate).toBe(p30.predicted_rate)
    expect(result.horizon_days).toBe(30)
    expect(result.source_lower_days).toBe(30)
    expect(result.source_upper_days).toBe(30)
  })

  it('below minimum snaps to shortest horizon', () => {
    const result = interpolatePrediction([p7, p30, p90], 3)
    expect(result.predicted_rate).toBe(p7.predicted_rate)
    expect(result.horizon_days).toBe(3)
    expect(result.source_lower_days).toBe(7)
    expect(result.source_upper_days).toBe(7)
  })

  it('above maximum snaps to longest horizon', () => {
    const result = interpolatePrediction([p7, p30, p90], 200)
    expect(result.predicted_rate).toBe(p90.predicted_rate)
    expect(result.horizon_days).toBe(200)
    expect(result.source_lower_days).toBe(90)
    expect(result.source_upper_days).toBe(90)
  })

  it('propagates low confidence if either bounding horizon is low', () => {
    const p7low = pred({ horizon_days: 7, confidence: 'low' })
    const result = interpolatePrediction([p7low, p30], 18)
    expect(result.confidence).toBe('low')
  })
})
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd frontend && npm test -- --run predictionMath
```

Expected: the five new tests FAIL with import/undefined errors.

- [ ] **Step 3: Add `InterpolatedPrediction` and `interpolatePrediction()` to `predictionMath.ts`**

At the end of `frontend/src/lib/predictionMath.ts`, append:

```typescript
export interface InterpolatedPrediction extends RawPrediction {
  source_lower_days: number
  source_upper_days: number
}

export function interpolatePrediction(
  predictions: RawPrediction[],
  targetDays: number,
): InterpolatedPrediction {
  if (predictions.length === 0) throw new Error('no predictions to interpolate from')
  const sorted = [...predictions].sort((a, b) => a.horizon_days - b.horizon_days)
  const min = sorted[0]
  const max = sorted[sorted.length - 1]

  if (targetDays <= min.horizon_days) {
    return { ...min, horizon_days: targetDays, source_lower_days: min.horizon_days, source_upper_days: min.horizon_days }
  }
  if (targetDays >= max.horizon_days) {
    return { ...max, horizon_days: targetDays, source_lower_days: max.horizon_days, source_upper_days: max.horizon_days }
  }

  const upperIndex = sorted.findIndex((p) => p.horizon_days > targetDays)
  const upper = sorted[upperIndex]
  const lower = sorted[upperIndex - 1]

  if (lower.horizon_days === targetDays) {
    return { ...lower, source_lower_days: lower.horizon_days, source_upper_days: lower.horizon_days }
  }

  const t = (targetDays - lower.horizon_days) / (upper.horizon_days - lower.horizon_days)
  return {
    horizon_days: targetDays,
    predicted_rate: lower.predicted_rate * (1 - t) + upper.predicted_rate * t,
    lower_bound: lower.lower_bound * (1 - t) + upper.lower_bound * t,
    upper_bound: lower.upper_bound * (1 - t) + upper.upper_bound * t,
    confidence: lower.confidence === 'low' || upper.confidence === 'low' ? 'low' : 'normal',
    generated_at:
      lower.generated_at < upper.generated_at ? lower.generated_at : upper.generated_at,
    source_lower_days: lower.horizon_days,
    source_upper_days: upper.horizon_days,
  }
}
```

- [ ] **Step 4: Run all frontend unit tests**

```bash
cd frontend && npm test -- --run
```

Expected: all tests (existing + five new) PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/predictionMath.ts frontend/src/lib/predictionMath.test.ts
git commit -m "feat: add interpolatePrediction() with linear interpolation between stored horizons"
```

---

## Task 7: `DatePredictionCard` + Dashboard wiring

**Files:**
- Create: `frontend/src/components/DatePredictionCard.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`

**Interfaces:**
- Consumes: `interpolatePrediction(predictions, targetDays): InterpolatedPrediction` from Task 6
- Produces: date picker UI on the dashboard between RecommendationCard and RateChart

- [ ] **Step 1: Create `DatePredictionCard.tsx`**

Create `frontend/src/components/DatePredictionCard.tsx`:

```tsx
import type { InterpolatedPrediction } from '../lib/predictionMath'

interface Props {
  prediction: InterpolatedPrediction
  pair: string
  targetDate: string
}

export function DatePredictionCard({ prediction, pair, targetDate }: Props) {
  const isLow = prediction.confidence === 'low'
  const isSameHorizon = prediction.source_lower_days === prediction.source_upper_days
  const sourceNote = isSameHorizon
    ? `Snapped to ${prediction.source_lower_days}-day forecast`
    : `Interpolated between ${prediction.source_lower_days}-day and ${prediction.source_upper_days}-day forecasts`

  return (
    <div
      className={`p-4 rounded-lg border ${
        isLow ? 'bg-yellow-50 border-yellow-200' : 'bg-blue-50 border-blue-200'
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-700">
          {pair} on {targetDate}
        </span>
        {isLow && (
          <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full font-medium">
            Low confidence
          </span>
        )}
      </div>
      <div className="text-2xl font-bold text-gray-900 mb-1">
        {prediction.predicted_rate.toFixed(4)}
      </div>
      <div className="text-sm text-gray-600">
        Range: {prediction.lower_bound.toFixed(4)} – {prediction.upper_bound.toFixed(4)}
      </div>
      <div className="text-xs text-gray-400 mt-2">{sourceNote}</div>
    </div>
  )
}
```

- [ ] **Step 2: Wire the date picker into `Dashboard.tsx`**

In `frontend/src/pages/Dashboard.tsx`, add these imports at the top:

```tsx
import { useState } from 'react'
import { interpolatePrediction, type InterpolatedPrediction } from '../lib/predictionMath'
import { DatePredictionCard } from '../components/DatePredictionCard'
```

Inside `Dashboard()`, add state after the existing hook calls:

```tsx
const [targetDate, setTargetDate] = useState('')
```

Compute the interpolated prediction (place this after the existing `const pair = ...` line):

```tsx
const todayStr = new Date().toISOString().split('T')[0]
const maxDateStr = (() => {
  const d = new Date()
  d.setDate(d.getDate() + 365)
  return d.toISOString().split('T')[0]
})()

const interpolated: InterpolatedPrediction | null = (() => {
  if (!targetDate || predictions.length === 0) return null
  const ms = new Date(targetDate).getTime() - Date.now()
  const targetDays = Math.max(1, Math.round(ms / 86400000))
  return interpolatePrediction(predictions, targetDays)
})()
```

In the JSX, between the `{recLoading ? ... : <RecommendationCard ... />}` block and the `{ratesLoading || predLoading ? ... : <RateChart ... />}` block, add:

```tsx
{/* Date prediction */}
{!predLoading && (
  <div className="bg-white rounded-lg shadow p-4 space-y-3">
    <p className="text-sm font-medium text-gray-700">Predict for a specific date</p>
    <div className="flex items-center gap-3">
      <input
        type="date"
        value={targetDate}
        min={(() => { const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().split('T')[0] })()}
        max={maxDateStr}
        onChange={(e) => setTargetDate(e.target.value)}
        className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      {targetDate && (
        <button
          onClick={() => setTargetDate('')}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Clear
        </button>
      )}
    </div>
    {interpolated && (
      <DatePredictionCard prediction={interpolated} pair={pair} targetDate={targetDate} />
    )}
  </div>
)}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Manually verify the date picker in the browser**

With `npm run dev` running, navigate to `/dashboard`, add EUR/USD, then:
1. Select a date 14 days from today in the date picker
2. Confirm a `DatePredictionCard` appears with a rate and "Interpolated between 7-day and 30-day forecasts" note
3. Select a date 5 days from today — card should snap to 7-day forecast with "Snapped to 7-day forecast"
4. Click "Clear" — card disappears

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DatePredictionCard.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat: add date picker with interpolated prediction card to dashboard"
```

---

## Task 8: Playwright E2E suite

**Files:**
- Modify: `frontend/package.json` — add `test:e2e` script
- Modify: `frontend/.gitignore` — add `e2e/.auth/`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/global-setup.ts`
- Create: `frontend/e2e/auth.spec.ts`
- Create: `frontend/e2e/dashboard.spec.ts`
- Create: `frontend/e2e/accuracy.spec.ts`
- Create: `frontend/.env.test` (gitignored — you fill in credentials)

**Interfaces:**
- Consumes: a real Supabase test user (create one in the Supabase dashboard before running)
- Produces: `npm run test:e2e` runs all three spec files against a local Vite dev server

- [ ] **Step 1: Install Playwright**

```bash
cd frontend && npm install --save-dev @playwright/test
npx playwright install chromium
```

- [ ] **Step 2: Create `frontend/.env.test`**

Create the file (it will be gitignored in Step 3):

```
VITE_TEST_EMAIL=your-test-user@example.com
VITE_TEST_PASSWORD=your-test-password
```

Replace the values with credentials for a Supabase test user you've already created.

- [ ] **Step 3: Update `.gitignore`**

In `frontend/.gitignore` (create if absent), add:

```
e2e/.auth/
.env.test
```

- [ ] **Step 4: Create `playwright.config.ts`**

Create `frontend/playwright.config.ts`:

```typescript
import * as fs from 'fs'
import * as path from 'path'
import { defineConfig, devices } from '@playwright/test'

// Load .env.test for local dev; CI sets env vars directly
const envFile = path.resolve(__dirname, '.env.test')
if (fs.existsSync(envFile)) {
  for (const line of fs.readFileSync(envFile, 'utf-8').split('\n')) {
    const eq = line.indexOf('=')
    if (eq === -1) continue
    const key = line.slice(0, eq).trim()
    const val = line.slice(eq + 1).trim()
    if (key && !process.env[key]) process.env[key] = val
  }
}

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: 'http://localhost:5173',
    storageState: 'e2e/.auth/user.json',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
  },
})
```

- [ ] **Step 5: Create `e2e/global-setup.ts`**

Create `frontend/e2e/global-setup.ts`:

```typescript
import * as fs from 'fs'
import * as path from 'path'
import { chromium, type FullConfig } from '@playwright/test'

export default async function globalSetup(_config: FullConfig) {
  const email = process.env.VITE_TEST_EMAIL
  const password = process.env.VITE_TEST_PASSWORD
  if (!email || !password) {
    throw new Error(
      'VITE_TEST_EMAIL and VITE_TEST_PASSWORD must be set in frontend/.env.test before running E2E tests',
    )
  }

  const browser = await chromium.launch()
  const page = await browser.newPage()

  await page.goto('http://localhost:5173/login')
  await page.fill('#email', email)
  await page.fill('#password', password)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/dashboard', { timeout: 15000 })

  const authDir = path.resolve(__dirname, '.auth')
  if (!fs.existsSync(authDir)) fs.mkdirSync(authDir, { recursive: true })
  await page.context().storageState({ path: path.join(authDir, 'user.json') })

  await browser.close()
}
```

- [ ] **Step 6: Create `e2e/auth.spec.ts`**

Create `frontend/e2e/auth.spec.ts`:

```typescript
import { test, expect } from '@playwright/test'

// Override the global storageState so these tests run unauthenticated
test.use({ storageState: { cookies: [], origins: [] } })

test('login page has email and password fields', async ({ page }) => {
  await page.goto('/login')
  await expect(page.locator('#email')).toBeVisible()
  await expect(page.locator('#password')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Log in' })).toBeVisible()
})

test('valid credentials redirect to dashboard', async ({ page }) => {
  await page.goto('/login')
  await page.fill('#email', process.env.VITE_TEST_EMAIL!)
  await page.fill('#password', process.env.VITE_TEST_PASSWORD!)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/dashboard', { timeout: 15000 })
  await expect(page).toHaveURL(/dashboard/)
})

test('unauthenticated /dashboard visit redirects to /login', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/login/)
})
```

- [ ] **Step 7: Create `e2e/dashboard.spec.ts`**

Create `frontend/e2e/dashboard.spec.ts`:

```typescript
import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/dashboard')
})

test('pair picker renders with Add button', async ({ page }) => {
  await expect(page.getByRole('button', { name: '+ Add' })).toBeVisible()
})

test('adding EUR/USD shows a recommendation card', async ({ page }) => {
  // USD is already the default base; set quote to EUR
  await page.selectOption('select:nth-of-type(2)', 'EUR')
  await page.click('button:has-text("+ Add")')
  // Wait for one of the four valid recommendation states
  await expect(
    page.getByText(/ACT NOW|WAIT|VOLATILE|NO SIGNAL/),
  ).toBeVisible({ timeout: 15000 })
})

test('rate chart canvas renders after pair is added', async ({ page }) => {
  await page.selectOption('select:nth-of-type(2)', 'EUR')
  await page.click('button:has-text("+ Add")')
  await expect(page.locator('canvas')).toBeVisible({ timeout: 15000 })
})

test('"Predict for a specific date" section is visible after pair is added', async ({ page }) => {
  await page.selectOption('select:nth-of-type(2)', 'EUR')
  await page.click('button:has-text("+ Add")')
  await expect(page.getByText('Predict for a specific date')).toBeVisible({ timeout: 15000 })
})

test('selecting a date 14 days from today shows interpolated prediction card', async ({ page }) => {
  await page.selectOption('select:nth-of-type(2)', 'EUR')
  await page.click('button:has-text("+ Add")')
  await page.getByText('Predict for a specific date').waitFor({ timeout: 15000 })

  const target = new Date()
  target.setDate(target.getDate() + 14)
  const dateStr = target.toISOString().split('T')[0]

  await page.fill('input[type="date"]', dateStr)
  // The card shows a 4-decimal rate value
  await expect(page.locator('text=/\\d+\\.\\d{4}/')).toBeVisible({ timeout: 10000 })
})
```

- [ ] **Step 8: Create `e2e/accuracy.spec.ts`**

Create `frontend/e2e/accuracy.spec.ts`:

```typescript
import { test, expect } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.goto('/accuracy')
})

test('accuracy page loads with heading', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Prediction Accuracy' })).toBeVisible()
})

test('summary strip is visible', async ({ page }) => {
  // Summary strip contains "of" and "pairs" — present whether data exists or not
  await expect(page.getByText(/\d+ of \d+ pairs|No backtest stats/)).toBeVisible({ timeout: 10000 })
})

test('horizon tabs 7d/30d/90d/365d all render', async ({ page }) => {
  for (const label of ['7d', '30d', '90d', '365d']) {
    await expect(page.getByRole('button', { name: label })).toBeVisible()
  }
})

test('clicking 30d tab activates it', async ({ page }) => {
  await page.getByRole('button', { name: '30d' }).click()
  const btn = page.getByRole('button', { name: '30d' })
  await expect(btn).toHaveClass(/bg-blue-600/)
})
```

- [ ] **Step 9: Add `test:e2e` script to `package.json`**

In `frontend/package.json`, inside `"scripts"`, add:

```json
"test:e2e": "playwright test"
```

- [ ] **Step 10: Run the E2E suite**

```bash
cd frontend && npm run test:e2e
```

Expected: all tests pass. The `webServer` block auto-starts `npm run dev`. `global-setup.ts` logs in once and saves storage state to `e2e/.auth/user.json`.

If `adding EUR/USD shows a recommendation card` times out: the test user may not have EUR/USD in their watchlist yet — the test adds it fresh via the picker, which triggers a Supabase insert and a prediction fetch. Increase the `timeout` on that assertion to 20000 if the Supabase round-trip is slow on first run.

- [ ] **Step 11: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e/ frontend/package.json frontend/.gitignore
git commit -m "test: add Playwright E2E suite (auth, dashboard, accuracy page)"
```

---

## Self-Review Checklist

- [x] Spec Section 1 (calibration extension): covered by Tasks 1 + 2
- [x] Spec Section 2 (accuracy frontend page): covered by Tasks 4 + 5
- [x] Spec Section 3 (backend calibration test): covered by Task 3
- [x] Spec Section 4 (date picker): covered by Tasks 6 + 7
- [x] Spec Section 5 (Playwright): covered by Task 8
- [x] DB migration included (Task 2, Step 1)
- [x] RLS check included (Task 4, Step 1)
- [x] `interpolatePrediction` return type is `InterpolatedPrediction` consistently across Tasks 6 and 7
- [x] `source_lower_days` / `source_upper_days` on snap paths: both set to the single snap horizon (not undefined)
- [x] `DatePredictionCard` isSameHorizon check handles snap case correctly
- [x] Playwright `auth.spec.ts` overrides `storageState` to `{ cookies: [], origins: [] }` for unauthenticated tests
- [x] No TBDs or placeholders in any step
