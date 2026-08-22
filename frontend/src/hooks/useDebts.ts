import { useEffect, useState, useCallback } from 'react'
import { supabase } from '../lib/supabaseClient'

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
  const [debts, setDebts] = useState<Debt[]>([])
  const [loading, setLoading] = useState(true)

  const fetchDebts = useCallback(async () => {
    const { data } = await supabase
      .from('debts')
      .select('*')
      .order('created_at', { ascending: false })
    setDebts(data ?? [])
    setLoading(false)
  }, [])

  useEffect(() => { fetchDebts() }, [fetchDebts])

  const createDebt = async (debt: Omit<Debt, 'id' | 'is_active' | 'created_at'>) => {
    const { error } = await supabase.from('debts').insert(debt)
    if (!error) await fetchDebts()
    return !error
  }

  const updateDebt = async (id: string, data: Partial<Debt>) => {
    const { error } = await supabase.from('debts').update(data).eq('id', id)
    if (!error) await fetchDebts()
    return !error
  }

  const deleteDebt = async (id: string) => {
    const { error } = await supabase.from('debts').update({ is_active: false }).eq('id', id)
    if (!error) await fetchDebts()
    return !error
  }

  return { debts, loading, createDebt, updateDebt, deleteDebt }
}
