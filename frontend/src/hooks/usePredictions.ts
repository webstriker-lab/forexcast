import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'

export interface Prediction {
  horizon_days: number
  predicted_rate: number
  lower_bound: number
  upper_bound: number
  confidence: 'normal' | 'low'
  generated_at: string
}

export function usePredictions(base: string, quote: string) {
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!base || !quote) return
    let cancelled = false
    setLoading(true)
    setError(null)

    async function load() {
      // Mirror the backend's own get_latest_predictions: find the exact
      // latest generated_at first, then fetch only that batch -- pulling
      // every prediction row ever generated for the pair (unbounded, no
      // date filter) is both wasteful and, if the row cap is ever hit,
      // silently truncates to the OLDEST rows instead of the newest.
      const { data: latestRow, error: latestError } = await supabase
        .from('predictions')
        .select('generated_at')
        .eq('base_code', base)
        .eq('quote_code', quote)
        .order('generated_at', { ascending: false })
        .limit(1)
        .maybeSingle()

      if (cancelled) return
      if (latestError) {
        setError(latestError.message)
        setLoading(false)
        return
      }
      if (!latestRow) {
        setError(null)
        setPredictions([])
        setLoading(false)
        return
      }

      const { data, error: fetchError } = await supabase
        .from('predictions')
        .select('horizon_days, predicted_rate, lower_bound, upper_bound, confidence, generated_at')
        .eq('base_code', base)
        .eq('quote_code', quote)
        .eq('generated_at', latestRow.generated_at)

      if (cancelled) return
      if (fetchError) {
        setError(fetchError.message)
      } else {
        setError(null)
        setPredictions([...(data ?? [])].sort((a, b) => a.horizon_days - b.horizon_days))
      }
      setLoading(false)
    }

    load()
    return () => {
      cancelled = true
    }
  }, [base, quote])

  return { predictions, loading, error }
}
