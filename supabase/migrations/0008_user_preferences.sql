-- Per-user display preferences (currently just a preferred currency for
-- totals shown across the Planner -- debts/goals can each be in any of the
-- app's currencies, and totals need a single currency to be summed into).
create table public.user_preferences (
    user_id uuid primary key references auth.users (id) on delete cascade,
    display_currency text not null default 'USD' references public.currencies (code),
    updated_at timestamptz not null default now()
);

alter table public.user_preferences enable row level security;

create policy "user_preferences_owner_select" on public.user_preferences
    for select using (auth.uid() = user_id);
create policy "user_preferences_owner_insert" on public.user_preferences
    for insert with check (auth.uid() = user_id);
create policy "user_preferences_owner_update" on public.user_preferences
    for update using (auth.uid() = user_id);
