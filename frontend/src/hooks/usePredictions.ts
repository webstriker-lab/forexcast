import { useEffect, useState } from 'react'
import { deriveCrossPredictions, invertPrediction, type RawPrediction } from '../lib/predictionMath'
import { fetchUsdLegPredictions, PIVOT } from '../lib/predictionsData'

export type Prediction = RawPrediction

export function usePredictions(base: string, quote: string) {
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!base || !quote) return
    let cancelled = false
    setLoading(true)
    setError(null)

    async function load() {
      try {
        let result: RawPrediction[]
        if (base === PIVOT) {
          result = await fetchUsdLegPredictions(quote)
        } else if (quote === PIVOT) {
          result = (await fetchUsdLegPredictions(base)).map(invertPrediction)
        } else {
          const [usdToBase, usdToQuote] = await Promise.all([
            fetchUsdLegPredictions(base),
            fetchUsdLegPredictions(quote),
          ])
          result = deriveCrossPredictions(usdToBase, usdToQuote)
        }

        if (cancelled) return
        setError(null)
        setPredictions([...result].sort((a, b) => a.horizon_days - b.horizon_days))
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : String(err))
        setPredictions([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [base, quote])

  return { predictions, loading, error }
}
