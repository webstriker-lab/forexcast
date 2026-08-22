-- Three more FRED-sourced macro fundamentals, one row per currency per
-- date each, mirroring macro_rates exactly (including its "internal
-- computation state only, no direct consumer" convention -- only the
-- service role reads/writes these).
create table public.macro_cpi (
    currency_code text not null references public.currencies (code),
    as_of date not null,
    series_id text not null,
    rate numeric not null,
    primary key (currency_code, as_of)
);
alter table public.macro_cpi enable row level security;

create table public.macro_gdp (
    currency_code text not null references public.currencies (code),
    as_of date not null,
    series_id text not null,
    rate numeric not null,
    primary key (currency_code, as_of)
);
alter table public.macro_gdp enable row level security;

create table public.macro_current_account (
    currency_code text not null references public.currencies (code),
    as_of date not null,
    series_id text not null,
    rate numeric not null,
    primary key (currency_code, as_of)
);
alter table public.macro_current_account enable row level security;

-- Which macro factor's regression won this (currency, horizon)'s
-- backtest, when one did: 'interest_rate' | 'cpi' | 'gdp' |
-- 'current_account'. Candidates are tried independently, never jointly
-- (with ~200-something backtest samples, a joint multivariate fit
-- across several correlated macro variables risks overfitting far more
-- than picking the single best one) -- see app.prediction.backtest.
-- Null means no factor cleared fit_regression's significance gate,
-- identical to the pre-existing "no regression fit" case.
alter table public.backtest_stats
    add column regression_factor text
        check (regression_factor in ('interest_rate', 'cpi', 'gdp', 'current_account'));
