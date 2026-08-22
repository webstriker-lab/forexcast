import { useEffect, useState, useCallback } from 'react'
import { supabase } from '../lib/supabaseClient'

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
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)

  const fetchAlerts = useCallback(async () => {
    const { data } = await supabase
      .from('alerts')
      .select('*')
      .order('created_at', { ascending: false })
    setAlerts(data ?? [])
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchAlerts()
  }, [fetchAlerts])

  const createAlert = async (alert: Omit<Alert, 'id' | 'is_active' | 'created_at'>) => {
    const { error } = await supabase.from('alerts').insert(alert)
    if (!error) await fetchAlerts()
    return !error
  }

  const toggleAlert = async (id: string, isActive: boolean) => {
    await supabase.from('alerts').update({ is_active: isActive }).eq('id', id)
    await fetchAlerts()
  }

  const deleteAlert = async (id: string) => {
    await supabase.from('alerts').delete().eq('id', id)
    await fetchAlerts()
  }

  return { alerts, loading, createAlert, toggleAlert, deleteAlert }
}
