-- Records which candidate model actually won the backtest for each
-- (currency, horizon): exponential smoothing (the prior sole model) or
-- naive persistence, whichever had the lower out-of-sample error. FX
-- rates are famously close to a random walk (Meese & Rogoff, 1983), so
-- the more complex model isn't guaranteed to earn its keep for every
-- pair -- this makes that an empirical, per-pair decision rather than a
-- blanket assumption. Existing rows default to 'exponential_smoothing',
-- the only model that ever ran before this.
alter table public.backtest_stats
    add column model_selected text not null default 'exponential_smoothing'
        check (model_selected in ('exponential_smoothing', 'naive'));
