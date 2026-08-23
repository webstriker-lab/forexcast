import { useState } from 'react'
import { interpolatePrediction, type InterpolatedPrediction } from '../lib/predictionMath'
import { DatePredictionCard } from '../components/DatePredictionCard'
import { useWatchlist } from '../hooks/useWatchlist'
import { useRates } from '../hooks/useRates'
import { usePredictions } from '../hooks/usePredictions'
import { useRecommendations } from '../hooks/useRecommendations'
import { PairPicker } from '../components/PairPicker'
import { RateChart } from '../components/RateChart'
import { RecommendationCard } from '../components/RecommendationCard'
import { Layout } from '../components/Layout'

export default function Dashboard() {
  const {
    pairs,
    selected,
    setSelected,
    addPair,
    removePair,
    loading: watchlistLoading,
    error: watchlistError,
  } = useWatchlist()
  const base = selected?.base_code ?? ''
  const quote = selected?.quote_code ?? ''
  const { rates, loading: ratesLoading, error: ratesError } = useRates(base, quote)
  const { predictions, loading: predLoading, error: predError } = usePredictions(base, quote)
  const { rec, loading: recLoading, error: recError } = useRecommendations(base, quote)

  const pair = base && quote ? `${base}/${quote}` : ''
  const error = watchlistError || ratesError || predError || recError

  const [targetDate, setTargetDate] = useState('')

  const todayStr = new Date().toISOString().split('T')[0]
  const maxDateStr = (() => {
    const d = new Date()
    d.setDate(d.getDate() + 365)
    return d.toISOString().split('T')[0]
  })()

  const interpolated: InterpolatedPrediction | null = (() => {
    if (!targetDate || predictions.length === 0) return null
    const ms = new Date(targetDate).getTime() - Date.now()
    const targetDays = Math.max(1, Math.round(ms / 86400000))
    return interpolatePrediction(predictions, targetDays)
  })()

  return (
    <Layout>
      <div className="space-y-6">
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
            {error}
          </div>
        )}

        {/* Pair picker */}
        <PairPicker
          pairs={pairs}
          selected={selected}
          onSelect={setSelected}
          onAdd={addPair}
          onRemove={removePair}
        />

        {watchlistLoading ? (
          <div className="text-center text-gray-400 py-12">Loading...</div>
        ) : !selected ? (
          <div className="text-center text-gray-400 py-12">
            <p className="text-lg">Add a currency pair to get started</p>
            <p className="text-sm mt-1">Select two currencies above and click "+ Add"</p>
          </div>
        ) : (
          <>
            {/* Recommendation */}
            {recLoading ? (
              <div className="h-24 bg-white rounded-lg shadow animate-pulse" />
            ) : (
              <RecommendationCard rec={rec} pair={pair} />
            )}

            {/* Date prediction */}
            {!predLoading && (
              <div className="bg-white rounded-lg shadow p-4 space-y-3">
                <p className="text-sm font-medium text-gray-700">Predict for a specific date</p>
                <div className="flex items-center gap-3">
                  <input
                    type="date"
                    value={targetDate}
                    min={(() => { const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().split('T')[0] })()}
                    max={maxDateStr}
                    onChange={(e) => setTargetDate(e.target.value)}
                    className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  {targetDate && (
                    <button
                      onClick={() => setTargetDate('')}
                      className="text-sm text-gray-500 hover:text-gray-700"
                    >
                      Clear
                    </button>
                  )}
                </div>
                {interpolated && (
                  <DatePredictionCard prediction={interpolated} pair={pair} targetDate={targetDate} />
                )}
              </div>
            )}

            {/* Chart */}
            {ratesLoading || predLoading ? (
              <div className="h-80 bg-white rounded-lg shadow animate-pulse flex items-center justify-center text-gray-400">
                Loading chart...
              </div>
            ) : (
              <RateChart rates={rates} predictions={predictions} pair={pair} />
            )}

            {/* Disclaimer */}
            <p className="text-xs text-gray-400 text-center">
              ⚠️ Not financial advice. Forecasts are statistical estimates, not guarantees.
            </p>
          </>
        )}
      </div>
    </Layout>
  )
}
