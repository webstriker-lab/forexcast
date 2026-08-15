# ForexCast — Recommendation Engine & Alerts (Design)

**Status:** Approved for planning
**Date:** 2026-08-15
**Scope:** Roadmap item 3 — the continuous ACT NOW/WAIT/VOLATILE recommendation computation, plus evaluation of manual `alerts` (both `threshold` and `recommendation_change` types). See [Deferred](#deferred) below for what's explicitly excluded.

## 1. Goal

Turn the raw forecasts already in `predictions` into an actionable signal — not "what will the rate be" but "should I act now, or is it worth waiting" — for both directions of every currency pair the app tracks, and detect when a user's manually-configured alert condition has actually fired.

## 2. Scope

**In scope:**
- A daily job computing one ACT NOW / WAIT / VOLATILE recommendation per directed pair (58 pairs: 29 currencies × both directions against USD), written to a new `recommendations` table.
- Evaluation of `alerts` rows (both `threshold` and `recommendation_change` types) against current data, recording firings to a new `alert_events` table.
- Scheduled via GitHub Actions, running after the daily forecast job.

**Deferred:**
- **Notification dispatch** (Telegram/email) is roadmap item 5. This task only records *that* an alert fired (`alert_events`); actually notifying the user about it is a separate, later concern with its own integration work (bot setup, email service, user-linking flows).
- **Backend API routes.** No FastAPI endpoint exposes `predictions` or `rates_cache` today — a future frontend queries Supabase directly via RLS. `recommendations` and `alert_events` follow the same precedent. Revisit only if the dashboard (item 6) finds a concrete reason a direct table read can't serve it.

## 3. Direction Handling

`predictions` only stores the USD→X direction (e.g. USD→INR: units of INR per 1 USD). A high USD→X rate is favorable for someone converting USD *into* INR (a remittance sender); a low USD→X rate is favorable for someone converting INR *into* USD (e.g. paying off a USD-denominated debt with INR earnings) — same underlying forecast, opposite meaning of "favorable," **stated here in USD→X terms**.

This task computes recommendations for **both directions** from the same 29×4 prediction rows. §4's algorithm always operates on a pair's *own stored value-space* — it never re-derives favorability by looking at the other direction's numbers:

- `(base_code='USD', quote_code=X)`: stores the USD→X figures as-is. Favorable = higher rate, in USD→X units.
- `(base_code=X, quote_code='USD')`: stores the simple reciprocal (`1 / value`) of the USD→X figures — a plain reciprocal, not `cross_rate()`, since one side is always USD here (no third-currency pivot involved). Inverting a range flips its order: the new lower bound is `1 / (USD→X upper bound)`, the new upper bound is `1 / (USD→X lower bound)`, since reciprocal is a decreasing function for positive numbers. **In this row's own reciprocal units, favorable is also the higher value** — a higher X→USD figure means more USD received per unit of X, the same real-world outcome as a *low* USD→X rate, just re-expressed. The "low is favorable" language above describes the underlying economics in USD→X terms; once the numbers are inverted into the X→USD row's own units, §4 treats high as favorable for both rows identically.

## 4. Recommendation Algorithm

One recommendation per directed pair per day, synthesized across that pair's 4 horizon predictions (7/30/90/365) from the same day's forecast batch — not 4 separate per-horizon recommendations. This matches the product spec's "WAIT (~N days)" phrasing, which names a single horizon, not four.

Both directed pairs are evaluated with the **same** rule below, applied to that pair's own stored value-space from §3 (for X→USD, that means every horizon's predicted_rate/lower_bound/upper_bound has already been inverted, and `current_rate` is `1 / (USD→X current rate)`, before this algorithm runs). There is no separate "favorable low" branch — the reciprocal transform in §3 is what encodes the direction; the comparison logic itself is identical for both rows.

1. Among the pair's 4 horizons (already in the pair's own value-space), find the **reference horizon**: whichever one the model expects the highest rate at.
2. Compare today's current rate (also already in the pair's own value-space) to the reference horizon's predicted rate: `current_rate >= reference predicted_rate` → **`act_now`** (today is already as good as or better than what the model expects later); otherwise (current rate is still below the reference prediction) → **`wait`**, with the reference horizon's day-count as "~N days" and its predicted rate + band as the target to watch for.
3. If the reference horizon's `confidence` is `'low'` → **`volatile`**, overriding the above. This reuses the prediction engine's existing per-currency volatility flag directly — no new confidence logic is computed here.

