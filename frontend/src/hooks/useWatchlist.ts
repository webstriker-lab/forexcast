import { useEffect, useState, useCallback } from 'react'
import { supabase } from '../lib/supabaseClient'

export interface CurrencyPair {
  base_code: string
  quote_code: string
}

export function useWatchlist() {
  const [pairs, setPairs] = useState<CurrencyPair[]>([])
  const [selected, setSelected] = useState<CurrencyPair | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchWatchlist = useCallback(async () => {
    const { data, error } = await supabase
      .from('watchlist')
      .select('base_code, quote_code')
      .order('created_at', { ascending: false })

    if (!error && data) {
      setPairs(data)
      if (data.length > 0 && !selected) setSelected(data[0])
    }
    setLoading(false)
  }, [selected])

  useEffect(() => {
    fetchWatchlist()
  }, [fetchWatchlist])

  const addPair = async (base: string, quote: string) => {
    const { error } = await supabase
      .from('watchlist')
      .insert({ base_code: base, quote_code: quote })
    if (!error) {
      await fetchWatchlist()
    }
    return !error
  }

  const removePair = async (base: string, quote: string) => {
    await supabase
      .from('watchlist')
      .delete()
      .match({ base_code: base, quote_code: quote })
    if (selected?.base_code === base && selected?.quote_code === quote) {
      setSelected(null)
    }
    await fetchWatchlist()
  }

  return { pairs, selected, setSelected, addPair, removePair, loading }
}
