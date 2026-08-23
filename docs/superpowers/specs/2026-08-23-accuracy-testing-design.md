# ForexCast: Accuracy Validation & Date Picker Design

**Date:** 2026-08-23
**Status:** Approved

## 1. Goal

Prove the prediction model is trustworthy (accuracy validation + calibration test), surface that proof to users (accuracy page), let users query a specific date (date picker), and verify the full stack end-to-end (Playwright E2E suite).

## 2. Scope

Five changes, implemented in this order (accuracy before UX):

1. Extend `backtest.py`'s `summarize()` with four new accuracy metrics
2. New `/accuracy` frontend page reading those metrics from Supabase
3. Backend calibration test asserting structural correctness on EUR/USD fixture data
4. Date picker with linear interpolation between stored horizons
5. Playwright E2E test suite against a local dev server

## 3. Section 1 — Calibration Extension

### 3.1 `summarize()` additions (`backend/app/prediction/backtest.py`)

`summarize()` returns four new keys alongside existing ones:

| Key | Type | Meaning |
|-----|------|---------|
| `es_mae` | float | Mean absolute % error of exponential smoothing across all origins |
| `naive_mae` | float | Mean absolute % error of naive persistence across all origins |
| `mae_improvement_pct` | float | `(naive_mae - es_mae) / naive_mae × 100`. Positive = ES beat naive by that %. Negative = naive won by that %. Always uses ES vs naive, so the value is meaningful even when naive wins. |
| `calibration_coverage` | float | Fraction of origins where actual fell within `[predicted × (1 + error_lower_pct), predicted × (1 + error_upper_pct)]`. In-sample, expect ~0.80; significantly below 0.70 signals a bug. |

`mae_improvement_pct` always uses naive as the denominator so it's directly comparable across horizons and currencies — positive means beating the benchmark, negative means naive won.

`calibration_coverage` is computed from the **winning model's** residuals (same `residuals` list already computed before the `return` in `summarize()`), counting entries where `error_lower_pct <= residual <= error_upper_pct`.

### 3.2 `backtest_stats` schema change

Add four nullable float columns:
```sql
ALTER TABLE backtest_stats
  ADD COLUMN es_mae FLOAT,
  ADD COLUMN naive_mae FLOAT,
  ADD COLUMN mae_improvement_pct FLOAT,
  ADD COLUMN calibration_coverage FLOAT;
```

### 3.3 `upsert_backtest_stats` (`backend/app/prediction/supabase_rest.py`)

Pass the four new fields through to the upsert payload. No structural change to the function signature.

## 4. Section 2 — Accuracy Frontend Page

### 4.1 New files

| File | Purpose |
|------|---------|
| `frontend/src/lib/accuracyData.ts` | Supabase query: fetch all `backtest_stats` rows including new columns |
| `frontend/src/hooks/useAccuracyStats.ts` | Hook wrapping the query, groups rows by `horizon_days` |
| `frontend/src/pages/Accuracy.tsx` | Page component |

### 4.2 `accuracyData.ts`

Selects: `quote_code, horizon_days, model_selected, es_mae, naive_mae, mae_improvement_pct, calibration_coverage, sample_count`.

Requires `backtest_stats` RLS to allow authenticated reads (same pattern as `predictions` and `rates_cache`).

### 4.3 Page layout (`/accuracy`)

```
┌─────────────────────────────────────────────────────────┐
│  Summary strip                                          │
│  "X of Y pairs beat the naive baseline · avg calibra-  │
│   tion coverage: Z%"                                    │
├─────────────────────────────────────────────────────────┤
│  [ 7d ] [ 30d ] [ 90d ] [ 365d ]   ← horizon tabs      │
├────────┬──────────┬──────────┬──────────┬──────┬───────┤
│ Pair   │ Model    │ ES MAE%  │Naive MAE%│ Impr │ Calib │
│ USD/EUR│ ES       │ 0.82%    │ 0.91%    │+10.1%│ 79%   │
│ USD/GBP│ Naive    │ 1.12%    │ 0.98%    │ —    │ 81%   │
│ ...    │          │          │          │      │       │
└────────┴──────────┴──────────┴──────────┴──────┴───────┘
│  ⚠ Calibration coverage is in-sample (~80% expected).  │
│  MAE is mean absolute % error across backtest origins.  │
└─────────────────────────────────────────────────────────┘
```

