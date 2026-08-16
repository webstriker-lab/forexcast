-- One LLM-scored sentiment reading per currency per day. Internal
-- computation state only, like backtest_stats/macro_rates -- no
-- consumer outside the prediction pipeline reads this directly yet.
create table public.news_sentiment (
    currency_code text not null references public.currencies (code),
    as_of date not null,
    score numeric not null,
    summary text not null,
    article_count integer not null,
    generated_at timestamptz not null default now(),
    primary key (currency_code, as_of)
);

alter table public.news_sentiment enable row level security;
-- Deliberately no select policy: only the service role (which bypasses
-- RLS) reads or writes this table, matching backtest_stats/macro_rates'
-- convention.
