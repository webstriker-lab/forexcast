import { useEffect, useState } from 'react'
import { fetchAccuracyStats, type BacktestStat } from '../lib/accuracyData'

export type StatsByHorizon = Map<number, BacktestStat[]>

export function useAccuracyStats() {
  const [statsByHorizon, setStatsByHorizon] = useState<StatsByHorizon>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchAccuracyStats()
      .then((rows) => {
        const grouped = new Map<number, BacktestStat[]>()
        for (const row of rows) {
          const existing = grouped.get(row.horizon_days) ?? []
          grouped.set(row.horizon_days, [...existing, row])
        }
        setStatsByHorizon(grouped)
        setError(null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [])

  return { statsByHorizon, loading, error }
}
