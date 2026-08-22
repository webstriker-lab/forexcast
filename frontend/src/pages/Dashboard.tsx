import { useWatchlist } from '../hooks/useWatchlist'
import { useRates } from '../hooks/useRates'
import { usePredictions } from '../hooks/usePredictions'
import { useRecommendations } from '../hooks/useRecommendations'
import { PairPicker } from '../components/PairPicker'
import { RateChart } from '../components/RateChart'
import { RecommendationCard } from '../components/RecommendationCard'
import { Layout } from '../components/Layout'

export default function Dashboard() {
  const { pairs, selected, setSelected, addPair, removePair, loading: watchlistLoading } = useWatchlist()
  const base = selected?.base_code ?? ''
  const quote = selected?.quote_code ?? ''
  const { rates, loading: ratesLoading } = useRates(base, quote)
  const { predictions, loading: predLoading } = usePredictions(base, quote)
  const { rec, loading: recLoading } = useRecommendations(base, quote)

  const pair = base && quote ? `${base}/${quote}` : ''

  return (
    <Layout>
      <div className="space-y-6">
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
