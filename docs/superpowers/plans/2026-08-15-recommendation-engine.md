# Recommendation Engine & Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the raw forecasts in `predictions` into an actionable ACT NOW / WAIT / VOLATILE signal for both directions of every currency pair (58 total), and evaluate manually-configured `alerts` against live data.

**Architecture:** A new `backend/app/recommendations/` package: pure-computation modules (`engine.py` for the recommendation algorithm and USD-reciprocal direction math, `alerts.py` for threshold/change detection), a Supabase I/O layer, daily orchestration, and a CLI — wired to a new GitHub Actions workflow that runs recommendations first, then alert evaluation (alert evaluation depends on that day's fresh recommendations for the `recommendation_change` alert type). All core logic verified against real execution while writing this plan.

**Tech Stack:** Same backend (Python 3.12, `httpx`, pytest). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-15-recommendation-engine-design.md`

## Global Constraints

- Every code task starts with a failing test before implementation (TDD).
- No live network calls in the automated test suite — all `httpx` calls are mocked. Live verification happens only in Task 10's manual steps.
- Covers both directions per currency (58 directed pairs) — USD→X (favorable = high rate) and X→USD (favorable = low rate, computed as the plain reciprocal of the USD→X figures).
- One recommendation per directed pair per day, synthesized across all 4 horizons via a "reference horizon" (whichever horizon predicts the most favorable rate) — never 4 separate per-horizon recommendations.
- `threshold` alerts are one-shot (deactivate on fire); `recommendation_change` alerts are repeating (never deactivated by firing).
- No notification dispatch and no new FastAPI routes in this task (both explicitly deferred — see spec §2).
- GitHub Actions secrets `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are already configured on this repo — no new secrets needed.
- Workflow YAML: all dynamic values flow through `env:` blocks, never interpolated directly into a `run:` shell body.

---

### Task 1: `recommendations` and `alert_events` migration

**Files:**
- Create: `supabase/migrations/0004_recommendations_and_alerts.sql`

**Interfaces:**
- Produces: `public.recommendations` and `public.alert_events` tables — consumed by later tasks' Supabase I/O.

- [ ] **Step 1: Write `supabase/migrations/0004_recommendations_and_alerts.sql`**

```sql
-- One computed recommendation per directed pair per day. Append-only,
-- like predictions -- detecting a recommendation_change alert requires
-- comparing today's row against the prior one, so history has to exist.
create table public.recommendations (
    id bigserial primary key,
    base_code text not null references public.currencies (code),
    quote_code text not null references public.currencies (code),
    recommendation text not null check (recommendation in ('act_now', 'wait', 'volatile')),
    reference_horizon_days integer not null,
    current_rate numeric not null,
    expected_rate numeric not null,
    lower_bound numeric not null,
    upper_bound numeric not null,
    generated_at timestamptz not null default now()
);

alter table public.recommendations enable row level security;
create policy "recommendations_public_read" on public.recommendations
    for select using (true);

-- Firing history for alerts -- separate from alerts itself (user-managed
-- config) since recommendation_change alerts can fire many times and
-- threshold alerts fire once; both need a record item 5 can later read
-- to know what to notify about.
create table public.alert_events (
    id bigserial primary key,
    alert_id uuid not null references public.alerts (id) on delete cascade,
    fired_at timestamptz not null default now(),
    details jsonb
);

alter table public.alert_events enable row level security;
create policy "alert_events_owner_select" on public.alert_events
    for select using (
        exists (
            select 1 from public.alerts
            where alerts.id = alert_events.alert_id
            and alerts.user_id = auth.uid()
        )
    );
```

- [ ] **Step 2: Apply the migration to the live Supabase project**

If `mcp__supabase__apply_migration` and `mcp__supabase__execute_sql` aren't already loaded: `ToolSearch(query="select:mcp__supabase__apply_migration,mcp__supabase__execute_sql")`.

`mcp__supabase__apply_migration(name="0004_recommendations_and_alerts", query=<the SQL from Step 1>)`
Expected: `{"success": true}`.

- [ ] **Step 3: Verify**

`mcp__supabase__execute_sql(query="select count(*) from public.recommendations")` → expect `0`.
`mcp__supabase__execute_sql(query="select count(*) from public.alert_events")` → expect `0`.
`mcp__supabase__execute_sql(query="select relrowsecurity from pg_class where relname in ('recommendations','alert_events')")` → expect both `true`.
`mcp__supabase__execute_sql(query="select tablename, count(*) from pg_policies where tablename in ('recommendations','alert_events') group by tablename")` → expect 1 policy each.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/0004_recommendations_and_alerts.sql
git commit -m "feat(db): add recommendations and alert_events tables"
```

---

### Task 2: Recommendation algorithm and direction math

**Files:**
- Create: `backend/app/recommendations/__init__.py` (empty)
- Create: `backend/app/recommendations/engine.py`
- Test: `backend/tests/test_recommendation_engine.py`

**Interfaces:**
- Produces: `invert_prediction(predicted_rate: float, lower_bound: float, upper_bound: float) -> dict` (returns `{"predicted_rate", "lower_bound", "upper_bound"}`) and `choose_recommendation(current_rate: float, horizons: list[dict], favorable_high: bool) -> dict` (returns `{"recommendation", "reference_horizon_days", "current_rate", "expected_rate", "lower_bound", "upper_bound"}`) in `app.recommendations.engine`. Both consumed by Task 6 (`jobs.py`).

- [ ] **Step 1: Create the empty package marker**

Create `backend/app/recommendations/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing test**

`backend/tests/test_recommendation_engine.py`:

```python
import pytest

from app.recommendations.engine import choose_recommendation, invert_prediction


def test_invert_prediction_flips_bound_order():
    result = invert_prediction(0.9, 0.85, 0.95)
    assert result["predicted_rate"] == pytest.approx(1 / 0.9)
    assert result["lower_bound"] == pytest.approx(1 / 0.95)
    assert result["upper_bound"] == pytest.approx(1 / 0.85)
    assert result["lower_bound"] < result["predicted_rate"] < result["upper_bound"]


def test_invert_prediction_round_trips():
    inverted = invert_prediction(0.9, 0.85, 0.95)
    back = invert_prediction(inverted["predicted_rate"], inverted["lower_bound"], inverted["upper_bound"])
    assert back["predicted_rate"] == pytest.approx(0.9)
    assert back["lower_bound"] == pytest.approx(0.85)
    assert back["upper_bound"] == pytest.approx(0.95)


HORIZONS = [
    {"horizon_days": 7, "predicted_rate": 90, "lower_bound": 88, "upper_bound": 92, "confidence": "normal"},
    {"horizon_days": 30, "predicted_rate": 95, "lower_bound": 91, "upper_bound": 99, "confidence": "normal"},
    {"horizon_days": 90, "predicted_rate": 93, "lower_bound": 85, "upper_bound": 101, "confidence": "normal"},
    {"horizon_days": 365, "predicted_rate": 100, "lower_bound": 80, "upper_bound": 120, "confidence": "normal"},
]


def test_choose_recommendation_waits_for_better_future_rate():
    result = choose_recommendation(85, HORIZONS, favorable_high=True)
    assert result["recommendation"] == "wait"
    assert result["reference_horizon_days"] == 365
    assert result["expected_rate"] == 100


def test_choose_recommendation_act_now_when_current_already_best():
    result = choose_recommendation(101, HORIZONS, favorable_high=True)
    assert result["recommendation"] == "act_now"


def test_choose_recommendation_volatile_when_reference_horizon_low_confidence():
    horizons = [dict(h) for h in HORIZONS]
    horizons[3] = {**horizons[3], "confidence": "low"}
    result = choose_recommendation(85, horizons, favorable_high=True)
    assert result["recommendation"] == "volatile"


HORIZONS_INVERTED = [
    {"horizon_days": 7, "predicted_rate": 0.011, "lower_bound": 0.0108, "upper_bound": 0.0113, "confidence": "normal"},
    {"horizon_days": 30, "predicted_rate": 0.0105, "lower_bound": 0.0101, "upper_bound": 0.011, "confidence": "normal"},
]


def test_choose_recommendation_favorable_low_direction_waits():
    result = choose_recommendation(0.012, HORIZONS_INVERTED, favorable_high=False)
    assert result["recommendation"] == "wait"
    assert result["reference_horizon_days"] == 30


def test_choose_recommendation_favorable_low_direction_act_now():
    result = choose_recommendation(0.0104, HORIZONS_INVERTED, favorable_high=False)
    assert result["recommendation"] == "act_now"


def test_choose_recommendation_raises_on_empty_horizons():
    with pytest.raises(ValueError):
        choose_recommendation(1.0, [], favorable_high=True)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest backend/tests/test_recommendation_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.recommendations.engine'`.

- [ ] **Step 4: Implement `backend/app/recommendations/engine.py`**

```python
def invert_prediction(predicted_rate: float, lower_bound: float, upper_bound: float) -> dict:
    """Inverts a USD->X prediction into the X->USD direction. Reciprocal
    is a decreasing function for positive numbers, so bound order flips:
    the new lower bound comes from the old upper bound, and vice versa.
    """
    return {
        "predicted_rate": 1 / predicted_rate,
        "lower_bound": 1 / upper_bound,
        "upper_bound": 1 / lower_bound,
    }


def choose_recommendation(current_rate: float, horizons: list[dict], favorable_high: bool) -> dict:
    """Given one direction's current rate and its horizon predictions
    (already in that direction's own value-space -- inverted beforehand
    via invert_prediction if this is the X->USD direction), picks the
    reference horizon (whichever predicts the most favorable rate) and
    decides act_now/wait/volatile.

    `horizons` is a list of dicts, each with horizon_days, predicted_rate,
    lower_bound, upper_bound, confidence.
    """
    if not horizons:
        raise ValueError("no horizons to choose from")

    if favorable_high:
        reference = max(horizons, key=lambda h: h["predicted_rate"])
    else:
        reference = min(horizons, key=lambda h: h["predicted_rate"])

    if reference["confidence"] == "low":
        recommendation = "volatile"
    elif favorable_high:
        recommendation = "act_now" if current_rate >= reference["predicted_rate"] else "wait"
    else:
        recommendation = "act_now" if current_rate <= reference["predicted_rate"] else "wait"

    return {
        "recommendation": recommendation,
        "reference_horizon_days": reference["horizon_days"],
        "current_rate": current_rate,
        "expected_rate": reference["predicted_rate"],
        "lower_bound": reference["lower_bound"],
        "upper_bound": reference["upper_bound"],
    }
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest backend/tests/test_recommendation_engine.py -v`
Expected: PASS (8 tests). This exact logic was run for real while writing this plan and produced exactly these results — if your run differs, investigate rather than adjusting the test.

- [ ] **Step 6: Commit**

```bash
git add backend/app/recommendations/__init__.py backend/app/recommendations/engine.py backend/tests/test_recommendation_engine.py
git commit -m "feat(backend): add recommendation algorithm and direction math"
```

---

### Task 3: Alert evaluation logic

**Files:**
- Create: `backend/app/recommendations/alerts.py`
- Test: `backend/tests/test_recommendation_alerts.py`

**Interfaces:**
- Produces: `threshold_crossed(current_rate: float, threshold_rate: float, direction: str) -> bool` and `recommendation_changed(latest: str, previous: str | None) -> bool` in `app.recommendations.alerts`. Both consumed by Task 7 (`jobs.py`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_recommendation_alerts.py`:

```python
import pytest

from app.recommendations.alerts import recommendation_changed, threshold_crossed


def test_threshold_crossed_above():
    assert threshold_crossed(86.0, 85.0, "above") is True
    assert threshold_crossed(84.0, 85.0, "above") is False


def test_threshold_crossed_below():
    assert threshold_crossed(84.0, 85.0, "below") is True
    assert threshold_crossed(86.0, 85.0, "below") is False


def test_threshold_crossed_raises_on_unknown_direction():
    with pytest.raises(ValueError):
        threshold_crossed(1.0, 2.0, "sideways")


def test_recommendation_changed_true_when_different():
    assert recommendation_changed("act_now", "wait") is True


def test_recommendation_changed_false_when_same():
    assert recommendation_changed("wait", "wait") is False


def test_recommendation_changed_false_when_no_previous():
    assert recommendation_changed("act_now", None) is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_recommendation_alerts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.recommendations.alerts'`.

- [ ] **Step 3: Implement `backend/app/recommendations/alerts.py`**

```python
def threshold_crossed(current_rate: float, threshold_rate: float, direction: str) -> bool:
    """direction is 'above' or 'below', matching alerts.direction's check
    constraint."""
    if direction == "above":
        return current_rate > threshold_rate
    if direction == "below":
        return current_rate < threshold_rate
    raise ValueError(f"unknown direction: {direction}")


def recommendation_changed(latest: str, previous: str | None) -> bool:
    """True if the two most recent recommendations for a pair differ. If
    there's no previous recommendation yet (fewer than 2 rows exist),
    there's nothing to compare against -- not a change.
    """
    if previous is None:
        return False
    return latest != previous
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_recommendation_alerts.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/recommendations/alerts.py backend/tests/test_recommendation_alerts.py
git commit -m "feat(backend): add alert evaluation logic"
```

---

### Task 4: Supabase I/O — recommendations

**Files:**
- Create: `backend/app/recommendations/supabase_rest.py`
- Test: `backend/tests/test_recommendations_supabase_rest.py`

**Interfaces:**
- Consumes: `get_settings()` from `app.config` (existing).
- Produces: `get_latest_predictions(quote_code: str) -> list[dict]`, `get_current_rate(quote_code: str) -> float | None`, `insert_recommendations(rows: list[dict]) -> None` in `app.recommendations.supabase_rest`. All consumed by Task 6 (`jobs.py`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_recommendations_supabase_rest.py`:

```python
from unittest.mock import MagicMock, patch

from app.recommendations.supabase_rest import (
    get_current_rate,
    get_latest_predictions,
    insert_recommendations,
)


def test_get_latest_predictions_fetches_latest_timestamp_then_matching_rows():
    latest_response = MagicMock()
    latest_response.json.return_value = [{"generated_at": "2026-08-15T18:00:00+00:00"}]
    latest_response.raise_for_status.return_value = None

    rows_response = MagicMock()
    rows_response.json.return_value = [
        {
            "horizon_days": 7,
            "predicted_rate": 90.0,
            "lower_bound": 88.0,
            "upper_bound": 92.0,
            "confidence": "normal",
        },
        {
            "horizon_days": 30,
            "predicted_rate": 95.0,
            "lower_bound": 91.0,
            "upper_bound": 99.0,
            "confidence": "normal",
        },
    ]
    rows_response.raise_for_status.return_value = None

    with patch(
        "app.recommendations.supabase_rest.httpx.get",
        side_effect=[latest_response, rows_response],
    ) as mock_get:
        result = get_latest_predictions("INR")

    assert len(result) == 2
    assert result[0]["horizon_days"] == 7
    assert result[0]["predicted_rate"] == 90.0
    assert mock_get.call_count == 2
    second_call_kwargs = mock_get.call_args_list[1].kwargs
    assert second_call_kwargs["params"]["generated_at"] == "eq.2026-08-15T18:00:00+00:00"


def test_get_latest_predictions_returns_empty_list_when_no_predictions_exist():
    latest_response = MagicMock()
    latest_response.json.return_value = []
    latest_response.raise_for_status.return_value = None

    with patch(
        "app.recommendations.supabase_rest.httpx.get", return_value=latest_response
    ) as mock_get:
        result = get_latest_predictions("INR")

    assert result == []
    mock_get.assert_called_once()


def test_get_current_rate_returns_latest_rate():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"rate": 95.44}]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.recommendations.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_current_rate("INR")

    assert result == 95.44
    args, kwargs = mock_get.call_args
    assert kwargs["params"] == {
        "select": "rate",
        "base_code": "eq.USD",
        "quote_code": "eq.INR",
        "order": "as_of.desc",
        "limit": 1,
    }


def test_get_current_rate_returns_none_when_not_found():
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None
    with patch("app.recommendations.supabase_rest.httpx.get", return_value=mock_response):
        result = get_current_rate("INR")

    assert result is None


def test_insert_recommendations_posts_batch():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {
            "base_code": "USD",
            "quote_code": "INR",
            "recommendation": "wait",
            "reference_horizon_days": 30,
            "current_rate": 95.0,
            "expected_rate": 97.0,
            "lower_bound": 94.0,
            "upper_bound": 100.0,
        }
    ]
    with patch(
        "app.recommendations.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        insert_recommendations(rows)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/recommendations"
    assert kwargs["json"] == rows
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_recommendations_supabase_rest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.recommendations.supabase_rest'`.

- [ ] **Step 3: Implement `backend/app/recommendations/supabase_rest.py`**

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


def get_latest_predictions(quote_code: str) -> list[dict]:
    """Returns the most recent forecast batch for (base_code='USD',
    quote_code=<quote_code>) -- up to 4 rows, one per horizon. Finds the
    exact latest generated_at first, then fetches only rows stamped with
    that exact value, so a currency with fewer than 4 horizons written
    today never gets padded out with a stale row from a previous day.
    """
    settings = get_settings()
    latest_response = httpx.get(
        f"{settings.supabase_url}/rest/v1/predictions",
        params={
            "select": "generated_at",
            "base_code": "eq.USD",
            "quote_code": f"eq.{quote_code}",
            "order": "generated_at.desc",
            "limit": 1,
        },
        headers=_headers(),
        timeout=30.0,
    )
    latest_response.raise_for_status()
    latest_rows = latest_response.json()
    if not latest_rows:
        return []
    latest_generated_at = latest_rows[0]["generated_at"]

    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/predictions",
        params={
            "select": "horizon_days,predicted_rate,lower_bound,upper_bound,confidence",
            "base_code": "eq.USD",
            "quote_code": f"eq.{quote_code}",
            "generated_at": f"eq.{latest_generated_at}",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return [
        {
            "horizon_days": row["horizon_days"],
            "predicted_rate": float(row["predicted_rate"]),
            "lower_bound": float(row["lower_bound"]),
            "upper_bound": float(row["upper_bound"]),
            "confidence": row["confidence"],
        }
        for row in rows
    ]


def get_current_rate(quote_code: str) -> float | None:
    """Returns the most recent USD-pivot rate for `quote_code` from
    rates_cache, or None if no rate exists yet.
    """
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/rates_cache",
        params={
            "select": "rate",
            "base_code": "eq.USD",
            "quote_code": f"eq.{quote_code}",
            "order": "as_of.desc",
            "limit": 1,
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return float(rows[0]["rate"]) if rows else None


def insert_recommendations(rows: list[dict]) -> None:
    """Appends a batch of recommendation rows. Plain insert, not upsert --
    recommendations has no unique constraint, matching predictions'
    append-only pattern (needed so recommendation_change alerts can
    compare today's row against the prior one).
    """
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/recommendations",
            headers=_headers(),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_recommendations_supabase_rest.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/recommendations/supabase_rest.py backend/tests/test_recommendations_supabase_rest.py
git commit -m "feat(backend): add recommendations Supabase I/O layer"
```

---

### Task 5: Supabase I/O — alerts (extends Task 4's file)

**Files:**
- Modify: `backend/app/recommendations/supabase_rest.py`
- Modify: `backend/tests/test_recommendations_supabase_rest.py`

**Interfaces:**
- Produces: `get_active_alerts() -> list[dict]`, `get_latest_two_recommendations(base_code: str, quote_code: str) -> list[str]`, `record_alert_event(alert_id: str, details: dict) -> None`, `deactivate_alert(alert_id: str) -> None` in `app.recommendations.supabase_rest`. All consumed by Task 7 (`jobs.py`).

- [ ] **Step 1: Add the failing tests**

Append to `backend/tests/test_recommendations_supabase_rest.py` (add these four names to the existing top-of-file import from `app.recommendations.supabase_rest`):

```python
def test_get_active_alerts_filters_by_is_active():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "id": "alert-1",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "threshold",
            "threshold_rate": 85.0,
            "direction": "above",
        }
    ]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.recommendations.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_active_alerts()

    assert len(result) == 1
    assert result[0]["id"] == "alert-1"
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["is_active"] == "eq.true"


def test_get_latest_two_recommendations_returns_values_newest_first():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"recommendation": "act_now"}, {"recommendation": "wait"}]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.recommendations.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_latest_two_recommendations("USD", "INR")

    assert result == ["act_now", "wait"]
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["limit"] == 2