Row color coding:
- Green background: `model_selected === 'exponential_smoothing'` (ES beat naive)
- Gray background: `model_selected === 'naive'` (naive won — honest, not an error)

"Impr" column: shows `+X%` when ES won, `—` when naive won (no negative to display — the model didn't claim to beat naive for that pair).

Summary strip counts: pairs where `model_selected === 'exponential_smoothing'` / total pairs for the active horizon tab.

### 4.4 Routing

- Add `<Route path="/accuracy" element={<ProtectedRoute><Accuracy /></ProtectedRoute>} />` to `App.tsx`
- Add "Accuracy" nav link to `Layout.tsx`

## 5. Section 3 — Backend Calibration Test

### 5.1 Fixture

`backend/tests/fixtures/eurusd_rates.json` — ~500 rows of daily USD/EUR rates (2+ years), fetched once from Frankfurter and committed. Format: `[{"date": "YYYY-MM-DD", "rate": 1.0842}, ...]`, oldest first.

A one-off helper script (`backend/scripts/fetch_fixture.py`) fetches and writes it. Not part of the test suite itself.

### 5.2 Test file: `backend/tests/test_accuracy_calibration.py`

Runs `run_backtest(rates, horizons=[7, 30, 90, 365])` then `summarize()` on each horizon's results. Asserts for **every** horizon:

1. `sample_count >= 10` — enough origins for stats to be meaningful
2. `error_lower_pct < 0 < error_upper_pct` — confidence band straddles zero (broken if both same sign)
3. `calibration_coverage >= 0.70` — at least 70% of actuals within the stated band
4. `es_mae > 0` and `naive_mae > 0` — MAE computed as a positive float
5. `model_selected in ("exponential_smoothing", "naive")` — no unexpected values

**Deliberately not asserted:** that exponential smoothing beats naive. ADR-0001 says the app uses whichever wins — asserting ES must win would violate that contract and break for pairs where naive genuinely is better.

### 5.3 CI

The test runs as part of `pytest backend/tests/` with no network calls (fixture is local). No env vars required.

## 6. Section 4 — Date Picker with Interpolation

### 6.1 `interpolatePrediction()` in `predictionMath.ts`

```typescript
function interpolatePrediction(
  predictions: RawPrediction[],
  targetDays: number
): RawPrediction
```

Behavior:
- Sort predictions by `horizon_days`
- `targetDays < min horizon` → snap to shortest horizon (no sub-7-day extrapolation)
- `targetDays > max horizon` → snap to longest horizon (no beyond-365 extrapolation)
- `targetDays` exactly matches a horizon → return that prediction directly
- Otherwise: find bounding horizons L and U, compute `t = (targetDays - L) / (U - L)`, linearly interpolate `predicted_rate`, `lower_bound`, `upper_bound`
- `confidence`: `'low'` if either bounding horizon is `'low'`, else `'normal'`
- `generated_at`: earlier of the two bounding horizons' timestamps
- `horizon_days`: set to `targetDays`

### 6.2 UI (`Dashboard.tsx`)

New state: `const [targetDate, setTargetDate] = useState<string>('')`

New section rendered between RecommendationCard and RateChart (only when a pair is selected):

```
┌─────────────────────────────────────────────────────────┐
│ Predict for a specific date                             │
│ [date input: min=tomorrow, max=today+365] [Clear]       │
│                                                         │
│ When a date is set:                                     │
│ ┌───────────────────────────────────────────────────┐  │
│ │ Predicted rate on {date}: 1.0923                  │  │
│ │ Range: 1.0712 – 1.1134                            │  │
│ │ Interpolated between 7-day and 30-day forecasts   │  │
│ │ (low confidence if either horizon is flagged)     │  │
│ └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 6.3 New component: `DatePredictionCard.tsx`

Props: `prediction: RawPrediction | null, pair: string, targetDate: string`

Shows: predicted rate (4dp), range (4dp), interpolation source note, low-confidence warning if applicable. Reuses the same visual style as RecommendationCard (border, padding, badge).

### 6.4 New tests in `predictionMath.test.ts`

- Midpoint between 7d and 30d: predicted_rate is the average of the two
- Exact horizon match returns that horizon unchanged (t=0 and t=1)
- Below-minimum snaps to shortest horizon
- Above-maximum snaps to longest horizon
- Low-confidence propagates if either bounding horizon is low

### 6.5 No backend changes

Uses predictions already fetched by `usePredictions`.

## 7. Section 5 — Playwright E2E Suite

### 7.1 Installation

`@playwright/test` added to `frontend/devDependencies`. Run `npx playwright install chromium`.

### 7.2 New files

| File | Purpose |
|------|---------|
| `frontend/playwright.config.ts` | Base URL, webServer block, single Chromium project |
| `frontend/e2e/global-setup.ts` | Login once, save storage state to `e2e/.auth/user.json` |
| `frontend/e2e/auth.spec.ts` | Auth flow tests |
| `frontend/e2e/dashboard.spec.ts` | Dashboard flow tests |
| `frontend/e2e/accuracy.spec.ts` | Accuracy page tests |

`e2e/.auth/` is gitignored.

### 7.3 Credentials

`frontend/.env.test` (gitignored):
```
VITE_TEST_EMAIL=...
VITE_TEST_PASSWORD=...
```
Read in `global-setup.ts` via `process.env`. Requires a dedicated test user already created in Supabase.

### 7.4 `playwright.config.ts`

```typescript
webServer: {
  command: 'npm run dev',
  url: 'http://localhost:5173',
  reuseExistingServer: !process.env.CI,
}
```

### 7.5 Test coverage

**`auth.spec.ts`**
- Login page renders (`/login` has email + password inputs)
- Valid credentials redirect to `/dashboard`
- Unauthenticated visit to `/dashboard` redirects to `/login`

**`dashboard.spec.ts`** (uses saved auth state)
- PairPicker renders
- Adding EUR/USD shows RecommendationCard with a valid label (ACT NOW / WAIT / VOLATILE / NO SIGNAL)
- RateChart canvas element is present
- "Predict for a specific date" section is visible
- Selecting a date 14 days from today shows the interpolated prediction card with a rate value

**`accuracy.spec.ts`** (uses saved auth state)
- `/accuracy` loads without error
- Summary strip is visible
- Clicking "30d" tab updates the visible rows
- Table contains at least one row

### 7.6 `package.json` addition

```json
"test:e2e": "playwright test"
```

### 7.7 Scope boundary

Playwright does not verify prediction math (Vitest) or backend calibration thresholds (pytest). It verifies: does the UI render, do flows complete, do the right elements appear.

## 8. Implementation Order

1. `backtest.py` + `summarize()` extension + schema migration + `upsert_backtest_stats`
2. Calibration test + fixture
3. Accuracy frontend page (lib + hook + component + routing)
4. `interpolatePrediction()` + unit tests
5. `DatePredictionCard` + Dashboard wiring
6. Playwright config + global setup + three spec files

## 9. Files Changed / Created

**Backend:**
- `backend/app/prediction/backtest.py` — `summarize()` extended
- `backend/app/prediction/supabase_rest.py` — new fields in upsert payload
- `backend/tests/test_accuracy_calibration.py` — new
- `backend/tests/fixtures/eurusd_rates.json` — new
- `backend/scripts/fetch_fixture.py` — new (one-off, not in test suite)

**Frontend:**
- `frontend/src/lib/accuracyData.ts` — new
- `frontend/src/hooks/useAccuracyStats.ts` — new
- `frontend/src/pages/Accuracy.tsx` — new
- `frontend/src/lib/predictionMath.ts` — `interpolatePrediction()` added
- `frontend/src/lib/predictionMath.test.ts` — new test cases
- `frontend/src/components/DatePredictionCard.tsx` — new
- `frontend/src/pages/Dashboard.tsx` — date picker state + `DatePredictionCard` wiring
- `frontend/src/App.tsx` — `/accuracy` route
- `frontend/src/components/Layout.tsx` — "Accuracy" nav link
- `frontend/playwright.config.ts` — new
- `frontend/e2e/global-setup.ts` — new
- `frontend/e2e/auth.spec.ts` — new
- `frontend/e2e/dashboard.spec.ts` — new
- `frontend/e2e/accuracy.spec.ts` — new

**Database:**
- Migration: add four columns to `backtest_stats`
