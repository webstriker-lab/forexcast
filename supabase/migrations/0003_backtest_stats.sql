-- Backtest results per (currency, horizon), refreshed weekly. Internal
-- computation state only -- the frontend never queries this directly,
-- everything it needs is already in public.predictions.
create table public.backtest_stats (
    id bigserial primary key,
    quote_code text not null references public.currencies (code),
    horizon_days integer not null,
    error_lower_pct numeric not null,
    error_upper_pct numeric not null,
    volatility_p90 numeric not null,
    sample_count integer not null,
    computed_at timestamptz not null default now(),
    unique (quote_code, horizon_days)
);

alter table public.backtest_stats enable row level security;
-- Deliberately no select policy: only the service role (which bypasses
-- RLS) reads or writes this table.