If fewer than 4 horizons exist for a pair on a given day (e.g. a currency was skipped that day because its `backtest_stats` weren't ready yet — an already-established, expected gap from the prediction engine), the algorithm just works with whichever horizons are present; if none are present for that pair that day, it's skipped for that run, not treated as an error.

## 5. New Schema

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

`recommendations` mirrors `predictions`' public-read, no-owner shape exactly (it's a market-wide computed signal, not per-user data). `alert_events` is scoped to the owning alert's user via a join-based policy, matching how a user should eventually be able to see their own alert history; only the service role (bypassing RLS) writes either table.

## 6. Alert Evaluation

The two `alert_type` values behave differently and need different post-fire handling:

- **`threshold`**: one-shot. Evaluated by comparing the pair's current rate against `threshold_rate` in the configured `direction` (`'above'`/`'below'`). On crossing: insert an `alert_events` row and set the alert's `is_active = false`. This matches the product spec's "tell me the *moment* it crosses" framing — a single notification, not a daily repeat of an already-known fact. (Deactivating also naturally prevents the same crossing from re-firing every day it stays crossed.)
- **`recommendation_change`**: repeating. Evaluated by comparing the pair's most recent `recommendations` row against the one before it. On a change: insert an `alert_events` row. `is_active` is **not** touched — a debt-payoff decision cares every time the signal flips, not just once, so this alert type stays active indefinitely.

Only `is_active = true` alerts are evaluated. Currency direction handling for `threshold` alerts follows the same reciprocal logic as §3 when the alert's `base_code`/`quote_code` names the X→USD direction.

## 7. Components

- `backend/app/recommendations/engine.py` — pure computation: given a pair's horizon predictions, apply §4's algorithm and return a recommendation dict. Given a USD→X figure (rate or bound), the direction-flip/reciprocal math from §3.
- `backend/app/recommendations/alerts.py` — pure computation: given an active alert plus current data, decide whether it fired.
- `backend/app/recommendations/supabase_rest.py` — I/O layer: reads each pair's latest prediction batch, reads active `alerts`, reads current rates, writes `recommendations` and `alert_events`, updates `alerts.is_active`. Mirrors the established `_headers()`/batching conventions from the ingestion and prediction packages' own `supabase_rest.py` modules.
- `backend/app/recommendations/jobs.py` — daily orchestration: `run_recommendations() -> int` (computes and writes recommendations for all 58 directed pairs) and `run_alert_evaluation() -> int` (evaluates all active alerts). Two separate functions since they have different inputs/outputs, but both run in the same daily job.
- `backend/app/recommendations/cli.py` — `python -m app.recommendations.cli --mode recommendations` / `--mode alerts`.
- `.github/workflows/recommend.yml` — daily, scheduled after the prediction engine's forecast cron.
- `supabase/migrations/0004_recommendations_and_alerts.sql` — the schema from §5.

## 8. Error Handling

Same "fail loudly, skip only genuinely expected gaps" principle already established: a pair with no prediction batch that day is skipped (expected — matches an already-known upstream gap), everything else propagates. Alert evaluation errors for one alert should not silently swallow — if a currency pair referenced by an alert has no current rate data, that's an unexpected condition worth failing loudly on, not skipping, since (unlike a fresh currency awaiting its first backtest) this app's 29-currency universe is fixed and known.

## 9. Testing

- `engine.py`/`alerts.py`: pure-function unit tests on synthetic data — reference-horizon selection, act-now/wait/volatile branching, the reciprocal direction-flip math (verify the round-trip identity the way earlier tasks did), threshold crossing in both directions, recommendation-change detection.
- `supabase_rest.py`: mocked-`httpx` tests matching the established convention.
- `jobs.py`/`cli.py`: orchestration tests with mocked dependencies.
- No live network or database calls in the automated suite. Live verification (real data produces sane, direction-correct recommendations) happens as a manual step against the live project, same pattern as the two prior plans.

## Definition of Done

- `supabase/migrations/0004_recommendations_and_alerts.sql` applied; both new tables exist with the RLS policies from §5.
- Daily job populates `recommendations` for all 58 directed pairs (up to; fewer if a pair's prediction batch is incomplete that day).
- Alert evaluation runs against any active alerts and correctly records firings to `alert_events`, with `threshold` alerts deactivating on fire and `recommendation_change` alerts staying active.
- Backend test suite (including new recommendation-engine tests) passes with no live network calls.
- Item 5 (Notifications) and item 6 (Dashboard) roadmap notes remain accurate to what this task actually leaves for them to consume.
