import { useEffect, useState, useCallback } from 'react'
import { supabase } from '../lib/supabaseClient'
import { useAuth } from '../contexts/AuthContext'

export interface SavingsGoal {
  id: string
  name: string
  target_currency: string
  target_amount: number
  current_saved: number
  target_date: string | null
  monthly_contribution: number | null
  is_active: boolean
  created_at: string
}

export function useSavingsGoals() {
  const { session } = useAuth()
  const [goals, setGoals] = useState<SavingsGoal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchGoals = useCallback(async () => {
    const { data, error: fetchError } = await supabase
      .from('savings_goals')
      .select('*')
      .order('created_at', { ascending: false })
    if (fetchError) {
      setError(fetchError.message)
    } else {
      setError(null)
      setGoals(data ?? [])
    }
    setLoading(false)
  }, [])

  useEffect(() => { fetchGoals() }, [fetchGoals])

  const createGoal = async (goal: Omit<SavingsGoal, 'id' | 'is_active' | 'created_at'>) => {
    if (!session) {
      setError('Not signed in')
      return false
    }
    const { error: insertError } = await supabase
      .from('savings_goals')
      .insert({ ...goal, user_id: session.user.id })
    if (insertError) {
      setError(insertError.message)
      return false
    }
    setError(null)
    await fetchGoals()
    return true
  }

  const updateGoal = async (id: string, data: Partial<SavingsGoal>) => {
    const { error: updateError } = await supabase.from('savings_goals').update(data).eq('id', id)
    if (updateError) {
      setError(updateError.message)
      return false
    }
    setError(null)
    await fetchGoals()
    return true
  }

  const deleteGoal = async (id: string) => {
    const { error: deleteError } = await supabase
      .from('savings_goals')
      .update({ is_active: false })
      .eq('id', id)
    if (deleteError) {
      setError(deleteError.message)
      return false
    }
    setError(null)
    await fetchGoals()
    return true
  }

  return { goals, loading, error, createGoal, updateGoal, deleteGoal }
}
