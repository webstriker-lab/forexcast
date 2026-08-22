import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'

export interface RateRow {
  as_of: string
  rate: number
}

const HISTORY_DAYS = 365

export function useRates(base: string, quote: string) {
  const [rates, setRates] = useState<RateRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!base || !quote) return
    let cancelled = false
    setLoading(true)
    setError(null)

    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - HISTORY_DAYS)

    supabase
      .from('rates_cache')
      .select('as_of, rate')
      .eq('base_code', base)
      .eq('quote_code', quote)
      .gte('as_of', cutoff.toISOString().slice(0, 10))
      .order('as_of', { ascending: true })
      .then(({ data, error: fetchError }) => {
        // A pair switch fired a newer request before this one resolved --
        // discard this stale result so it can't overwrite the current pair's
        // data with a different pair's rates.
        if (cancelled) return
        if (fetchError) {
          setError(fetchError.message)
        } else {
          setError(null)
          setRates(data ?? [])
        }
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [base, quote])

  return { rates, loading, error }
}
