# Forecast Enhancements Design — 2026-08-24

## Overview

This spec covers four interrelated improvements to ForexCast, selected as **Approach 1 (minimal-additive)** from the 2026-08-24 architectural brainstorm:

1. Fix two production bugs (planner infinite-loading, recommendation missing for cross-pairs)
2. Wire LLM news sentiment into recommendations and surface an explainable rationale
3. Extend the existing horizon/date-picker UI with a quick-pick horizon chooser
4. Add a holdout accuracy gate that proves ES beats the naive baseline on out-of-sample 2025 data

Nothing in this spec restructures the prediction engine or adds new storage beyond what is noted. Deferred work is listed explicitly in Section 5.

---

## Section 1 — Bug Fixes

### 1.1 Planner infinite-loading

**Root cause:** `useSavingsGoals`, `useDebts`, and `useAchievements` have no error or empty-array branch — they remain in the loading state when the underlying Supabase query returns zero rows or an error.

**Fix:**
- Add explicit `error` and empty-array resolution to all three hooks so they always settle.
- Add a `catch` path that stores an error string; the Planner page renders a descriptive banner ("Could not load planner data — check your connection") instead of spinning forever.
- No schema changes, no new tables.

### 1.2 Recommendation missing (`No recommendation available for EUR/SGD`)

**Root cause (likely):** `backtest_stats` has no row for cross-pairs because `run_backtest_job` loops over USD-pivot currencies only. `usePredictions` returns an empty array for EUR/SGD, and `chooseRecommendation` throws. The current UI silently renders null.

**Fix:**
- UI: render a "No forecast data yet" empty-state card when `predictions` is empty, instead of silently showing nothing.
- Data pipeline: confirm whether `run_backtest_job` needs a separate pass for cross-pairs, or whether the frontend's `deriveCrossPredictions` path covers the gap at read-time. This is a one-time diagnostic; new code only if the pipeline is genuinely missing a pass.

---

## Section 2 — LLM News Integration & Explainable Recommendations

### 2.1 LLM key enforcement

The backend recommendation endpoint checks for a configured LLM key using a new `is_llm_configured()` helper (`backend/app/config.py`). Priority order:

1. Per-user `api_key_encrypted` from `llm_settings` (decrypted at request time)
2. `OPENROUTER_API_KEY` environment variable (service-level fallback)

If neither is present, the endpoint returns `requires_llm_setup: true` in the recommendation response. The frontend renders a dismissible banner: *"Add an LLM key in Settings to unlock news-aware recommendations."* Statistical recommendations still display; only the news and reasoning sections are hidden.

The raw API key is never logged. Encryption via `sealBox` / `VITE_LLM_SETTINGS_PUBLIC_KEY` is unchanged.

### 2.2 Sentiment as a secondary modifier

`score_sentiment(headlines) → {score: -1..1, summary: str}` is already implemented in `backend/app/news/llm_client.py`. The score is now passed into the recommendation engine as a secondary signal — the statistical model (`chooseRecommendation`) remains authoritative (consistent with ADR-0001):

- If the statistical result is `no_signal` and `|sentiment_score| > 0.4`, flip to `act_now` (score < 0) or `wait` (score > 0) per the sentiment sign.
- In all other cases, sentiment annotates but does not override.

This rule is simple, traceable, and testable without additional model infrastructure.

### 2.3 Explainable recommendations

The recommendation API response (`/api/recommendations/{base}/{quote}`) gains a `reasoning: string | null` field. When an LLM key is configured, the backend makes one cheap LLM call per recommendation request with a structured prompt (model output, horizon, sentiment summary → 2–3 sentence rationale in English). Example:

> "The 90-day ES model predicts EUR/SGD at 1.4612 (+1.2% from current). Recent news sentiment is mildly bearish (−0.31). Recommendation: wait — the statistical signal outweighs the news sentiment."

The `reasoning` string is displayed below the recommendation badge on the dashboard card. If `reasoning` is null (no key configured, or LLM call failed), the card renders exactly as it does today. The LLM call is made per recommendation request with no caching in V1 — do not add a cache layer unless traffic warrants it.

---

## Section 3 — Horizon Chooser & Date Picker

### 3.1 What already exists

`interpolatePrediction()`, `DatePredictionCard`, and the free-form date input are already wired into `Dashboard.tsx` (accuracy-testing feature, 2026-08-23). No new data layer or backend changes.

### 3.2 Additions

**Quick-pick horizon buttons** — a row of four buttons (7d / 30d / 90d / 365d) above the date input. Clicking one fills the date field to today + N days and immediately renders `DatePredictionCard`. Since these match stored forecast horizons, no interpolation is required and the result is maximally accurate.

**Free-form date input** — unchanged. Selecting any other date triggers interpolation as before.

