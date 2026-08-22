import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'

export interface RateRow {
  as_of: string
  rate: number
}

export function useRates(base: string, quote: string) {
  const [rates, setRates] = useState<RateRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!base || !quote) return
    setLoading(true)
    supabase
      .from('rates_cache')
      .select('as_of, rate')
      .eq('base_code', base)
      .eq('quote_code', quote)
      .order('as_of', { ascending: true })
      .then(({ data }) => {
        setRates(data ?? [])
        setLoading(false)
      })
  }, [base, quote])

  return { rates, loading }
}
