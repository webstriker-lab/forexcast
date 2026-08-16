-- FRED interest-rate observations, one row per currency per date.
-- Internal computation state only, like backtest_stats -- no consumer
-- outside the prediction pipeline reads this directly.
create table public.macro_rates (
    currency_code text not null references public.currencies (code),
    as_of date not null,
    series_id text not null,
    rate numeric not null,
    primary key (currency_code, as_of)
);

alter table public.macro_rates enable row level security;
-- Deliberately no select policy: only the service role (which bypasses
-- RLS) reads or writes this table, matching backtest_stats' convention.

-- Nullable: NULL means "no regression fit for this currency/horizon --
-- use the unadjusted 2a baseline," the default/common case until a
-- currency both has FRED coverage and clears the fit's quality gate.
alter table public.backtest_stats
    add column regression_slope numeric,
    add column regression_intercept numeric;