**Card label copy:**
- Exact horizon: *"Snapped to 90d forecast"*
- Interpolated: *"Interpolated between 30d and 90d"* (already shown via `source_lower_days` / `source_upper_days`)

**Disclaimer** — replaces the existing generic disclaimer:

> *"Forecasts are statistical estimates. Dates that fall between stored horizons (7 / 30 / 90 / 365 days) are linearly interpolated — accuracy degrades for dates far from a stored anchor."*

---

## Section 4 — Holdout Accuracy Gating

### 4.1 Script: `backend/scripts/eval_holdout.py`

Fetches EUR/USD rate history (and optionally other pairs) from Supabase, splits at **2024-12-31**:
- Training window: all data up to and including 2024-12-31
- Test window: 2025-01-01 to present

For each of the four horizons (7 / 30 / 90 / 365), runs `run_backtest()` restricted to origins in the training window, then scores ES vs naive MAE against the holdout period. Outputs a table:

```
pair     horizon  es_mae   naive_mae  improvement_pct
EUR/USD  7        0.0041   0.0053     +22.6%
EUR/USD  30       0.0089   0.0104     +14.4%
...
```

Can be run manually with `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` set. Requires no new tables.

### 4.2 Pytest gate: `backend/tests/test_holdout_accuracy.py`

Parametrized over four horizons using the committed EUR/USD fixture (`backend/tests/fixtures/eurusd_rates.json`) — no DB dependency in CI.

**Single assertion per case:** `mae_improvement_pct > 0` — ES must beat naive on the holdout window.

EUR/USD at all four horizons is the canary. A failure means the model's edge against the naive baseline has vanished on out-of-sample data and must be investigated before the next release.

**Relation to existing tests:** `test_accuracy_calibration.py` is in-sample (uses all data). This test is strictly out-of-sample (splits at 2024-12-31). They coexist without overlap.

---

## Section 5 — Deferred Work

The following items were discussed and deliberately excluded from this spec. They must be addressed in future specs before their corresponding features can be built.

### 5.1 With-news vs without-news ablation (Approach 2)

Run the holdout eval twice — once with LLM sentiment enabled, once without — and post the improvement delta to `/accuracy`. This provides hard evidence of whether news actually improves `mae_improvement_pct` over stats-alone. Not in scope here because the news integration (Section 2) must be shipped and validated first.

### 5.2 Live LLM test wizard in Settings (Approach 2)

A "Test key" button in `SettingsPage` that fires a cheap test prompt at the configured provider/model and shows pass/fail before the user saves. Excluded because the hard-fail banner (Section 2.1) covers the critical UX gap for now.

### 5.3 Pluggable engine refactor (Approach 3)

A `Predictor.predict(rates, macro, news_score)` interface with composable, tunable mix weights across statistical, macro, and news signals. The right time to build this is after the holdout (Section 4) and ablation (5.1 above) prove that news materially improves MAE vs stats-alone. Building it now is premature.

### 5.4 Whole-app loophole / quality audit

A systematic audit covering RLS gaps on all tables, `rates_cache` edge cases, cross-pair recommendation pipeline integrity, planner hook error paths, and un-gated API endpoints. Too broad to fold into this spec. Scope as a standalone future task.

---

## Testing Summary

| Area | Test type | Location |
|------|-----------|----------|
| Planner hooks error/empty | Unit (Vitest) | `frontend/src/hooks/` |
| Recommendation empty-state | Component (Vitest) | `frontend/src/components/` |
| `is_llm_configured()` | Unit (pytest) | `backend/tests/` |
| Sentiment modifier rule | Unit (pytest) | `backend/tests/` |
| `reasoning` field present when key set | Integration (pytest) | `backend/tests/` |
| Horizon quick-pick fills date correctly | Component (Vitest) | `frontend/src/pages/` |
| Holdout `mae_improvement_pct > 0` | Parametrized pytest | `backend/tests/test_holdout_accuracy.py` |

---

## Files Touched (estimated)

**Backend**
- `backend/app/config.py` — `is_llm_configured()`
- `backend/app/recommendations/engine.py` — sentiment modifier
- `backend/app/recommendations/router.py` — `reasoning` field, `requires_llm_setup` flag
- `backend/scripts/eval_holdout.py` — new
- `backend/tests/test_holdout_accuracy.py` — new

**Frontend**
- `frontend/src/hooks/useDebts.ts`, `useSavingsGoals.ts`, `useAchievements.ts` — error/empty branches
- `frontend/src/pages/Planner.tsx` — error banner
- `frontend/src/pages/Dashboard.tsx` — horizon quick-pick buttons, disclaimer copy
- `frontend/src/components/RecommendationCard.tsx` — `reasoning` display, `requires_llm_setup` banner, empty-state card

**No schema changes required.** All new columns (`reasoning`, `requires_llm_setup`) are API response fields only.
