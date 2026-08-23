# Forecast Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two production bugs (planner loading, recommendation empty state), wire LLM news sentiment into recommendations with explainable reasoning, add horizon quick-pick buttons to the date picker, and add a holdout accuracy pytest gate.

**Architecture:** Bug fixes are isolated to their respective hooks and pages. LLM integration is additive: a new FastAPI endpoint `/recommendations/{base}/{quote}/insights` returns sentiment; the frontend hook `useRecommendationInsights` calls it alongside the existing Supabase recommendation read. Horizon buttons are pure UI. Holdout gate runs `run_backtest` + `summarize` against the committed EUR/USD fixture.

**Tech Stack:** FastAPI (backend), React + Vitest (frontend), pytest (backend tests), Supabase PostgREST (existing data layer), GDELT + `score_sentiment()` (news sentiment).

**Spec:** `docs/superpowers/specs/2026-08-24-forecast-enhancements-design.md`

## Global Constraints

- Never log or return a raw LLM API key in any response body, log line, or error message.
- Sentiment modifier only fires when statistical result is `no_signal` AND `|score| > 0.4` — the statistical model is never overridden otherwise.
- `is_llm_configured()` checks `(settings.llm_api_key and settings.llm_provider) or settings.openrouter_api_key` — same priority order as `score_sentiment()`.
- Auth pattern: `user_id: str = Depends(get_current_user)` from `app.auth`.
- All pytest tests must pass with `pytest backend/tests/ -q`; all Vitest tests must pass with `npm run test` inside `frontend/`.
- Commit after every task.

---

### Task 1: Fix Planner infinite-loading + error banner

**Files:**
- Modify: `frontend/src/hooks/useAchievements.ts`
- Modify: `frontend/src/pages/Planner.tsx`
- Test: `frontend/src/hooks/useAchievements.test.ts` (new)

**Interfaces:**
- Consumes: nothing new
- Produces: `useAchievements()` now always resolves `loading` to `false`; `useDebts()` and `useSavingsGoals()` already resolve correctly

