import { supabase } from './supabaseClient'
import type { RawPrediction } from './predictionMath'

export const PIVOT = 'USD'

// Fetches the latest USD->code prediction batch. Mirrors the backend's own
// get_latest_predictions: find the exact latest generated_at first, then
// fetch only that batch -- pulling every prediction row ever generated
// (unbounded, no date filter) is both wasteful and, if the row cap is
// ever hit, silently truncates to the OLDEST rows instead of the newest.
export async function fetchUsdLegPredictions(code: string): Promise<RawPrediction[]> {
  const { data: latestRow, error: latestError } = await supabase
    .from('predictions')
    .select('generated_at')
    .eq('base_code', PIVOT)
    .eq('quote_code', code)
    .order('generated_at', { ascending: false })
    .limit(1)
    .maybeSingle()

  if (latestError) throw new Error(latestError.message)
  if (!latestRow) return []

  const { data, error } = await supabase
    .from('predictions')
    .select('horizon_days, predicted_rate, lower_bound, upper_bound, confidence, generated_at')
    .eq('base_code', PIVOT)
    .eq('quote_code', code)
    .eq('generated_at', latestRow.generated_at)

  if (error) throw new Error(error.message)
  return data ?? []
}

// Latest materialized rate for an exact (base, quote) direction from
// rates_cache -- used as the "current rate" when deriving a cross-pair
// recommendation, so it matches exactly what the rate chart already shows
// for that pair instead of re-deriving it a second, possibly divergent way.
export async function fetchCurrentRate(base: string, quote: string): Promise<number | null> {
  const { data, error } = await supabase
    .from('rates_cache')
    .select('rate')
    .eq('base_code', base)
    .eq('quote_code', quote)
    .order('as_of', { ascending: false })
    .limit(1)
    .maybeSingle()

  if (error) throw new Error(error.message)
  return data?.rate ?? null
}
