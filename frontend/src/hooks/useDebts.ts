import { useEffect, useState, useCallback } from 'react'
import { supabase } from '../lib/supabaseClient'
import { useAuth } from '../contexts/AuthContext'

export interface Debt {
  id: string
  name: string
  currency_code: string
  original_amount: number
  current_balance: number
  interest_rate: number
  minimum_payment: number
  due_day: number | null
  is_active: boolean
  created_at: string
}

export function useDebts() {
  const { session } = useAuth()
  const [debts, setDebts] = useState<Debt[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchDebts = useCallback(async () => {
    const { data, error: fetchError } = await supabase
      .from('debts')
      .select('*')
      .order('created_at', { ascending: false })
    if (fetchError) {
      setError(fetchError.message)
    } else {
      setError(null)
      setDebts(data ?? [])
    }
    setLoading(false)
  }, [])

  useEffect(() => { fetchDebts() }, [fetchDebts])

  const createDebt = async (debt: Omit<Debt, 'id' | 'is_active' | 'created_at'>) => {
    if (!session) {
      setError('Not signed in')
      return false
    }
    const { error: insertError } = await supabase
      .from('debts')
      .insert({ ...debt, user_id: session.user.id })
    if (insertError) {
      setError(insertError.message)
      return false
    }
    setError(null)
    await fetchDebts()
    return true
  }

  const updateDebt = async (id: string, data: Partial<Debt>) => {
    const { error: updateError } = await supabase.from('debts').update(data).eq('id', id)
    if (updateError) {
      setError(updateError.message)
      return false
    }
    setError(null)
    await fetchDebts()
    return true
  }

  const deleteDebt = async (id: string) => {
    const { error: deleteError } = await supabase
      .from('debts')
      .update({ is_active: false })
      .eq('id', id)
    if (deleteError) {
      setError(deleteError.message)
      return false
    }
    setError(null)
    await fetchDebts()
    return true
  }

  return { debts, loading, error, createDebt, updateDebt, deleteDebt }
}