**Root cause:** `useAchievements.fetchData()` calls `Promise.all([supabase..., supabase..., getBadges().catch(...)])`. If either Supabase call throws an uncaught exception (e.g. network timeout that bypasses Supabase's own error envelope), `setLoading(false)` is never reached and Planner spins forever. Also `Planner.tsx` never renders errors from the three hooks.

- [ ] **Step 1: Write the failing test (simulate a thrown Supabase error)**

Create `frontend/src/hooks/useAchievements.test.ts`:

```typescript
import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAchievements } from './useAchievements'

vi.mock('../lib/supabaseClient', () => ({
  supabase: {
    from: () => ({
      select: () => ({
        order: () => ({ error: null, data: [] }),
        maybeSingle: () => ({ error: null, data: null }),
      }),
    }),
  },
}))

vi.mock('../lib/apiClient', () => ({
  getBadges: vi.fn().mockRejectedValue(new Error('network error')),
  checkinStreak: vi.fn(),
}))

describe('useAchievements', () => {
  it('resolves loading=false even when getBadges throws', async () => {
    const { result } = renderHook(() => useAchievements())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
  })
})
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd frontend && npx vitest run src/hooks/useAchievements.test.ts
```

Expected: test times out or `loading` never becomes `false`.

- [ ] **Step 3: Wrap fetchData in try/finally**

In `frontend/src/hooks/useAchievements.ts`, change `fetchData`:

```typescript
const fetchData = useCallback(async () => {
  try {
    const [achievementsResult, streaksResult, badgesResult] = await Promise.all([
      supabase.from('achievements').select('*').order('earned_at', { ascending: false }),
      supabase.from('streaks').select('*').maybeSingle(),
      getBadges().catch((err: Error) => {
        setError(err.message)
        return {} as Record<string, Badge>
      }),
    ])

    if (achievementsResult.error) {
      setError(achievementsResult.error.message)
    } else {
      setAchievements(achievementsResult.data ?? [])
    }
    if (streaksResult.error) {
      setError(streaksResult.error.message)
    } else {
      setStreaks(
        streaksResult.data ?? {
          daily_checkin_current: 0, daily_checkin_best: 0, daily_checkin_last: null,
          savings_current: 0, savings_best: 0, savings_last: null,
          debt_payment_current: 0, debt_payment_best: 0, debt_payment_last: null,
        },
      )
    }
    setBadges(badgesResult)
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Failed to load achievements')
  } finally {
    setLoading(false)
  }
}, [])
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/hooks/useAchievements.test.ts
```

Expected: PASS

- [ ] **Step 5: Add error banner to Planner.tsx**

In `frontend/src/pages/Planner.tsx`, change the destructuring lines to:

```tsx
const { debts, loading: debtsLoading, error: debtsError } = useDebts()
const { goals, loading: goalsLoading, error: goalsError } = useSavingsGoals()
const { achievements, streaks, badges, loading: achievementsLoading, error: achievementsError, recordCheckin } = useAchievements()
```

Add a combined error variable after those three lines:

```tsx
const plannerError = debtsError || goalsError || achievementsError
```

Then inside the returned JSX, immediately after `<Layout>` and before the loading check, add:

```tsx
{plannerError && (
  <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
    Could not load planner data — {plannerError}
  </div>
)}
```

- [ ] **Step 6: Run all frontend tests**

```bash
cd frontend && npm run test
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useAchievements.ts frontend/src/hooks/useAchievements.test.ts frontend/src/pages/Planner.tsx
git commit -m "fix: planner always resolves loading; add error banner"
```

---

### Task 2: Fix recommendation empty-state copy

**Files:**
- Modify: `frontend/src/components/RecommendationCard.tsx`
- Test: `frontend/src/components/RecommendationCard.test.tsx` (new)

**Interfaces:**
- Consumes: `rec: Recommendation | null`, `pair: string` (unchanged)
- Produces: better null-state copy; prop signature unchanged

**Root cause:** When `rec` is null (cross-pair with no predictions yet, or job hasn't run), the card shows "No recommendation available for {pair}" with no guidance. Users don't know why or what to do.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/RecommendationCard.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { RecommendationCard } from './RecommendationCard'

describe('RecommendationCard', () => {
  it('shows actionable empty state when rec is null', () => {
    render(<RecommendationCard rec={null} pair="EUR/SGD" />)
    expect(screen.getByText(/no forecast data yet/i)).toBeInTheDocument()
    expect(screen.getByText(/weekly/i)).toBeInTheDocument()
  })

  it('renders recommendation badge for act_now', () => {
    const rec = {
      recommendation: 'act_now' as const,
      current_rate: 1.45, expected_rate: 1.40,
      lower_bound: 1.38, upper_bound: 1.42,
      reference_horizon_days: 30,
      generated_at: '2026-08-24T00:00:00Z',
    }
    render(<RecommendationCard rec={rec} pair="EUR/SGD" />)
    expect(screen.getByText('ACT NOW')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify the first test fails**

```bash
cd frontend && npx vitest run src/components/RecommendationCard.test.tsx
```

Expected: "no forecast data yet" text not found.

- [ ] **Step 3: Update the null branch in RecommendationCard**

In `frontend/src/components/RecommendationCard.tsx`, replace the `if (!rec)` block:

```tsx
if (!rec) {
  return (
    <div className="p-4 bg-white rounded-lg shadow text-center space-y-1">
      <p className="text-gray-500 font-medium">No forecast data yet for {pair}</p>
      <p className="text-gray-400 text-sm">
        The weekly backtest job populates predictions — check back after the next scheduled run.
      </p>
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/RecommendationCard.test.tsx
```

Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RecommendationCard.tsx frontend/src/components/RecommendationCard.test.tsx
git commit -m "fix: actionable empty state when no forecast data for pair"
```

---

### Task 3: LLM insights backend endpoint

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/recommendations/router.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_recommendations_insights.py`

**Interfaces:**
- Consumes: `get_settings()`, `get_current_user`, `score_sentiment()`, `fetch_articles()`, `COUNTRY_NAMES`
- Produces: `GET /recommendations/{base}/{quote}/insights` → `{"requires_llm_setup": bool, "sentiment": {"score": float, "summary": str} | null}`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_recommendations_insights.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
AUTH_HEADER = {"Authorization": "Bearer test-token"}


def mock_auth(_header=None):
    return "user-123"


@pytest.fixture(autouse=True)
def patch_auth():
    with patch("app.recommendations.router.get_current_user", mock_auth):
        yield


def test_insights_returns_requires_llm_setup_when_not_configured():
    with patch("app.recommendations.router.is_llm_configured", return_value=False):
        resp = client.get("/recommendations/EUR/USD/insights", headers=AUTH_HEADER)
    assert resp.status_code == 200
    body = resp.json()
    assert body["requires_llm_setup"] is True
    assert body["sentiment"] is None


def test_insights_returns_sentiment_when_configured():
    with (
        patch("app.recommendations.router.is_llm_configured", return_value=True),
        patch("app.recommendations.router.fetch_articles", return_value=[{"title": "Euro strengthens"}]),
        patch("app.recommendations.router.score_sentiment", return_value={"score": 0.6, "summary": "Positive outlook"}),
    ):
        resp = client.get("/recommendations/EUR/USD/insights", headers=AUTH_HEADER)
    assert resp.status_code == 200
    body = resp.json()
    assert body["requires_llm_setup"] is False
    assert body["sentiment"]["score"] == pytest.approx(0.6)
    assert "Positive" in body["sentiment"]["summary"]


def test_insights_returns_null_sentiment_when_articles_empty():
    with (
        patch("app.recommendations.router.is_llm_configured", return_value=True),
        patch("app.recommendations.router.fetch_articles", return_value=[]),
        patch("app.recommendations.router.score_sentiment") as mock_score,
    ):
        resp = client.get("/recommendations/USD/EUR/insights", headers=AUTH_HEADER)
    assert resp.status_code == 200
    mock_score.assert_not_called()
    assert resp.json()["sentiment"] is None
```

- [ ] **Step 2: Run to verify tests fail**

```bash
cd backend && python -m pytest tests/test_recommendations_insights.py -v
```

Expected: ImportError or 404 (router not mounted yet).

- [ ] **Step 3: Add `is_llm_configured()` to config.py**

In `backend/app/config.py`, add after the `get_settings` function:

```python
def is_llm_configured() -> bool:
    """Returns True if any LLM provider is configured — either a direct
    provider key+name pair, or the openrouter fallback key."""
    s = get_settings()
    return bool((s.llm_api_key and s.llm_provider) or s.openrouter_api_key)
```

- [ ] **Step 4: Create `backend/app/recommendations/router.py`**

```python
from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.config import is_llm_configured
from app.news.country_map import COUNTRY_NAMES
from app.news.gdelt_client import fetch_articles
from app.news.llm_client import score_sentiment

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

MIN_ARTICLES = 3


@router.get("/{base}/{quote}/insights")
def get_insights(
    base: str,
    quote: str,
    _user_id: str = Depends(get_current_user),
) -> dict:
    """Returns LLM sentiment for a currency pair.

    Scores the non-USD leg (or quote when neither is USD). Returns
    requires_llm_setup=True when no LLM key is configured so the
    frontend can surface a setup prompt without making a failed call.
    """
    if not is_llm_configured():
        return {"requires_llm_setup": True, "sentiment": None}

    # Pick the currency to score: prefer the non-USD leg; fall back to quote.
    target = quote if base == "USD" else base
    country = COUNTRY_NAMES.get(target)
    if country is None:
        return {"requires_llm_setup": False, "sentiment": None}

    articles = fetch_articles(country)
    if len(articles) < MIN_ARTICLES:
        return {"requires_llm_setup": False, "sentiment": None}

    result = score_sentiment(articles, country)
    return {"requires_llm_setup": False, "sentiment": result}
```

- [ ] **Step 5: Mount the router in main.py**

In `backend/app/main.py`, add:

```python
from app.recommendations.router import router as recommendations_router
```

And add after the existing `app.include_router(planner_router)` line:

```python
app.include_router(recommendations_router)
```

- [ ] **Step 6: Run the tests**

```bash
cd backend && python -m pytest tests/test_recommendations_insights.py -v
```

Expected: all 3 pass.

- [ ] **Step 7: Run full backend test suite**

```bash
cd backend && python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/config.py backend/app/recommendations/router.py backend/app/main.py backend/tests/test_recommendations_insights.py
git commit -m "feat: add /recommendations/{base}/{quote}/insights LLM sentiment endpoint"
```

---

### Task 4: Frontend insights hook + updated RecommendationCard + Dashboard wiring

**Files:**
- Modify: `frontend/src/lib/apiClient.ts`
- Create: `frontend/src/hooks/useRecommendationInsights.ts`
- Modify: `frontend/src/components/RecommendationCard.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Test: `frontend/src/hooks/useRecommendationInsights.test.ts` (new)

**Interfaces:**
- Consumes: `GET /recommendations/{base}/{quote}/insights` from Task 3; `Recommendation` type from `useRecommendations`
- Produces:
  - `fetchRecommendationInsights(base, quote): Promise<RecommendationInsights>`
  - `useRecommendationInsights(base, quote): { insights, loading, error }`
  - `RecommendationInsights: { requires_llm_setup: boolean; sentiment: { score: number; summary: string } | null }`
  - `RecommendationCard` gains optional prop `insights?: RecommendationInsights`

- [ ] **Step 1: Add `fetchRecommendationInsights` to apiClient.ts**

In `frontend/src/lib/apiClient.ts`, append:

```typescript
export interface RecommendationInsights {
  requires_llm_setup: boolean
  sentiment: { score: number; summary: string } | null
}

export async function fetchRecommendationInsights(base: string, quote: string): Promise<RecommendationInsights> {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')

  const res = await fetch(`${API_BASE_URL}/recommendations/${base}/${quote}/insights`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}
```

- [ ] **Step 2: Create `useRecommendationInsights.ts`**

```typescript
import { useEffect, useState } from 'react'
import { fetchRecommendationInsights, type RecommendationInsights } from '../lib/apiClient'

export function useRecommendationInsights(base: string, quote: string) {
  const [insights, setInsights] = useState<RecommendationInsights | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!base || !quote) return
    let cancelled = false
    setLoading(true)
    setError(null)

    fetchRecommendationInsights(base, quote)
      .then((data) => { if (!cancelled) { setInsights(data); setLoading(false) } })
      .catch((err) => { if (!cancelled) { setError(err instanceof Error ? err.message : String(err)); setLoading(false) } })

    return () => { cancelled = true }
  }, [base, quote])

  return { insights, loading, error }
}
```

- [ ] **Step 3: Write tests for the hook**

Create `frontend/src/hooks/useRecommendationInsights.test.ts`:

```typescript
import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { useRecommendationInsights } from './useRecommendationInsights'
import * as apiClient from '../lib/apiClient'

describe('useRecommendationInsights', () => {
  it('fetches insights and sets them', async () => {
    vi.spyOn(apiClient, 'fetchRecommendationInsights').mockResolvedValue({
      requires_llm_setup: false,
      sentiment: { score: 0.5, summary: 'Positive outlook' },
    })
    const { result } = renderHook(() => useRecommendationInsights('EUR', 'USD'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.insights?.sentiment?.score).toBe(0.5)
  })

  it('sets requires_llm_setup when key missing', async () => {
    vi.spyOn(apiClient, 'fetchRecommendationInsights').mockResolvedValue({
      requires_llm_setup: true,
      sentiment: null,
    })
    const { result } = renderHook(() => useRecommendationInsights('EUR', 'USD'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.insights?.requires_llm_setup).toBe(true)
  })
})
```

- [ ] **Step 4: Run hook tests**

```bash
cd frontend && npx vitest run src/hooks/useRecommendationInsights.test.ts
```

Expected: both pass.

- [ ] **Step 5: Update RecommendationCard to accept and display insights**

In `frontend/src/components/RecommendationCard.tsx`, update the `Props` interface and component:

```tsx
import type { Recommendation } from '../hooks/useRecommendations'
import type { RecommendationInsights } from '../lib/apiClient'

// ... STYLES unchanged ...

interface Props {
  rec: Recommendation | null
  pair: string
  insights?: RecommendationInsights | null
}

export function RecommendationCard({ rec, pair, insights }: Props) {
  // Sentiment modifier: flip no_signal when sentiment is strong
  const effectiveRec = (() => {
    if (!rec || rec.recommendation !== 'no_signal') return rec
    const score = insights?.sentiment?.score
    if (score === undefined || score === null) return rec
    if (score < -0.4) return { ...rec, recommendation: 'act_now' as const }
    if (score > 0.4) return { ...rec, recommendation: 'wait' as const }
    return rec
  })()

  if (!effectiveRec) {
    return (
      <div className="p-4 bg-white rounded-lg shadow text-center space-y-1">
        <p className="text-gray-500 font-medium">No forecast data yet for {pair}</p>
        <p className="text-gray-400 text-sm">
          The weekly backtest job populates predictions — check back after the next scheduled run.
        </p>
      </div>
    )
  }

  const style = STYLES[effectiveRec.recommendation]

  // Compose reasoning string from rec + sentiment
  const direction = effectiveRec.recommendation === 'wait' ? 'higher' : 'lower or flat'
  const sentimentLine = insights?.sentiment
    ? ` News sentiment: ${insights.sentiment.score >= 0 ? 'positive' : 'negative'} (${insights.sentiment.score.toFixed(2)}) — ${insights.sentiment.summary}`
    : ''
  const reasoning = `The ${effectiveRec.reference_horizon_days}-day forecast predicts ${effectiveRec.expected_rate.toFixed(4)} (${direction} from current ${effectiveRec.current_rate.toFixed(4)}).${sentimentLine}`

  return (
    <div className={`p-4 rounded-lg border ${style.bg}`}>
      {insights?.requires_llm_setup && (
        <div className="mb-3 text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded px-3 py-2">
          Add an LLM key in Settings to unlock news-aware recommendations. (Note: not dismissible in V1 — add localStorage dismiss state as a follow-up if desired.)
        </div>
      )}
      <div className="flex items-center justify-between mb-3">
        <span className="font-semibold text-lg">{pair}</span>
        <span className={`px-3 py-1 rounded-full text-sm font-bold ${style.badge}`}>
          {style.emoji} {style.label}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-gray-500">Current:</span>{' '}
          <span className="font-medium">{effectiveRec.current_rate.toFixed(4)}</span>
        </div>
        <div>
          <span className="text-gray-500">Expected ({effectiveRec.reference_horizon_days}d):</span>{' '}
          <span className="font-medium">{effectiveRec.expected_rate.toFixed(4)}</span>
        </div>
        <div>
          <span className="text-gray-500">Range:</span>{' '}
          <span className="font-medium">{effectiveRec.lower_bound.toFixed(4)} – {effectiveRec.upper_bound.toFixed(4)}</span>
        </div>
        <div>
          <span className="text-gray-500">Updated:</span>{' '}
          <span className="font-medium">{new Date(effectiveRec.generated_at).toLocaleDateString()}</span>
        </div>
      </div>
      {effectiveRec.recommendation === 'no_signal' && (
        <p className="text-xs text-gray-500 mt-3">
          The backtested model has no directional edge for this pair right now — the range above is
          the honest historical spread, not a forecasted move.
        </p>
      )}
      <p className="text-xs text-gray-500 mt-3 italic">{reasoning}</p>
    </div>
  )
}
```

- [ ] **Step 6: Wire useRecommendationInsights into Dashboard.tsx**

In `frontend/src/pages/Dashboard.tsx`, add the import at the top:

```tsx
import { useRecommendationInsights } from '../hooks/useRecommendationInsights'
```

Add the hook call inside the component (near the other hooks):

```tsx
const { insights } = useRecommendationInsights(base, quote)
```

Update the `<RecommendationCard>` usage to pass insights:

```tsx
<RecommendationCard rec={rec} pair={pair} insights={insights} />
```

- [ ] **Step 7: Run all frontend tests**

```bash
cd frontend && npm run test
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/apiClient.ts frontend/src/hooks/useRecommendationInsights.ts frontend/src/hooks/useRecommendationInsights.test.ts frontend/src/components/RecommendationCard.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat: LLM news sentiment insights on dashboard recommendation card"
```

---

### Task 5: Horizon quick-pick buttons in Dashboard

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Interfaces:**
- Consumes: `setTargetDate` (existing state setter in Dashboard), `maxDateStr` (existing)
- Produces: 4 quick-pick buttons (7d / 30d / 90d / 365d) that fill the date input

- [ ] **Step 1: Add helper to compute date string N days from today**

In `frontend/src/pages/Dashboard.tsx`, the `maxDateStr` IIFE already shows the pattern. Add `daysFromToday` as a local helper inside the component (just above the return statement):

```tsx
function daysFromToday(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return d.toISOString().split('T')[0]
}
```

- [ ] **Step 2: Insert quick-pick buttons before the date input**

In the "Date prediction" section of `Dashboard.tsx`, before the `<div className="flex items-center gap-3">` that holds the date input, add:

```tsx
<div className="flex gap-2">
  {([7, 30, 90, 365] as const).map((n) => (
    <button
      key={n}
      onClick={() => setTargetDate(daysFromToday(n))}
      className="px-3 py-1 text-xs font-medium rounded-full border border-gray-300 text-gray-600 hover:border-blue-400 hover:text-blue-600 transition-colors"
    >
      {n}d
    </button>
  ))}
</div>
```

- [ ] **Step 3: Update disclaimer copy**

In `Dashboard.tsx`, find the existing disclaimer `<p>` inside the date prediction block and replace its text content with:

```tsx
<p className="text-xs text-gray-400">
  Forecasts are statistical estimates. Dates between stored horizons (7 / 30 / 90 / 365 days) are linearly interpolated — accuracy degrades for dates far from a stored anchor.
</p>
```

- [ ] **Step 4: Run all frontend tests**

```bash
cd frontend && npm run test
```

Expected: all pass (no tests touch the quick-pick buttons directly — visual regression belongs in E2E).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: horizon quick-pick buttons (7d/30d/90d/365d) in date prediction card"
```

---

### Task 6: Holdout accuracy eval script + pytest gate

**Files:**
- Create: `backend/scripts/eval_holdout.py`
- Create: `backend/tests/test_holdout_accuracy.py`

**Interfaces:**
- Consumes: `run_backtest(rates, horizons)` from `app.prediction.backtest`; `summarize(samples)` from `app.prediction.backtest`; `backend/tests/fixtures/eurusd_rates.json` (existing)
- Produces: printed table in eval script; `mae_improvement_pct > 0` pytest assertion per horizon

- [ ] **Step 1: Write the pytest gate first**

Create `backend/tests/test_holdout_accuracy.py`:

```python
"""Out-of-sample accuracy gate.

Loads the committed EUR/USD fixture (oldest to newest), runs the full
rolling-origin backtest, and asserts that ES beats the naive baseline
on the complete window. The fixture spans 2023-01-01 to present, so
origins in 2023-2024 are evaluated against 2024-2025 actuals -- a
genuine out-of-sample check. A failure means the model's edge has
vanished and must be investigated before the next release.
"""
import json
from pathlib import Path

import pytest

from app.prediction.backtest import run_backtest, summarize

FIXTURE = Path(__file__).parent / "fixtures" / "eurusd_rates.json"
HORIZONS = [7, 30, 90, 365]


def _load_rates() -> list[float]:
    rows = json.loads(FIXTURE.read_text())
    return [r["rate"] for r in rows]


@pytest.mark.parametrize("horizon", HORIZONS)
def test_es_beats_naive_on_eurusd_holdout(horizon: int):
    rates = _load_rates()
    results = run_backtest(rates, [horizon])
    assert horizon in results, f"No backtest results for horizon={horizon}"
    summary = summarize(results[horizon])
    improvement = summary.get("mae_improvement_pct")
    assert improvement is not None, "mae_improvement_pct is None — not enough data"
    assert improvement > 0, (
        f"ES does NOT beat naive for EUR/USD {horizon}d: "
        f"es_mae={summary['es_mae']:.4f} naive_mae={summary['naive_mae']:.4f} "
        f"improvement={improvement:.2f}%"
    )
```

- [ ] **Step 2: Run to verify status (may pass or fail — record result)**

```bash
cd backend && python -m pytest tests/test_holdout_accuracy.py -v
```

Expected: PASS or FAIL depending on the model's actual edge. If any horizon fails, record which ones before implementing the eval script.

- [ ] **Step 3: Create `backend/scripts/eval_holdout.py`**

```python
#!/usr/bin/env python3
"""Holdout accuracy evaluator.

Loads EUR/USD rate history from Supabase (or the committed fixture as
fallback), splits at CUTOFF_DATE, runs the backtest on all data, and
prints a table of ES vs naive MAE for each horizon.

Usage (requires SUPABASE_URL + SUPABASE_SERVICE_KEY in environment):
    python backend/scripts/eval_holdout.py

For CI or local testing without DB access, the fixture at
backend/tests/fixtures/eurusd_rates.json is used automatically.
"""
import json
import os
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.prediction.backtest import run_backtest, summarize

CUTOFF_DATE = "2024-12-31"
HORIZONS = [7, 30, 90, 365]
FIXTURE = Path(__file__).parent.parent / "tests" / "fixtures" / "eurusd_rates.json"


def _load_from_supabase() -> list[dict]:
    """Fetches EUR/USD rate history from Supabase rates_cache."""
    import httpx

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    resp = httpx.get(
        f"{url}/rest/v1/rates_cache",
        params={
            "select": "as_of,rate",
            "base_code": "eq.USD",
            "quote_code": "eq.EUR",
            "order": "as_of.asc",
        },
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return [{"date": r["as_of"][:10], "rate": r["rate"]} for r in resp.json()]


def _load_rates() -> list[dict]:
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"):
        print("Loading EUR/USD from Supabase...")
        return _load_from_supabase()
    print(f"SUPABASE_URL not set — using committed fixture at {FIXTURE}")
    return json.loads(FIXTURE.read_text())


def main():
    rows = _load_rates()
    rates = [r["rate"] for r in rows]
    dates = [r["date"] for r in rows]

    cutoff_idx = max(
        (i for i, d in enumerate(dates) if d <= CUTOFF_DATE),
        default=-1,
    )
    if cutoff_idx < 0:
        print(f"No data on or before {CUTOFF_DATE}. Cannot split.")
        sys.exit(1)

    print(f"\nData range: {dates[0]} to {dates[-1]} ({len(rates)} rows)")
    print(f"Cutoff: {CUTOFF_DATE} (index {cutoff_idx} of {len(rates)-1})")
    print(f"Training rows: {cutoff_idx+1}, Test rows: {len(rates)-cutoff_idx-1}\n")

    results = run_backtest(rates, HORIZONS)

    header = f"{'Pair':<12}{'Horizon':>9}{'ES MAE':>10}{'Naive MAE':>12}{'Improvement':>14}{'Model':>10}"
    print(header)
    print("-" * len(header))

    for h in HORIZONS:
        if h not in results:
            print(f"  EUR/USD  {h:>6}d  — not enough data —")
            continue
        s = summarize(results[h])
        es = s["es_mae"]
        naive = s["naive_mae"]
        imp = s["mae_improvement_pct"]
        model = s["model_selected"]
        imp_str = f"+{imp:.1f}%" if imp and imp > 0 else (f"{imp:.1f}%" if imp else "N/A")
        print(f"  EUR/USD  {h:>6}d  {es*100:>8.3f}%  {naive*100:>10.3f}%  {imp_str:>12}  {model:>10}")

    print()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify the script runs against the fixture**

```bash
cd backend && python scripts/eval_holdout.py
```

Expected: prints a table with 4 horizon rows and no errors.

- [ ] **Step 5: Run full backend test suite**

```bash
cd backend && python -m pytest tests/ -q
```

Expected: all pass (the new test is included).

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_holdout_accuracy.py backend/scripts/eval_holdout.py
git commit -m "feat: holdout accuracy eval script + pytest gate (mae_improvement_pct>0)"
```

