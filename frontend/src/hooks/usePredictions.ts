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

  useEffect(() => {
    if (!base || !quote) return
    setLoading(true)
    supabase
      .from('predictions')
      .select('horizon_days, predicted_rate, lower_bound, upper_bound, confidence, generated_at')
      .eq('base_code', base)
      .eq('quote_code', quote)
      .order('generated_at', { ascending: false })
      .then(({ data }) => {
        // Keep only the latest batch per horizon
        const latest = new Map<number, Prediction>()
        for (const row of data ?? []) {
          if (!latest.has(row.horizon_days)) latest.set(row.horizon_days, row)
        }
        setPredictions([...latest.values()].sort((a, b) => a.horizon_days - b.horizon_days))
        setLoading(false)
      })
  }, [base, quote])

  return { predictions, loading }
}
