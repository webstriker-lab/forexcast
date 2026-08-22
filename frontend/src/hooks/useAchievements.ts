import { useEffect, useState, useCallback } from 'react'
import { supabase } from '../lib/supabaseClient'
import { checkinStreak, getBadges } from '../lib/apiClient'

export interface Achievement {
  id: string
  badge_id: string
  earned_at: string
  metadata: Record<string, unknown> | null
}

export interface Badge {
  name: string
  emoji: string
  description: string
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
  const [badges, setBadges] = useState<Record<string, Badge>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    const [achievementsResult, streaksResult, badgesResult] = await Promise.all([
      supabase.from('achievements').select('*').order('earned_at', { ascending: false }),
      supabase.from('streaks').select('*').maybeSingle(),
      getBadges().catch((err: Error) => {
        setError(err.message)
        return {} as Record<string, Badge>
      }),
    ])

    if (achievementsResult.error) {
      setError(achievementsResult.error.message)
    } else {
      setAchievements(achievementsResult.data ?? [])
    }
    if (streaksResult.error) {
      setError(streaksResult.error.message)
    } else {
      // .maybeSingle() returns null both when the row genuinely doesn't
      // exist yet (a user who's never checked in) and would otherwise be
      // indistinguishable from "still loading" to StreakCounter, which
      // renders its loading state on any null streaks -- default to an
      // explicit zero-value object so a real, permanent zero state
      // renders instead of an infinite "Loading streaks...".
      setStreaks(
        streaksResult.data ?? {
          daily_checkin_current: 0,
          daily_checkin_best: 0,
          daily_checkin_last: null,
          savings_current: 0,
          savings_best: 0,
          savings_last: null,
          debt_payment_current: 0,
          debt_payment_best: 0,
          debt_payment_last: null,
        },
      )
    }
    setBadges(badgesResult)
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const recordCheckin = async () => {
    // Streak logic lives only in the backend (already correct, already
    // tested via update_streak in app.planner.achievements) -- this used
    // to reimplement it client-side, diverging in two ways: no same-day
    // guard, and "today" computed via UTC instead of the backend's
    // server-local date.
    try {
      await checkinStreak()
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Check-in failed')
    }
  }

  return { achievements, streaks, badges, loading, error, recordCheckin, refetch: fetchData }
}
