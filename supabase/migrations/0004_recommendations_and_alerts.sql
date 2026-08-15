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
