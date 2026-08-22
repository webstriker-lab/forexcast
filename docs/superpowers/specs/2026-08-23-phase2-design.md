# ForexCast Phase 2 — Debt Savings Planner & Gamification (Design)

**Status:** Draft
**Date:** 2026-08-23
**Scope:** Phase 2 — extends Phase 1's currency data layer with personal finance tools and engagement features.

## 1. Problem & Users

Ashwath and friends use ForexCast to decide *when* to convert currencies. Phase 2 answers a deeper question: **"How much can I save, and when will I be debt-free?"** — combining Phase 1's forex forecasts with personal financial planning.

Users have real financial obligations in multiple currencies:
- Student loans in USD, paid with INR earnings
- Remittances to family in different countries
- Travel savings goals in EUR/GBP
- Mixed-currency debt portfolios

Phase 2 adds two modules:
1. **Debt Savings Planner** — input debts, income, savings; get a payoff timeline with milestone tracking; see how forex timing affects the total cost
2. **Gamification** — mascot, streaks, badges to keep users engaged with their financial goals

## 2. Architecture

- **Backend:** Extends existing FastAPI with new `/planner` routes for debt/income CRUD and timeline computation
- **Frontend:** New pages in the existing React SPA — Planner, Goals, Achievements
- **Database:** New Supabase tables for debts, income, savings goals, milestones, achievements
- **Computation:** Client-side timeline calculation (no new scheduled jobs — this is on-demand, not batch)
- **Integration:** Uses Phase 1's `predictions` table for multi-currency debt cost projections

## 3. Debt Savings Planner

### 3.1 Data Model

**Debts table:**
```sql
create table public.debts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    name text not null,                    -- e.g. "Student Loan", "Credit Card"
    currency_code text not null references public.currencies (code),
    original_amount numeric not null,      -- total original debt
    current_balance numeric not null,      -- remaining balance
    interest_rate numeric not null,        -- annual interest rate (e.g. 0.05 for 5%)
    minimum_payment numeric not null,      -- monthly minimum payment
    due_day integer,                       -- day of month payment is due (1-31)
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);
```

**Income table:**
```sql
create table public.income (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    name text not null,                    -- e.g. "Salary", "Freelance"
    currency_code text not null references public.currencies (code),
    amount numeric not null,               -- monthly amount
    frequency text not null check (frequency in ('monthly', 'biweekly', 'weekly')),
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);
```

**Savings goals table:**
```sql
create table public.savings_goals (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    name text not null,                    -- e.g. "Europe Trip", "Emergency Fund"
    target_currency text not null references public.currencies (code),
    target_amount numeric not null,        -- goal amount in target currency
    current_saved numeric not null default 0,
    target_date date,                      -- optional target date
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);
```

**Milestones table:**
```sql
create table public.milestones (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    debt_id uuid references public.debts (id) on delete cascade,
    goal_id uuid references public.savings_goals (id) on delete cascade,
    milestone_type text not null check (milestone_type in ('debt_paid_off', 'goal_reached', 'balance_milestone', 'streak_milestone')),
    description text not null,
    achieved_at timestamptz not null default now(),
    metadata jsonb                        -- e.g. {"amount": 1000, "currency": "USD"}
);
```

### 3.2 Timeline Calculation

The planner computes a month-by-month payoff timeline:

1. **For each active debt:**
   - Calculate months to payoff using amortization formula
   - Factor in interest (compound monthly)
   - Show when each debt hits milestones (50% paid, 75% paid, paid off)

2. **For savings goals:**
   - Calculate months to reach target based on monthly contribution
   - Factor in forex rate changes using Phase 1's predictions
   - Show projected completion date

3. **Multi-currency optimization:**
   - If user earns in INR but has USD debt, show how forex timing affects total cost
   - Use Phase 1's ACT NOW/WAIT recommendations to suggest optimal conversion timing
   - Calculate potential savings from timing vs. immediate conversion

### 3.3 Components

- **DebtManager** — CRUD for debts, shows current balances and interest rates
- **IncomeManager** — CRUD for income sources
- **SavingsGoalManager** — CRUD for savings goals with target dates
- **TimelineView** — interactive timeline showing debt payoff and goal progress
- **ForexImpactCard** — shows how forex timing affects multi-currency obligations
- **MilestoneTracker** — displays achieved and upcoming milestones