def test_record_alert_event_posts_event():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.recommendations.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        record_alert_event("alert-1", {"reason": "threshold crossed"})

    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/alert_events"
    assert kwargs["json"] == [{"alert_id": "alert-1", "details": {"reason": "threshold crossed"}}]


def test_deactivate_alert_patches_is_active_false():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.recommendations.supabase_rest.httpx.patch", return_value=mock_response
    ) as mock_patch:
        deactivate_alert("alert-1")

    args, kwargs = mock_patch.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/alerts"
    assert kwargs["params"] == {"id": "eq.alert-1"}
    assert kwargs["json"] == {"is_active": False}
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest backend/tests/test_recommendations_supabase_rest.py -v`
Expected: FAIL with `ImportError` (the four new names don't exist in `app.recommendations.supabase_rest` yet).

- [ ] **Step 3: Append the four functions to `backend/app/recommendations/supabase_rest.py`**

```python
def get_active_alerts() -> list[dict]:
    """Returns all alerts with is_active=true."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/alerts",
        params={
            "select": "id,base_code,quote_code,alert_type,threshold_rate,direction",
            "is_active": "eq.true",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def get_latest_two_recommendations(base_code: str, quote_code: str) -> list[str]:
    """Returns up to the 2 most recent `recommendation` values for a
    directed pair, newest first -- used to detect a recommendation_change.
    """
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/recommendations",
        params={
            "select": "recommendation",
            "base_code": f"eq.{base_code}",
            "quote_code": f"eq.{quote_code}",
            "order": "generated_at.desc",
            "limit": 2,
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return [row["recommendation"] for row in response.json()]


def record_alert_event(alert_id: str, details: dict) -> None:
    settings = get_settings()
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/alert_events",
        headers=_headers(),
        json=[{"alert_id": alert_id, "details": details}],
        timeout=30.0,
    )
    response.raise_for_status()


def deactivate_alert(alert_id: str) -> None:
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/alerts",
        params={"id": f"eq.{alert_id}"},
        headers=_headers(),
        json={"is_active": False},
        timeout=30.0,
    )
    response.raise_for_status()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest backend/tests/test_recommendations_supabase_rest.py -v`
Expected: PASS (9 tests total).

- [ ] **Step 5: Commit**

```bash
git add backend/app/recommendations/supabase_rest.py backend/tests/test_recommendations_supabase_rest.py
git commit -m "feat(backend): add alerts Supabase I/O layer"
```

---

### Task 6: Daily recommendation orchestration

**Files:**
- Create: `backend/app/recommendations/jobs.py`
- Test: `backend/tests/test_recommendation_jobs.py`

**Interfaces:**
- Consumes: `get_active_currencies()` from `app.ingestion.supabase_rest` (existing). `choose_recommendation`, `invert_prediction` from `app.recommendations.engine` (Task 2). `get_latest_predictions`, `get_current_rate`, `insert_recommendations` from `app.recommendations.supabase_rest` (Task 4).
- Produces: `run_recommendations() -> int` in `app.recommendations.jobs`. Consumed by Task 8 (`cli.py`) and extended by Task 7.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_recommendation_jobs.py`:

```python
from unittest.mock import patch

from app.recommendations.jobs import run_recommendations

HORIZONS = [
    {"horizon_days": 7, "predicted_rate": 90.0, "lower_bound": 88.0, "upper_bound": 92.0, "confidence": "normal"},
    {"horizon_days": 30, "predicted_rate": 95.0, "lower_bound": 91.0, "upper_bound": 99.0, "confidence": "normal"},
]


def test_run_recommendations_writes_both_directions_per_currency():
    with patch(
        "app.recommendations.jobs.get_active_currencies", return_value=["USD", "INR"]
    ), patch(
        "app.recommendations.jobs.get_latest_predictions", return_value=HORIZONS
    ), patch(
        "app.recommendations.jobs.get_current_rate", return_value=85.0
    ), patch("app.recommendations.jobs.insert_recommendations") as mock_insert:
        count = run_recommendations()

    assert count == 2
    rows = mock_insert.call_args[0][0]
    forward = next(r for r in rows if r["base_code"] == "USD" and r["quote_code"] == "INR")
    reverse = next(r for r in rows if r["base_code"] == "INR" and r["quote_code"] == "USD")
    assert forward["recommendation"] == "wait"
    assert forward["reference_horizon_days"] == 30
    assert forward["current_rate"] == 85.0
    assert reverse["current_rate"] == 1 / 85.0
    assert reverse["expected_rate"] == 1 / 95.0


def test_run_recommendations_skips_currency_with_no_predictions():
    with patch(
        "app.recommendations.jobs.get_active_currencies", return_value=["USD", "INR"]
    ), patch(
        "app.recommendations.jobs.get_latest_predictions", return_value=[]
    ), patch(
        "app.recommendations.jobs.get_current_rate", return_value=85.0
    ), patch("app.recommendations.jobs.insert_recommendations") as mock_insert:
        count = run_recommendations()

    assert count == 0
    mock_insert.assert_called_once_with([])


def test_run_recommendations_skips_currency_with_no_current_rate():
    with patch(
        "app.recommendations.jobs.get_active_currencies", return_value=["USD", "INR"]
    ), patch(
        "app.recommendations.jobs.get_latest_predictions", return_value=HORIZONS
    ), patch(
        "app.recommendations.jobs.get_current_rate", return_value=None
    ), patch("app.recommendations.jobs.insert_recommendations") as mock_insert:
        count = run_recommendations()

    assert count == 0
    mock_insert.assert_called_once_with([])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_recommendation_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.recommendations.jobs'`.

- [ ] **Step 3: Implement `backend/app/recommendations/jobs.py`**

```python
from app.ingestion.supabase_rest import get_active_currencies
from app.recommendations.engine import choose_recommendation, invert_prediction
from app.recommendations.supabase_rest import (
    get_current_rate,
    get_latest_predictions,
    insert_recommendations,
)

PIVOT = "USD"


def _predictable_currencies() -> list[str]:
    return [code for code in get_active_currencies() if code != PIVOT]


def run_recommendations() -> int:
    """Daily job: for every USD-quoted currency, compute a recommendation
    for both directions (USD->X and X->USD) from that currency's latest
    forecast batch, and write them to `recommendations`. A currency with
    no forecast batch or no current rate yet is skipped for both
    directions.
    """
    rows = []
    for quote_code in _predictable_currencies():
        horizons = get_latest_predictions(quote_code)
        if not horizons:
            continue
        current_rate = get_current_rate(quote_code)
        if current_rate is None:
            continue

        forward = choose_recommendation(current_rate, horizons, favorable_high=True)
        rows.append(
            {
                "base_code": PIVOT,
                "quote_code": quote_code,
                "recommendation": forward["recommendation"],
                "reference_horizon_days": forward["reference_horizon_days"],
                "current_rate": forward["current_rate"],
                "expected_rate": forward["expected_rate"],
                "lower_bound": forward["lower_bound"],
                "upper_bound": forward["upper_bound"],
            }
        )

        inverted_horizons = [
            {**h, **invert_prediction(h["predicted_rate"], h["lower_bound"], h["upper_bound"])}
            for h in horizons
        ]
        reverse = choose_recommendation(1 / current_rate, inverted_horizons, favorable_high=False)
        rows.append(
            {
                "base_code": quote_code,
                "quote_code": PIVOT,
                "recommendation": reverse["recommendation"],
                "reference_horizon_days": reverse["reference_horizon_days"],
                "current_rate": reverse["current_rate"],
                "expected_rate": reverse["expected_rate"],
                "lower_bound": reverse["lower_bound"],
                "upper_bound": reverse["upper_bound"],
            }
        )

    insert_recommendations(rows)
    return len(rows)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_recommendation_jobs.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/recommendations/jobs.py backend/tests/test_recommendation_jobs.py
git commit -m "feat(backend): add daily recommendation orchestration"
```

---

### Task 7: Alert evaluation orchestration (extends Task 6's file)

**Files:**
- Modify: `backend/app/recommendations/jobs.py`
- Modify: `backend/tests/test_recommendation_jobs.py`

**Interfaces:**
- Consumes: `threshold_crossed`, `recommendation_changed` from `app.recommendations.alerts` (Task 3). `get_active_alerts`, `get_latest_two_recommendations`, `record_alert_event`, `deactivate_alert`, `get_current_rate` from `app.recommendations.supabase_rest` (Tasks 4-5).
- Produces: `run_alert_evaluation() -> int` in `app.recommendations.jobs`. Consumed by Task 8 (`cli.py`).

- [ ] **Step 1: Add the failing tests**

Append to `backend/tests/test_recommendation_jobs.py`, adding `import pytest` at the top of the file alongside the existing imports:

```python
import pytest

from app.recommendations.jobs import run_alert_evaluation


def test_run_alert_evaluation_fires_and_deactivates_threshold_alert():
    alerts = [
        {
            "id": "alert-1",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "threshold",
            "threshold_rate": 85.0,
            "direction": "above",
        }
    ]
    with patch("app.recommendations.jobs.get_active_alerts", return_value=alerts), patch(
        "app.recommendations.jobs.get_current_rate", return_value=86.0
    ), patch("app.recommendations.jobs.record_alert_event") as mock_record, patch(
        "app.recommendations.jobs.deactivate_alert"
    ) as mock_deactivate:
        count = run_alert_evaluation()

    assert count == 1
    mock_record.assert_called_once()
    mock_deactivate.assert_called_once_with("alert-1")


def test_run_alert_evaluation_does_not_fire_uncrossed_threshold():
    alerts = [
        {
            "id": "alert-1",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "threshold",
            "threshold_rate": 85.0,
            "direction": "above",
        }
    ]
    with patch("app.recommendations.jobs.get_active_alerts", return_value=alerts), patch(
        "app.recommendations.jobs.get_current_rate", return_value=80.0
    ), patch("app.recommendations.jobs.record_alert_event") as mock_record, patch(
        "app.recommendations.jobs.deactivate_alert"
    ) as mock_deactivate:
        count = run_alert_evaluation()

    assert count == 0
    mock_record.assert_not_called()
    mock_deactivate.assert_not_called()


def test_run_alert_evaluation_raises_when_alerts_currency_has_no_current_rate():
    # This app's currency universe is fixed and known (unlike a genuinely
    # expected gap, e.g. a new currency awaiting its first backtest) -- a
    # missing current rate for an alert's currency is unexpected and must
    # fail loudly, not be silently skipped.
    alerts = [
        {
            "id": "alert-1",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "threshold",
            "threshold_rate": 85.0,
            "direction": "above",
        }
    ]
    with patch("app.recommendations.jobs.get_active_alerts", return_value=alerts), patch(
        "app.recommendations.jobs.get_current_rate", return_value=None
    ):
        with pytest.raises(ValueError, match="INR"):
            run_alert_evaluation()


def test_run_alert_evaluation_fires_recommendation_change_without_deactivating():
    alerts = [
        {
            "id": "alert-2",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "recommendation_change",
            "threshold_rate": None,
            "direction": None,
        }
    ]
    with patch("app.recommendations.jobs.get_active_alerts", return_value=alerts), patch(
        "app.recommendations.jobs.get_latest_two_recommendations",
        return_value=["act_now", "wait"],
    ), patch("app.recommendations.jobs.record_alert_event") as mock_record, patch(
        "app.recommendations.jobs.deactivate_alert"
    ) as mock_deactivate:
        count = run_alert_evaluation()

    assert count == 1
    mock_record.assert_called_once()
    mock_deactivate.assert_not_called()


def test_run_alert_evaluation_skips_unchanged_recommendation():
    alerts = [
        {
            "id": "alert-2",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "recommendation_change",
            "threshold_rate": None,
            "direction": None,
        }
    ]
    with patch("app.recommendations.jobs.get_active_alerts", return_value=alerts), patch(
        "app.recommendations.jobs.get_latest_two_recommendations",
        return_value=["wait", "wait"],
    ), patch("app.recommendations.jobs.record_alert_event") as mock_record:
        count = run_alert_evaluation()

    assert count == 0
    mock_record.assert_not_called()
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest backend/tests/test_recommendation_jobs.py -v`
Expected: FAIL with `ImportError` (`run_alert_evaluation` doesn't exist yet).

- [ ] **Step 3: Append `run_alert_evaluation` to `backend/app/recommendations/jobs.py`, and add the new imports**

Add these names to the existing `from app.recommendations.supabase_rest import (...)` line at the top of the file:

```python
from app.recommendations.alerts import recommendation_changed, threshold_crossed
from app.recommendations.supabase_rest import (
    deactivate_alert,
    get_active_alerts,
    get_current_rate,
    get_latest_predictions,
    get_latest_two_recommendations,
    insert_recommendations,
    record_alert_event,
)
```

Then append:

```python
def run_alert_evaluation() -> int:
    """Evaluates every active alert and records a firing event for each
    one that triggers. threshold alerts deactivate on fire (one-shot);
    recommendation_change alerts stay active (repeating).
    """
    fired = 0
    for alert in get_active_alerts():
        if alert["alert_type"] == "threshold":
            current_rate = get_current_rate(alert["quote_code"])
            if current_rate is None:
                # Unlike a fresh currency awaiting its first backtest, this
                # app's 29-currency universe is fixed and known -- a missing
                # rate for an alert's currency is unexpected, not a normal
                # gap, so it fails loudly rather than being silently skipped.
                raise ValueError(
                    f"No current rate for {alert['quote_code']} (alert {alert['id']})"
                )
            if threshold_crossed(current_rate, float(alert["threshold_rate"]), alert["direction"]):
                record_alert_event(
                    alert["id"],
                    {
                        "alert_type": "threshold",
                        "current_rate": current_rate,
                        "threshold_rate": float(alert["threshold_rate"]),
                        "direction": alert["direction"],
                    },
                )
                deactivate_alert(alert["id"])
                fired += 1
        elif alert["alert_type"] == "recommendation_change":
            recent = get_latest_two_recommendations(alert["base_code"], alert["quote_code"])
            latest = recent[0] if recent else None
            previous = recent[1] if len(recent) > 1 else None
            if latest is not None and recommendation_changed(latest, previous):
                record_alert_event(
                    alert["id"],
                    {
                        "alert_type": "recommendation_change",
                        "latest": latest,
                        "previous": previous,
                    },
                )
                fired += 1
    return fired
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest backend/tests/test_recommendation_jobs.py -v`
Expected: PASS (8 tests total).

- [ ] **Step 5: Commit**

```bash
git add backend/app/recommendations/jobs.py backend/tests/test_recommendation_jobs.py
git commit -m "feat(backend): add alert evaluation orchestration"
```

---

### Task 8: CLI entrypoint

**Files:**
- Create: `backend/app/recommendations/cli.py`
- Test: `backend/tests/test_recommendation_cli.py`

**Interfaces:**
- Consumes: `run_recommendations() -> int`, `run_alert_evaluation() -> int` from `app.recommendations.jobs` (Tasks 6-7).
- Produces: `main(argv: list[str] | None = None) -> None` in `app.recommendations.cli`, runnable as `python -m app.recommendations.cli --mode recommendations` or `--mode alerts`. Consumed by Task 9's GitHub Actions workflow.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_recommendation_cli.py`:

```python
from unittest.mock import patch

from app.recommendations.cli import main


def test_recommendations_mode_calls_run_recommendations():
    with patch(
        "app.recommendations.cli.run_recommendations", return_value=58
    ) as mock_recs, patch("app.recommendations.cli.run_alert_evaluation") as mock_alerts:
        main(["--mode", "recommendations"])

    mock_recs.assert_called_once()
    mock_alerts.assert_not_called()


def test_alerts_mode_calls_run_alert_evaluation():
    with patch("app.recommendations.cli.run_recommendations") as mock_recs, patch(
        "app.recommendations.cli.run_alert_evaluation", return_value=2
    ) as mock_alerts:
        main(["--mode", "alerts"])

    mock_alerts.assert_called_once()
    mock_recs.assert_not_called()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_recommendation_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.recommendations.cli'`.

- [ ] **Step 3: Implement `backend/app/recommendations/cli.py`**

```python
import argparse

from app.recommendations.jobs import run_alert_evaluation, run_recommendations


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ForexCast recommendation engine")
    parser.add_argument("--mode", choices=["recommendations", "alerts"], required=True)
    args = parser.parse_args(argv)

    if args.mode == "recommendations":
        count = run_recommendations()
    else:
        count = run_alert_evaluation()

    print(f"Wrote {count} rows ({args.mode})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_recommendation_cli.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full backend suite to confirm nothing broke**

Run: `pytest backend/tests -v`
Expected: PASS (all tests — everything from the three prior plans plus this plan's new tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/recommendations/cli.py backend/tests/test_recommendation_cli.py
git commit -m "feat(backend): add recommendation engine CLI entrypoint"
```

---

### Task 9: GitHub Actions scheduled workflow

**Files:**
- Create: `.github/workflows/recommend.yml`

**Interfaces:**
- Consumes: `backend/requirements.txt` (existing), `python -m app.recommendations.cli` (Task 8).
- Produces: none consumed by later tasks — leaf task.

- [ ] **Step 1: Create `.github/workflows/recommend.yml`**

```yaml
name: Generate recommendations

on:
  schedule:
    # Daily, after the prediction engine's forecast cron (18:00 UTC) so
    # today's predictions already exist.
    - cron: '0 19 * * *'
  workflow_dispatch:
    inputs:
      mode:
        description: 'Mode: "both" (default, matches the daily schedule) or force just one'
        required: true
        default: 'both'
        type: choice
        options:
          - both
          - recommendations
          - alerts

jobs:
  recommend:
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
      - name: Run recommendation job(s)
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
          MODE: ${{ github.event.inputs.mode || 'both' }}
        run: |
          if [ "$MODE" = "both" ]; then
            python -m app.recommendations.cli --mode recommendations
            python -m app.recommendations.cli --mode alerts
          else
            python -m app.recommendations.cli --mode "$MODE"
          fi
```

`recommendations` always runs before `alerts` when `mode=both` (the daily schedule's effective behavior) — `recommendation_change` alerts need that day's fresh recommendation already written to detect a change against. All dynamic values flow through `env:`, never interpolated directly into the `run:` body.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/recommend.yml
git commit -m "ci: add scheduled GitHub Actions workflow for recommendations"
```

---

### Task 10: Live verification

No new GitHub Actions secrets are needed — `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are already configured.

- [ ] **Step 1: Trigger a manual run with mode=both**

On GitHub: repo → Actions → "Generate recommendations" → Run workflow → mode = `both` → Run workflow. Wait for a green checkmark.

- [ ] **Step 2: Verify `recommendations` populated**

If `mcp__supabase__execute_sql` isn't already loaded: `ToolSearch(query="select:mcp__supabase__execute_sql")`.

`mcp__supabase__execute_sql(query="select count(*) as rows, count(distinct quote_code) as quote_currencies from public.recommendations")`
Expected: up to 58 rows (29 currencies × 2 directions — could be fewer if any currency had no prediction batch yet).

`mcp__supabase__execute_sql(query="select base_code, quote_code, recommendation, reference_horizon_days, current_rate, expected_rate, lower_bound, upper_bound from public.recommendations order by generated_at desc limit 6")`
Expected: 6 rows with sane numbers — `lower_bound <= expected_rate <= upper_bound` (or the reverse ordering for the X→USD rows, since bounds are direction-relative — just confirm the three numbers are in a sensible range together, not wildly inconsistent), and each pair should appear with both a `(USD, X)` and an `(X, USD)` row.

- [ ] **Step 3: Create a real test alert and verify it fires**

Get a real user id to satisfy `alerts.user_id`'s foreign key: `mcp__supabase__execute_sql(query="select id from auth.users limit 1")`.

Get the current USD→INR rate to pick a threshold that will definitely be crossed: `mcp__supabase__execute_sql(query="select rate from public.rates_cache where base_code='USD' and quote_code='INR' order by as_of desc limit 1")`.

Insert a threshold alert set just below that current rate, direction `'above'` (guaranteed to be crossed):

`mcp__supabase__execute_sql(query="insert into public.alerts (user_id, base_code, quote_code, alert_type, threshold_rate, direction, is_active) values ('<the user id from above>', 'USD', 'INR', 'threshold', <current rate minus 1>, 'above', true) returning id")`

Also insert a `recommendation_change` alert for the same pair, to confirm it evaluates without error on its first-ever run (it won't fire yet — no prior recommendation exists to compare against on day one, which is correct behavior, not a bug):

`mcp__supabase__execute_sql(query="insert into public.alerts (user_id, base_code, quote_code, alert_type, is_active) values ('<the user id from above>', 'USD', 'INR', 'recommendation_change', true) returning id")`

- [ ] **Step 4: Trigger a manual run with mode=alerts**

On GitHub: repo → Actions → "Generate recommendations" → Run workflow → mode = `alerts` → Run workflow. Wait for a green checkmark.

- [ ] **Step 5: Verify the threshold alert fired and deactivated, and the recommendation_change alert evaluated cleanly**

`mcp__supabase__execute_sql(query="select a.id, a.alert_type, a.is_active, e.fired_at, e.details from public.alerts a left join public.alert_events e on e.alert_id = a.id where a.base_code='USD' and a.quote_code='INR' order by a.created_at desc limit 2")`

Expected: the `threshold` alert has `is_active = false` and a matching `alert_events` row with `details` describing the crossing. The `recommendation_change` alert has `is_active = true` (unchanged) and no `alert_events` row yet (correct — no prior recommendation existed to compare against on its first evaluation).

- [ ] **Step 6: Clean up the test alerts**

`mcp__supabase__execute_sql(query="delete from public.alerts where base_code='USD' and quote_code='INR' and alert_type in ('threshold','recommendation_change') and user_id = '<the user id from above>'")`

(The `on delete cascade` on `alert_events.alert_id` cleans up the associated event row automatically.)

- [ ] **Step 7: Run the full backend test suite one more time**

Run: `pytest backend/tests -v`
Expected: PASS, all tests, no live network calls in the suite itself.

- [ ] **Step 8: Confirm nothing is left uncommitted**

Run: `git status --short`
Expected: clean.

## Definition of Done

- `public.recommendations` and `public.alert_events` exist with the RLS policies from Task 1.
- `pytest backend/tests -v` passes, including all new recommendation-engine tests, with zero live network calls.
- A manual `workflow_dispatch` run with `mode=both` completes successfully and populates `recommendations` for up to all 58 directed pairs.
- A real threshold alert, inserted against live data with a guaranteed-crossed condition, is confirmed to fire, record an `alert_events` row, and deactivate.
- A real `recommendation_change` alert is confirmed to evaluate without error on its first run (correctly not firing, since no prior recommendation exists yet to compare against).
- The scheduled trigger (daily, `recommendations` then `alerts`) is present in the committed workflow file — no further action needed for it to run automatically going forward.
- Item 5 (Notifications) and item 6 (Dashboard) roadmap notes remain accurate to what this task leaves for them to consume (`alert_events` rows for item 5; `recommendations`/`predictions` tables for item 6).
