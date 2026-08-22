# Phase 2 Fix — Design Spec

Corrects `docs/superpowers/specs/2026-08-23-phase2-design.md`'s implementation
(commit `c427808`), which was built without review and shipped several
design-level defects — not just bugs — found by an independent review of
the unreviewed code. That review is not repeated here; see project memory
for the full findings. This spec settles the design questions the review
surfaced and states exactly what changes.

The Phase 2 migration (`supabase/migrations/0007_phase2_planner.sql`) has
never been applied to the live database — this is a pre-launch correction,
not a live-data migration. The migration itself is revised here rather than
appended to, since nothing has ever depended on its current shape.

**Scope boundary:** this spec makes the *already-built* surface (debts,
savings goals, badges, streaks — `DebtManager`, `SavingsGoalManager`,
`BadgeGrid`, `StreakCounter`, `MascotWidget`, and their backend routes)
correct, secure, and internally consistent. It does not build the
components the original spec promised but never shipped (an Income page,
`MilestoneTracker`, `TimelineView`, `ForexImpactCard`) — those stay
deferred, matching this project's established incremental-shipping pattern
(2a before 2b/2c, 5a before 5b). Revisit only if a future increment
actually needs them.

## 1. Interest rate: standardize on percentage-as-typed

`DebtManager.tsx`'s form takes and (attempts to) display interest rate as a
plain percentage ("5.5" for 5.5%), but `timeline.py`'s
`monthly_rate = annual_rate / 12` treats the stored value as a fraction
(0.055) — so a real 5.5% debt is computed as 550% APR and the payoff
calculation raises for almost any real input.

**Decision:** the column stores the percentage exactly as a user types it
(5.5 means 5.5%) — this needs no schema change, `interest_rate numeric` is
already unit-less; only the two places that give it meaning need to agree.

- `timeline.py`: `monthly_rate = (annual_rate / 100) / 12`.
- `DebtManager.tsx`: display the stored value directly with a `%` suffix —
  remove the existing `* 100` in the display path (that was compensating
  for the wrong convention).

## 2. Savings goal timeline: no fabricated numbers

`POST /planner/timeline/goals` currently invents `monthly_contribution =
target_amount * 0.1` regardless of the user's actual situation — every
goal projects to exactly 10 months.

**Decision:** add `monthly_contribution numeric` (nullable) to
`savings_goals`, exposed as a real optional field in `SavingsGoalCreate`/
`SavingsGoalUpdate` and a real input in `SavingsGoalManager.tsx`. At
timeline-calculation time:

1. If `monthly_contribution` is set, use it directly.
2. Else if `target_date` is set, derive it honestly:
   `(target_amount - current_saved) / months_between(today, target_date)`,
   where `months_between(a, b) = max(1, (b.year - a.year) * 12 + (b.month
   - a.month))` — calendar-month difference, floored at 1 to avoid
   division by zero for a same-month or past target date.