## 4. Gamification

### 4.1 Mascot

A friendly fox mascot named "Forex" that:
- Appears on the dashboard with contextual messages
- Celebrates milestones with animations
- Provides tips and encouragement
- Reacts to market conditions (happy when rates are favorable, concerned during volatility)

### 4.2 Streaks

- **Daily Check-in Streak** — consecutive days visiting the app
- **Savings Streak** — consecutive months contributing to savings goals
- **Debt Payment Streak** — consecutive months making debt payments on time
- **Forecast Accuracy Streak** — consecutive days where user acted on recommendations

### 4.3 Badges

**Financial Milestones:**
- 🎯 First Debt Paid Off
- 💰 Savings Goal Reached
- 📊 100 Forex Checks
- 🦊 Fox Friend (30-day streak)
- 🌍 Multi-Currency Master (active debts in 3+ currencies)
- 📈 Forecast Follower (acted on 10 recommendations)
- 💎 Diamond Hands (held through volatility without panic selling)
- 🏆 Financial Freedom (all debts paid off)

**Engagement:**
- 🔔 Alert Setter (created first alert)
- 💬 Chat User (first conversation with AI)
- 📱 PWA Installer (installed app on phone)
- 🎯 Goal Setter (created first savings goal)

### 4.4 Achievement System

```sql
create table public.achievements (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    badge_id text not null,                -- e.g. "first_debt_paid_off"
    badge_name text not null,              -- e.g. "First Debt Paid Off"
    badge_emoji text not null,             -- e.g. "🎯"
    earned_at timestamptz not null default now(),
    metadata jsonb,                        -- e.g. {"debt_name": "Student Loan", "amount": 5000}
    unique (user_id, badge_id)
);
```

### 4.5 Components

- **MascotWidget** — animated fox with contextual messages
- **StreakCounter** — displays current streaks with fire emoji
- **BadgeGrid** — shows earned and locked badges
- **AchievementToast** — popup when new badge earned
- **ProgressRing** — circular progress indicator for goals

## 5. New Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/planner/debts` | GET/POST | List/create debts |
| `/planner/debts/{id}` | PUT/DELETE | Update/delete debt |
| `/planner/income` | GET/POST | List/create income sources |
| `/planner/income/{id}` | PUT/DELETE | Update/delete income |
| `/planner/goals` | GET/POST | List/create savings goals |
| `/planner/goals/{id}` | PUT/DELETE | Update/delete goal |
| `/planner/timeline` | GET | Compute payoff timeline |
| `/planner/achievements` | GET | List earned badges |
| `/planner/streaks` | GET | Get current streaks |

## 6. Frontend Pages

| Route | Component | Description |
|-------|-----------|-------------|
| `/planner` | Planner | Main planner view with timeline |
| `/planner/debts` | Debts | Debt management |
| `/planner/income` | Income | Income management |
| `/planner/goals` | Goals | Savings goals |
| `/planner/achievements` | Achievements | Badges and streaks |

## 7. Integration with Phase 1

- **Forex Impact:** Uses `predictions` to show how rate changes affect multi-currency debt costs
- **Recommendations:** Uses `recommendations` to suggest optimal conversion timing
- **Alerts:** Can create alerts for savings goal milestones (e.g., "notify when I've saved 50% of my Europe trip fund")
- **Chat:** AI can answer questions about debt payoff timelines and savings progress

## 8. Testing Strategy

- Unit tests for timeline calculation (amortization, forex impact)
- Unit tests for achievement logic (badge earning conditions)
- Integration tests for CRUD operations
- Mock tests for Supabase interactions
- No live network calls in automated tests

## 9. Implementation Order

1. Database schema (new tables)
2. Backend CRUD routes
3. Timeline calculation engine
4. Achievement/streak logic
5. Frontend components
6. Integration with Phase 1 features
7. Mascot and animations
8. Testing and verification

## Definition of Done

- All new tables created with RLS policies
- Backend routes implemented and tested
- Timeline calculation accurate and tested
- Achievement system working
- Frontend pages complete and responsive
- Integration with Phase 1 features verified
- All tests passing
- Documentation updated
