import { useEffect, useState, useCallback } from 'react'
import { supabase } from '../lib/supabaseClient'

export interface SavingsGoal {
  id: string
  name: string
  target_currency: string
  target_amount: number
  current_saved: number
  target_date: string | null
  is_active: boolean
  created_at: string
}

export function useSavingsGoals() {
  const [goals, setGoals] = useState<SavingsGoal[]>([])
  const [loading, setLoading] = useState(true)

  const fetchGoals = useCallback(async () => {
    const { data } = await supabase
      .from('savings_goals')
      .select('*')
      .order('created_at', { ascending: false })
    setGoals(data ?? [])
    setLoading(false)
  }, [])

  useEffect(() => { fetchGoals() }, [fetchGoals])

  const createGoal = async (goal: Omit<SavingsGoal, 'id' | 'is_active' | 'created_at'>) => {
    const { error } = await supabase.from('savings_goals').insert(goal)
    if (!error) await fetchGoals()
    return !error
  }

  const updateGoal = async (id: string, data: Partial<SavingsGoal>) => {
    const { error } = await supabase.from('savings_goals').update(data).eq('id', id)
    if (!error) await fetchGoals()
    return !error
  }

  const deleteGoal = async (id: string) => {
    const { error } = await supabase.from('savings_goals').update({ is_active: false }).eq('id', id)
    if (!error) await fetchGoals()
    return !error
  }

  return { goals, loading, createGoal, updateGoal, deleteGoal }
}
