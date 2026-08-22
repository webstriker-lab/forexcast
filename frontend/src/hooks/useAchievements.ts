import { useEffect, useState, useCallback } from 'react'
import { supabase } from '../lib/supabaseClient'

export interface Achievement {
  id: string
  badge_id: string
  badge_name: string
  badge_emoji: string
  earned_at: string
  metadata: Record<string, unknown> | null
}

export interface Streaks {
  daily_checkin_current: number
  daily_checkin_best: number
  daily_checkin_last: string | null
  savings_current: number
  savings_best: number
  savings_last: string | null
  debt_payment_current: number
  debt_payment_best: number
  debt_payment_last: string | null
}

export function useAchievements() {
  const [achievements, setAchievements] = useState<Achievement[]>([])
  const [streaks, setStreaks] = useState<Streaks | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    const [achievementsResult, streaksResult] = await Promise.all([
      supabase.from('achievements').select('*').order('earned_at', { ascending: false }),
      supabase.from('streaks').select('*').single(),
    ])
    
    setAchievements(achievementsResult.data ?? [])
    setStreaks(streaksResult.data)
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const recordCheckin = async () => {
    // Update streak
    const today = new Date().toISOString().split('T')[0]
    const { data: currentStreaks } = await supabase
      .from('streaks')
      .select('*')
      .single()

    const lastCheckin = currentStreaks?.daily_checkin_last
    const isConsecutive = lastCheckin === new Date(Date.now() - 86400000).toISOString().split('T')[0]
    
    const newStreak = {
      daily_checkin_current: isConsecutive ? (currentStreaks?.daily_checkin_current || 0) + 1 : 1,
      daily_checkin_best: Math.max(
        currentStreaks?.daily_checkin_best || 0,
        isConsecutive ? (currentStreaks?.daily_checkin_current || 0) + 1 : 1
      ),
      daily_checkin_last: today,
    }

    await supabase.from('streaks').upsert(newStreak, { onConflict: 'user_id' })
    await fetchData()
  }

  return { achievements, streaks, loading, recordCheckin, refetch: fetchData }
}
