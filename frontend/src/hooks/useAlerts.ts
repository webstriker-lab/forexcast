import { useEffect, useState, useCallback } from 'react'
import { supabase } from '../lib/supabaseClient'
import { useAuth } from '../contexts/AuthContext'

export interface Alert {
  id: string
  base_code: string
  quote_code: string
  alert_type: 'threshold' | 'recommendation_change'
  threshold_rate: number | null
  direction: 'above' | 'below' | null
  is_active: boolean
  created_at: string
}

export function useAlerts() {
  const { session } = useAuth()
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAlerts = useCallback(async () => {
    const { data, error: fetchError } = await supabase
      .from('alerts')
      .select('*')
      .order('created_at', { ascending: false })
    if (fetchError) {
      setError(fetchError.message)
    } else {
      setError(null)
      setAlerts(data ?? [])
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchAlerts()
  }, [fetchAlerts])

  const createAlert = async (alert: Omit<Alert, 'id' | 'is_active' | 'created_at'>) => {
    if (!session) {
      setError('Not signed in')
      return false
    }
    const { error: insertError } = await supabase
      .from('alerts')
      .insert({ ...alert, user_id: session.user.id })
    if (insertError) {
      setError(insertError.message)
      return false
    }
    setError(null)
    await fetchAlerts()
    return true
  }

  const toggleAlert = async (id: string, isActive: boolean) => {
    const { error: updateError } = await supabase
      .from('alerts')
      .update({ is_active: isActive })
      .eq('id', id)
    if (updateError) {
      setError(updateError.message)
      return
    }
    await fetchAlerts()
  }

  const deleteAlert = async (id: string) => {
    const { error: deleteError } = await supabase.from('alerts').delete().eq('id', id)
    if (deleteError) {
      setError(deleteError.message)
      return
    }
    await fetchAlerts()
  }

  return { alerts, loading, error, createAlert, toggleAlert, deleteAlert }
}