3. Else, return `{"error": "set a monthly contribution or a target date"}`
   for that goal (matching this codebase's per-item error-shape
   convention, e.g. `get_debt_timeline`'s existing per-debt `{"error":
   ...}` entries) rather than fabricating a number.

## 3. Achievements: one source of truth, not three

The actual root cause: three separate places encode the same 9 badges and
disagree. `achievements.py`'s `check_*_achievements` functions spread
`BADGES[badge_id]` (keys `name`/`emoji`/`description`) into the row passed
to `create_achievement`; the `achievements` table has columns
`badge_name`/`badge_emoji` (no `description`) — so PostgREST rejects
every insert, silently, because `routes.py`'s `except Exception: pass`
swallows it. Separately, `BadgeGrid.tsx` hardcodes its own third, 7-badge
list, different from both.

**Decision:** stop storing display metadata per-row at all — `BADGES` in
`achievements.py` becomes the single source of truth, and every consumer
(backend award-checks, frontend display) reads through it by `badge_id`.

- Revise the `achievements` table to `(id, user_id, badge_id, earned_at,
  metadata, unique(user_id, badge_id))` — drop `badge_name`/`badge_emoji`
  entirely, they were always derivable from `badge_id`.
- `check_*_achievements` functions build `{"badge_id": ..., "metadata":
  ...}` only — no more spreading `BADGES[...]` into the row.
- `GET /planner/badges` (already exists) is the one place the full
  `BADGES` catalog is served; add `Depends(get_current_user)` to it for
  consistency — it's the only route besides `/health` that lacked auth,
  and being static/non-sensitive isn't a reason for the exception; every
  other route in this codebase requires it.
- `BadgeGrid.tsx` fetches `GET /planner/badges` for the catalog (name/
  emoji/description) and `GET /planner/achievements` for which `badge_id`s
  the user has earned, joining them client-side — its own hardcoded list
  is deleted.

## 4. Streak logic: backend-only

`useAchievements.ts` reimplements `update_streak`'s logic client-side,
diverging from the backend version in two ways: it has no same-day guard
(a second check-in the same day resets the streak to 1 instead of leaving
it unchanged), and it computes "today" via `toISOString()` (UTC) while the
backend uses `date.today()` (server-local) — two clocks writing the same
column.

**Decision:** delete the client-side reimplementation. The frontend calls
the existing `POST /planner/streaks/checkin` instead, inheriting the
backend's already-correct, already-tested logic — one implementation, not
two that can disagree.

## 5. Multi-currency debt summary: convert before summing

`calculate_total_debt_summary` sums `current_balance` across debts with
different `currency_code`s with no conversion, and the frontend displays
the result with a bare `$` prefix — for an app whose premise is
multi-currency debt, this produces a materially wrong headline number.

**Decision:** convert every debt's balance to USD (this app's existing
pivot currency, per `PIVOT = "USD"` in `recommendations/jobs.py`) before
summing. `calculate_total_debt_summary` stays a pure function — it gains a
`rates: dict[str, float]` parameter (currency_code -> USD rate) that the
route builds by calling the already-reviewed
`app.recommendations.supabase_rest.get_current_rate` once per distinct
currency among the user's debts, before invoking the calculator. A debt in
`currency_code == "USD"` needs no lookup (rate 1.0). If a rate is
unavailable for some currency (no `rates_cache` data yet), that debt's
balance is excluded from `total_balance` and a `currencies_missing_rate:
list[str]` field is added to the summary so the frontend can say "total
excludes N debts pending a rate" rather than silently under-reporting with
no explanation.

## 6. Mechanical fixes (matching this codebase's established patterns)

- **Field allowlists**: `update_debt`/`update_income`/`update_savings_goal`
  currently pass their `data` dict straight into the PATCH body. Add an
  allowlist per table (matching `update_alert_for_user`'s reasoning: the
  service-role key bypasses RLS, so this is the only enforcement
  boundary) — `debts`: `name`/`current_balance`/`interest_rate`/
  `minimum_payment`/`due_day`; `income`: `name`/`amount`/`frequency`;
  `savings_goals`: `name`/`target_amount`/`current_saved`/`target_date`/
  `monthly_contribution`. `currency_code` is excluded from every allowlist
  — a debt/income/goal's currency is fixed at creation, matching how
  `create_alert_for_user` treats `base_code`/`quote_code`.
- **Deletes report real outcomes**: `delete_debt`/`delete_income`/
  `delete_savings_goal` return `len(response.json()) > 0` (matching
  `delete_alert_for_user`) instead of an unconditional `True` — a delete
  for an id that doesn't exist or isn't owned by the caller should say so.
- **`include_inactive` for achievement-checking**: `get_user_debts`/
  `get_user_income`/`get_user_savings_goals` gain an `include_inactive:
  bool = False` parameter. Default behavior now actually matches their
  docstrings (`is_active=eq.true` filter added) for the list/timeline
  routes. `check_achievements` (which needs to see paid-off, i.e.
  inactive, debts to award `first_debt_paid_off`/`financial_freedom`)
  passes `include_inactive=True`.

## 7. Test coverage

Add `backend/tests/test_planner_supabase_rest.py` (mocked httpx, matching
every other module's `test_*_supabase_rest.py`) covering: each CRUD
function's request shape, the allowlist actually filtering an injected
key, delete returning `False` for a non-owned/missing id, and
`include_inactive` toggling the `is_active` filter. Add auth tests for
`backend/app/planner/routes.py` matching `test_routers_chat.py`'s
established real-signed-JWT convention (a request with no bearer token
gets 401 on at least one representative route per CRUD group, plus the
now-authenticated `/badges`).

## 8. Testing the corrected calculations

- `calculate_debt_payoff`: a test asserting the *exact* known values for a
  realistic input (10000 @ 12% APR, 500/mo -> 23 months, $1,213.48 total
  interest — already verified by hand during the review) pinned as an
  actual assertion, not just `len(payments) > 0`.
- `calculate_savings_timeline`'s goal-derivation path: a test with
  `target_date` set and no `monthly_contribution`, asserting the derived
  value matches `(target - current) / months`.
- `calculate_total_debt_summary`: a test with two debts in different
  currencies and a `rates` dict, asserting the USD-converted sum, plus a
  test for the `currencies_missing_rate` path when a rate is absent.
- Achievement award round-trip: a test that `check_debt_achievements`'
  output dict, when passed through `create_achievement` (mocked httpx),
  produces a PATCH/POST body containing only `badge_id`/`user_id`/
  `metadata` — no `name`/`emoji`/`description` keys — closing the exact
  gap that let the original mismatch ship silently.

## 9. Migration revision

`supabase/migrations/0007_phase2_planner.sql` is edited in place (not
migration `0008`) since it has never been applied — `debts`/`income`
unchanged; `savings_goals` gains `monthly_contribution numeric`;
`achievements` drops `badge_name`/`badge_emoji`. Applied live via
`mcp__supabase__apply_migration` as part of this plan's execution, the
same as every other migration in this project.
