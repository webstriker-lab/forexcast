# Phase 2 — Debt Savings Planner Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** A personal finance planner that combines Phase 1's forex forecasts with debt tracking, income management, savings goals, and gamification — answering "How much can I save, and when will I be debt-free?"

**Tech Stack:** Python 3.12, FastAPI, Supabase (PostgreSQL + RLS), React 18, TypeScript, Tailwind CSS.

**Spec:** [docs/superpowers/specs/2026-08-23-phase2-design.md](../specs/2026-08-23-phase2-design.md)

## Global Constraints

- All new tables use RLS — users can only see/modify their own data
- Timeline calculation is pure computation (no network calls) — fully testable
- Achievement logic is event-driven — triggered by data changes, not polling
- Gamification is opt-in — users can disable mascot/streaks in settings
- Multi-currency calculations use Phase 1's `cross_rate()` helper

---

### Task 1: Database Schema

**Files:**
- Create: `supabase/migrations/0007_phase2_planner.sql`

**Steps:**

- [ ] **Step 1: Create the migration file**

```sql
-- Phase 2: Debt Savings Planner & Gamification

-- Debts table
create table public.debts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    name text not null,
    currency_code text not null references public.currencies (code),
    original_amount numeric not null check (original_amount > 0),
    current_balance numeric not null check (current_balance >= 0),
    interest_rate numeric not null check (interest_rate >= 0),
    minimum_payment numeric not null check (minimum_payment > 0),
    due_day integer check (due_day between 1 and 31),
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

alter table public.debts enable row level security;

create policy "debts_owner_select" on public.debts
    for select using (auth.uid() = user_id);
create policy "debts_owner_insert" on public.debts
    for insert with check (auth.uid() = user_id);
create policy "debts_owner_update" on public.debts
    for update using (auth.uid() = user_id);
create policy "debts_owner_delete" on public.debts
    for delete using (auth.uid() = user_id);

-- Income table
create table public.income (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    name text not null,
    currency_code text not null references public.currencies (code),
    amount numeric not null check (amount > 0),
    frequency text not null check (frequency in ('monthly', 'biweekly', 'weekly')),
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

alter table public.income enable row level security;

create policy "income_owner_select" on public.income
    for select using (auth.uid() = user_id);
create policy "income_owner_insert" on public.income
    for insert with check (auth.uid() = user_id);
create policy "income_owner_update" on public.income
    for update using (auth.uid() = user_id);
create policy "income_owner_delete" on public.income
    for delete using (auth.uid() = user_id);

-- Savings goals table
create table public.savings_goals (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    name text not null,
    target_currency text not null references public.currencies (code),
    target_amount numeric not null check (target_amount > 0),
    current_saved numeric not null default 0 check (current_saved >= 0),
    target_date date,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

alter table public.savings_goals enable row level security;

create policy "savings_goals_owner_select" on public.savings_goals
    for select using (auth.uid() = user_id);
create policy "savings_goals_owner_insert" on public.savings_goals
    for insert with check (auth.uid() = user_id);
create policy "savings_goals_owner_update" on public.savings_goals
    for update using (auth.uid() = user_id);
create policy "savings_goals_owner_delete" on public.savings_goals
    for delete using (auth.uid() = user_id);

-- Achievements table
create table public.achievements (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    badge_id text not null,
    badge_name text not null,
    badge_emoji text not null,
    earned_at timestamptz not null default now(),
    metadata jsonb,
    unique (user_id, badge_id)
);

alter table public.achievements enable row level security;

create policy "achievements_owner_select" on public.achievements
    for select using (auth.uid() = user_id);
create policy "achievements_owner_insert" on public.achievements
    for insert with check (auth.uid() = user_id);

-- Streaks table
create table public.streaks (
    user_id uuid primary key references auth.users (id) on delete cascade,
    daily_checkin_current integer not null default 0,
    daily_checkin_best integer not null default 0,
    daily_checkin_last date,
    savings_current integer not null default 0,
    savings_best integer not null default 0,
    savings_last date,
    debt_payment_current integer not null default 0,
    debt_payment_best integer not null default 0,
    debt_payment_last date,
    updated_at timestamptz not null default now()
);

alter table public.streaks enable row level security;

create policy "streaks_owner_select" on public.streaks
    for select using (auth.uid() = user_id);
create policy "streaks_owner_insert" on public.streaks
    for insert with check (auth.uid() = user_id);
create policy "streaks_owner_update" on public.streaks
    for update using (auth.uid() = user_id);
```

- [ ] **Step 2: Commit**

```bash
git add supabase/migrations/0007_phase2_planner.sql
git commit -m "feat: add Phase 2 schema — debts, income, savings goals, achievements, streaks"
```

---

### Task 2: Backend CRUD Routes

**Files:**
- Create: `backend/app/planner/__init__.py`
- Create: `backend/app/planner/supabase_rest.py`
- Create: `backend/app/planner/routes.py`
- Test: `backend/tests/test_planner_routes.py`

