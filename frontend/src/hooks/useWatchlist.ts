import { useEffect, useState, useCallback, useRef } from 'react'
import { supabase } from '../lib/supabaseClient'
import { useAuth } from '../contexts/AuthContext'

export interface CurrencyPair {
  base_code: string
  quote_code: string
}

export function useWatchlist() {
  const { session } = useAuth()
  const [pairs, setPairs] = useState<CurrencyPair[]>([])
  const [selected, setSelected] = useState<CurrencyPair | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Read inside fetchWatchlist via a ref rather than a dependency -- this
  // avoids re-fetching the whole watchlist every time the user just picks
  // a different already-loaded pair (selected changing is not a reason to
  // hit the network again).
  const selectedRef = useRef(selected)
  selectedRef.current = selected

  const fetchWatchlist = useCallback(async () => {
    const { data, error: fetchError } = await supabase
      .from('watchlist')
      .select('base_code, quote_code')
      .order('created_at', { ascending: false })

    if (fetchError) {
      setError(fetchError.message)
    } else if (data) {
      setError(null)
      setPairs(data)
      if (data.length > 0 && !selectedRef.current) setSelected(data[0])
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchWatchlist()
  }, [fetchWatchlist])

  const addPair = async (base: string, quote: string) => {
    if (!session) {
      setError('Not signed in')
      return false
    }
    const { error: insertError } = await supabase
      .from('watchlist')
      .insert({ base_code: base, quote_code: quote, user_id: session.user.id })
    if (insertError) {
      // Unique constraint violation = pair already in watchlist
      if (insertError.code === '23505') {
        setError(`${base}/${quote} is already in your watchlist`)
      } else {
        setError(insertError.message)
      }
      return false
    }
    setError(null)
    await fetchWatchlist()
    return true
  }

  const removePair = async (base: string, quote: string) => {
    const { error: deleteError } = await supabase
      .from('watchlist')
      .delete()
      .match({ base_code: base, quote_code: quote })
    if (deleteError) {
      setError(deleteError.message)
      return
    }
    if (selected?.base_code === base && selected?.quote_code === quote) {
      setSelected(null)
    }
    await fetchWatchlist()
  }

  return { pairs, selected, setSelected, addPair, removePair, loading, error }
}
