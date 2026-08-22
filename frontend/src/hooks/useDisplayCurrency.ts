import { useCallback, useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import { useAuth } from '../contexts/AuthContext'

export function useDisplayCurrency() {
  const { session } = useAuth()
  const [currency, setCurrencyState] = useState('USD')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!session) {
      setLoading(false)
      return
    }
    const { data, error: fetchError } = await supabase
      .from('user_preferences')
      .select('display_currency')
      .maybeSingle()
    if (fetchError) {
      setError(fetchError.message)
    } else {
      setError(null)
      setCurrencyState(data?.display_currency ?? 'USD')
    }
    setLoading(false)
  }, [session])

  useEffect(() => {
    load()
  }, [load])

  const setCurrency = async (newCurrency: string) => {
    if (!session) return false
    const { error: upsertError } = await supabase
      .from('user_preferences')
      .upsert(
        { user_id: session.user.id, display_currency: newCurrency, updated_at: new Date().toISOString() },
        { onConflict: 'user_id' },
      )
    if (upsertError) {
      setError(upsertError.message)
      return false
    }
    setError(null)
    setCurrencyState(newCurrency)
    return true
  }

  return { currency, setCurrency, loading, error }
}