**Steps:**

- [ ] **Step 1: Create Supabase accessors**

```python
# backend/app/planner/supabase_rest.py
from datetime import datetime, timezone
import httpx
from app.config import get_settings

def _headers(prefer: str | None = None) -> dict:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers

# Debts CRUD
def get_user_debts(user_id: str) -> list[dict]:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/debts",
        params={"user_id": f"eq.{user_id}", "is_active": "eq.true", "order": "created_at.desc"},
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()

def create_debt(user_id: str, data: dict) -> dict:
    settings = get_settings()
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/debts",
        headers=_headers(prefer="return=representation"),
        json={**data, "user_id": user_id},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()[0]

def update_debt(debt_id: str, user_id: str, data: dict) -> dict | None:
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/debts",
        params={"id": f"eq.{debt_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        json=data,
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None

def delete_debt(debt_id: str, user_id: str) -> bool:
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/debts",
        params={"id": f"eq.{debt_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(),
        json={"is_active": False},
        timeout=30.0,
    )
    response.raise_for_status()
    return True

# Similar functions for income, savings_goals, achievements, streaks...
```

- [ ] **Step 2: Create FastAPI routes**

```python
# backend/app/planner/routes.py
from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user
from app.planner.supabase_rest import (
    get_user_debts, create_debt, update_debt, delete_debt,
    # ... other imports
)

router = APIRouter(prefix="/planner", tags=["planner"])

@router.get("/debts")
async def list_debts(user_id: str = Depends(get_current_user)):
    return get_user_debts(user_id)

@router.post("/debts")
async def add_debt(data: dict, user_id: str = Depends(get_current_user)):
    return create_debt(user_id, data)

# ... similar routes for income, goals, achievements, streaks
```

- [ ] **Step 3: Write tests**

- [ ] **Step 4: Commit**

---

### Task 3: Timeline Calculation Engine

**Files:**
- Create: `backend/app/planner/timeline.py`
- Test: `backend/tests/test_planner_timeline.py`

**Steps:**

- [ ] **Step 1: Implement amortization calculator**

```python
# backend/app/planner/timeline.py
from datetime import date, timedelta
from dataclasses import dataclass

@dataclass
class DebtPayment:
    month: int
    payment: float
    interest: float
    principal: float
    remaining_balance: float

@dataclass
class TimelineEntry:
    month: int
    date: date
    debts: dict[str, DebtPayment]  # debt_id -> payment details
    total_debt: float
    total_interest_paid: float
    savings_progress: dict[str, float]  # goal_id -> current amount

def calculate_debt_payoff(
    principal: float,
    annual_rate: float,
    monthly_payment: float,
    start_date: date,
) -> list[DebtPayment]:
    """Calculate month-by-month debt payoff with compound interest."""
    payments = []
    balance = principal
    monthly_rate = annual_rate / 12
    month = 0
    
    while balance > 0 and month < 600:  # 50 year cap
        month += 1
        interest = balance * monthly_rate
        principal_paid = min(monthly_payment - interest, balance)
        balance -= principal_paid
        
        payments.append(DebtPayment(
            month=month,
            payment=monthly_payment,
            interest=interest,
            principal=principal_paid,
            remaining_balance=max(0, balance),
        ))
    
    return payments

def calculate_savings_timeline(
    target_amount: float,
    monthly_contribution: float,
    current_saved: float,
    start_date: date,
) -> list[dict]:
    """Calculate month-by-month savings progress."""
    timeline = []
    balance = current_saved
    month = 0
    
    while balance < target_amount and month < 600:
        month += 1
        balance += monthly_contribution
        
        timeline.append({
            "month": month,
            "date": start_date + timedelta(days=30 * month),
            "balance": min(balance, target_amount),
            "progress": min(balance / target_amount, 1.0),
        })
    
    return timeline

def calculate_forex_impact(
    debt_amount: float,
    debt_currency: str,
    income_currency: str,
    current_rate: float,
    predicted_rate: float,
) -> dict:
    """Calculate how forex timing affects debt cost."""
    current_cost = debt_amount / current_rate
    predicted_cost = debt_amount / predicted_rate
    savings = current_cost - predicted_cost
    
    return {
        "current_cost": current_cost,
        "predicted_cost": predicted_cost,
        "potential_savings": savings,
        "recommendation": "wait" if savings > 0 else "act_now",
    }
```

- [ ] **Step 2: Write comprehensive tests**

- [ ] **Step 3: Commit**

---

### Task 4: Achievement & Streak Logic

**Files:**
- Create: `backend/app/planner/achievements.py`
- Test: `backend/tests/test_planner_achievements.py`

**Steps:**

- [ ] **Step 1: Define badge constants**

