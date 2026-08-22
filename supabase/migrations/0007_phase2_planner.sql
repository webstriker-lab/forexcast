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
    monthly_contribution numeric check (monthly_contribution > 0),
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
