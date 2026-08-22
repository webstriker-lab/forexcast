import { useEffect, useState } from 'react'
import { Layout } from '../components/Layout'
import { MascotWidget } from '../components/MascotWidget'
import { StreakCounter } from '../components/StreakCounter'
import { BadgeGrid } from '../components/BadgeGrid'
import { useDebts } from '../hooks/useDebts'
import { useSavingsGoals } from '../hooks/useSavingsGoals'
import { useAchievements } from '../hooks/useAchievements'
import { getDebtTimeline } from '../lib/apiClient'
import { supabase } from '../lib/supabaseClient'
import { Link } from 'react-router-dom'

export default function Planner() {
  const { debts, loading: debtsLoading } = useDebts()
  const { goals, loading: goalsLoading } = useSavingsGoals()
  const { achievements, streaks, badges, loading: achievementsLoading, recordCheckin } = useAchievements()

  const activeDebts = debts.filter(d => d.is_active)
  const activeGoals = goals.filter(g => g.is_active)

  // Debts and goals can each be in any of 12 currencies -- a raw sum across
  // them is meaningless, so both totals are converted to USD before
  // summing, the same way DebtManager/get_debt_timeline already does for
  // the dedicated debt page.
  const [totalDebt, setTotalDebt] = useState<number | null>(null)
  const [totalSaved, setTotalSaved] = useState<number | null>(null)

  useEffect(() => {
    getDebtTimeline()
      .then(res => setTotalDebt(res.summary.total_balance))
      .catch(() => setTotalDebt(null))
  }, [debts])

  useEffect(() => {
    if (activeGoals.length === 0) {
      setTotalSaved(0)
      return
    }
    let cancelled = false
    const currencies = [...new Set(activeGoals.map(g => g.target_currency))].filter(c => c !== 'USD')

    async function loadRatesAndSum() {
      const rateByCurrency = new Map<string, number>()
      if (currencies.length > 0) {
        const { data } = await supabase
          .from('rates_cache')
          .select('quote_code, rate, as_of')
          .eq('base_code', 'USD')
          .in('quote_code', currencies)
          .order('as_of', { ascending: false })
        for (const row of data ?? []) {
          if (!rateByCurrency.has(row.quote_code)) rateByCurrency.set(row.quote_code, row.rate)
        }
      }
      if (cancelled) return
      const sum = activeGoals.reduce((acc, g) => {
        const rate = g.target_currency === 'USD' ? 1 : rateByCurrency.get(g.target_currency)
        return rate ? acc + g.current_saved / rate : acc
      }, 0)
      setTotalSaved(sum)
    }

    loadRatesAndSum()
    return () => {
      cancelled = true
    }
  }, [goals])

  if (debtsLoading || goalsLoading || achievementsLoading) {
    return (
      <Layout>
        <div className="text-center text-gray-400 py-12">Loading...</div>
      </Layout>
    )
  }

  return (
    <Layout>
      <div className="space-y-6">
        {/* Mascot */}
        <MascotWidget context="welcome" />

        {/* Quick Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Link to="/planner/debts" className="bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow">
            <p className="text-sm text-gray-500">Total Debt (USD)</p>
            <p className="text-2xl font-bold text-red-600">
              {totalDebt !== null ? `$${totalDebt.toLocaleString()}` : '—'}
            </p>
            <p className="text-xs text-gray-400">{activeDebts.length} active debts</p>
          </Link>
          <Link to="/planner/goals" className="bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow">
            <p className="text-sm text-gray-500">Total Saved (USD)</p>
            <p className="text-2xl font-bold text-green-600">
              {totalSaved !== null ? `$${totalSaved.toLocaleString()}` : '—'}
            </p>
            <p className="text-xs text-gray-400">{activeGoals.length} active goals</p>
          </Link>
          <div className="bg-white rounded-lg shadow p-4">
            <p className="text-sm text-gray-500">Achievements</p>
            <p className="text-2xl font-bold">{achievements.length}</p>
            <p className="text-xs text-gray-400">badges earned</p>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <p className="text-sm text-gray-500">Check-in Streak</p>
            <p className="text-2xl font-bold">{streaks?.daily_checkin_current || 0} 🔥</p>
            <p className="text-xs text-gray-400">days in a row</p>
          </div>
        </div>

        {/* Streaks */}
        <StreakCounter streaks={streaks} onCheckin={recordCheckin} />

        {/* Recent Achievements */}
        <div>
          <h2 className="text-xl font-bold mb-4">Achievements</h2>
          <BadgeGrid achievements={achievements} badges={badges} />
        </div>

        {/* Quick Actions */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">Quick Actions</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Link
              to="/planner/debts"
              className="px-4 py-3 bg-red-50 text-red-700 rounded-lg hover:bg-red-100 text-center font-medium"
            >
              💳 Manage Debts
            </Link>
            <Link
              to="/planner/goals"
              className="px-4 py-3 bg-green-50 text-green-700 rounded-lg hover:bg-green-100 text-center font-medium"
            >
              🎯 Savings Goals
            </Link>
            <Link
              to="/planner/achievements"
              className="px-4 py-3 bg-yellow-50 text-yellow-700 rounded-lg hover:bg-yellow-100 text-center font-medium"
            >
              🏆 View All Badges
            </Link>
          </div>
        </div>
      </div>
    </Layout>
  )
}