```python
# backend/app/planner/achievements.py
BADGES = {
    "first_debt_paid_off": {
        "name": "First Debt Paid Off",
        "emoji": "🎯",
        "description": "Paid off your first debt completely",
    },
    "savings_goal_reached": {
        "name": "Savings Goal Reached",
        "emoji": "💰",
        "description": "Reached a savings goal",
    },
    "forex_check_100": {
        "name": "100 Forex Checks",
        "emoji": "📊",
        "description": "Checked forex rates 100 times",
    },
    "streak_30_days": {
        "name": "Fox Friend",
        "emoji": "🦊",
        "description": "30-day check-in streak",
    },
    "multi_currency_master": {
        "name": "Multi-Currency Master",
        "emoji": "🌍",
        "description": "Active debts in 3+ currencies",
    },
    "forecast_follower": {
        "name": "Forecast Follower",
        "emoji": "📈",
        "description": "Acted on 10 recommendations",
    },
    "financial_freedom": {
        "name": "Financial Freedom",
        "emoji": "🏆",
        "description": "All debts paid off",
    },
}

def check_debt_achievements(user_id: str, debts: list[dict], achievements: list[dict]) -> list[dict]:
    """Check if any debt-related achievements should be earned."""
    new_achievements = []
    earned_ids = {a["badge_id"] for a in achievements}
    
    # Check for paid off debts
    paid_off = [d for d in debts if d["current_balance"] == 0]
    if paid_off and "first_debt_paid_off" not in earned_ids:
        new_achievements.append({
            "badge_id": "first_debt_paid_off",
            **BADGES["first_debt_paid_off"],
            "metadata": {"debt_name": paid_off[0]["name"]},
        })
    
    # Check for multi-currency
    active_currencies = {d["currency_code"] for d in debts if d["is_active"]}
    if len(active_currencies) >= 3 and "multi_currency_master" not in earned_ids:
        new_achievements.append({
            "badge_id": "multi_currency_master",
            **BADGES["multi_currency_master"],
        })
    
    # Check for financial freedom
    active_debts = [d for d in debts if d["is_active"] and d["current_balance"] > 0]
    if not active_debts and debts and "financial_freedom" not in earned_ids:
        new_achievements.append({
            "badge_id": "financial_freedom",
            **BADGES["financial_freedom"],
        })
    
    return new_achievements

def update_streak(user_id: str, streak_type: str, current_streak: dict) -> dict:
    """Update a streak counter."""
    today = date.today()
    last_date = current_streak.get(f"{streak_type}_last")
    
    if last_date == today:
        return current_streak  # Already checked in today
    
    if last_date == today - timedelta(days=1):
        # Consecutive day
        current_streak[f"{streak_type}_current"] += 1
    else:
        # Streak broken
        current_streak[f"{streak_type}_current"] = 1
    
    current_streak[f"{streak_type}_last"] = today
    current_streak[f"{streak_type}_best"] = max(
        current_streak.get(f"{streak_type}_best", 0),
        current_streak[f"{streak_type}_current"]
    )
    
    return current_streak
```

- [ ] **Step 2: Write tests**

- [ ] **Step 3: Commit**

---

### Task 5: Frontend Components

**Files:**
- Create: `frontend/src/pages/Planner.tsx`
- Create: `frontend/src/pages/Debts.tsx`
- Create: `frontend/src/pages/Goals.tsx`
- Create: `frontend/src/pages/Achievements.tsx`
- Create: `frontend/src/components/DebtManager.tsx`
- Create: `frontend/src/components/SavingsGoalManager.tsx`
- Create: `frontend/src/components/TimelineView.tsx`
- Create: `frontend/src/components/ForexImpactCard.tsx`
- Create: `frontend/src/components/MascotWidget.tsx`
- Create: `frontend/src/components/BadgeGrid.tsx`
- Create: `frontend/src/components/StreakCounter.tsx`
- Create: `frontend/src/hooks/useDebts.ts`
- Create: `frontend/src/hooks/useIncome.ts`
- Create: `frontend/src/hooks/useSavingsGoals.ts`
- Create: `frontend/src/hooks/useAchievements.ts`

**Steps:**

- [ ] **Step 1: Create data hooks**

- [ ] **Step 2: Create UI components**

- [ ] **Step 3: Create pages**

- [ ] **Step 4: Update App.tsx with new routes**

- [ ] **Step 5: Commit**

---

### Task 6: Integration & Testing

**Steps:**

- [ ] **Step 1: Run full backend test suite**

- [ ] **Step 2: Run frontend build**

- [ ] **Step 3: Verify all routes work**

- [ ] **Step 4: Commit and push**

---

### Task 7: Live Verification

**Steps:**

- [ ] **Step 1: Apply schema migration**

- [ ] **Step 2: Test CRUD operations**

- [ ] **Step 3: Test timeline calculation**

- [ ] **Step 4: Test achievement system**

- [ ] **Step 5: Final commit**
