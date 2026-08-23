import { supabase } from './supabaseClient'

export interface BacktestStat {
  quote_code: string
  horizon_days: number
  model_selected: 'exponential_smoothing' | 'naive'
  es_mae: number | null
  naive_mae: number | null
  mae_improvement_pct: number | null
  calibration_coverage: number | null
  sample_count: number
}

export async function fetchAccuracyStats(): Promise<BacktestStat[]> {
  const { data, error } = await supabase
    .from('backtest_stats')
    .select(
      'quote_code, horizon_days, model_selected, es_mae, naive_mae, mae_improvement_pct, calibration_coverage, sample_count',
    )
    .order('quote_code', { ascending: true })

  if (error) throw new Error(error.message)
  return (data ?? []) as BacktestStat[]
}
