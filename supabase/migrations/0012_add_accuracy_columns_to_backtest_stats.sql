ALTER TABLE public.backtest_stats
  ADD COLUMN IF NOT EXISTS es_mae                real,
  ADD COLUMN IF NOT EXISTS naive_mae              real,
  ADD COLUMN IF NOT EXISTS mae_improvement_pct    real,
  ADD COLUMN IF NOT EXISTS calibration_coverage   real;
