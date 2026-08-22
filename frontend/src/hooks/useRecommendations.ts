import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'

export interface Recommendation {
  recommendation: 'act_now' | 'wait' | 'volatile'
  current_rate: number
  expected_rate: number
  lower_bound: number
  upper_bound: number
  reference_horizon_days: number
  generated_at: string
}

export function useRecommendations(base: string, quote: string) {
  const [rec, setRec] = useState<Recommendation | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!base || !quote) return
    setLoading(true)
    supabase
      .from('recommendations')
      .select('recommendation, current_rate, expected_rate, lower_bound, upper_bound, reference_horizon_days, generated_at')
      .eq('base_code', base)
      .eq('quote_code', quote)
      .order('generated_at', { ascending: false })
      .limit(1)
      .single()
      .then(({ data }) => {
        setRec(data)
        setLoading(false)
      })
  }, [base, quote])

  return { rec, loading }
}
