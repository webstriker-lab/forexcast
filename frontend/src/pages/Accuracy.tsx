import { useState } from 'react'
import { Layout } from '../components/Layout'
import { useAccuracyStats } from '../hooks/useAccuracyStats'
import type { BacktestStat } from '../lib/accuracyData'

const HORIZONS = [7, 30, 90, 365]
const HORIZON_LABELS: Record<number, string> = { 7: '7d', 30: '30d', 90: '90d', 365: '365d' }

function pct(n: number | null, decimals = 2): string {
  if (n === null) return '—'
  return `${(n * 100).toFixed(decimals)}%`
}

function ImprovementCell({ value }: { value: number | null }) {
  if (value === null || value <= 0) return <span className="text-gray-400">—</span>
  return <span className="text-green-700 font-medium">+{value.toFixed(1)}%</span>
}

function StatRow({ stat }: { stat: BacktestStat }) {
  const isES = stat.model_selected === 'exponential_smoothing'
  return (
    <tr className={isES ? 'bg-green-50' : 'bg-gray-50'}>
      <td className="px-4 py-2 text-sm font-medium text-gray-900">
        USD/{stat.quote_code}
      </td>
      <td className="px-4 py-2 text-sm text-gray-700">
        {isES ? 'ES' : 'Naive'}
      </td>
      <td className="px-4 py-2 text-sm text-gray-700">{pct(stat.es_mae)}</td>
      <td className="px-4 py-2 text-sm text-gray-700">{pct(stat.naive_mae)}</td>
      <td className="px-4 py-2 text-sm">
        <ImprovementCell value={stat.mae_improvement_pct} />
      </td>
      <td className="px-4 py-2 text-sm text-gray-700">
        {stat.calibration_coverage !== null
          ? `${(stat.calibration_coverage * 100).toFixed(0)}%`
          : '—'}
      </td>
      <td className="px-4 py-2 text-sm text-gray-500">{stat.sample_count}</td>
    </tr>
  )
}

export default function Accuracy() {
  const { statsByHorizon, loading, error } = useAccuracyStats()
  const [activeHorizon, setActiveHorizon] = useState(7)

  const rows = statsByHorizon.get(activeHorizon) ?? []
  const esBeatCount = rows.filter((r) => r.model_selected === 'exponential_smoothing').length
  const avgCalib =
    rows.length > 0
      ? rows.reduce((sum, r) => sum + (r.calibration_coverage ?? 0), 0) / rows.length
      : 0

  return (
    <Layout>
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Prediction Accuracy</h1>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center text-gray-400 py-12">Loading accuracy stats…</div>
        ) : (
          <>
            {/* Summary strip */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-800">
              <span className="font-semibold">
                {esBeatCount} of {rows.length} pairs
              </span>{' '}
              beat the naive baseline · avg calibration coverage:{' '}
              <span className="font-semibold">{(avgCalib * 100).toFixed(0)}%</span>
            </div>

            {/* Horizon tabs */}
            <div className="flex gap-2">
              {HORIZONS.map((h) => (
                <button
                  key={h}
                  onClick={() => setActiveHorizon(h)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeHorizon === h
                      ? 'bg-blue-600 text-white'
                      : 'bg-white text-gray-600 border border-gray-200 hover:border-blue-300'
                  }`}
                >
                  {HORIZON_LABELS[h]}
                </button>
              ))}
            </div>

            {/* Table */}
            <div className="bg-white rounded-lg shadow overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-gray-200">
                    {['Pair', 'Model', 'ES MAE', 'Naive MAE', 'Improvement', 'Calibration', 'Samples'].map(
                      (h) => (
                        <th
                          key={h}
                          className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide"
                        >
                          {h}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {rows.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-gray-400 text-sm">
                        No backtest stats available yet. Run the weekly backtest job to populate
                        this page.
                      </td>
                    </tr>
                  ) : (
                    rows.map((stat) => <StatRow key={stat.quote_code} stat={stat} />)
                  )}
                </tbody>
              </table>
            </div>

            <p className="text-xs text-gray-400 text-center">
              ⚠️ Calibration coverage is in-sample (~80% expected). MAE is mean absolute % error
              across rolling backtest origins.
            </p>
          </>
        )}
      </div>
    </Layout>
  )
}
