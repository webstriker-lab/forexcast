import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import { chooseRecommendation, deriveCrossPredictions } from '../lib/predictionMath'
import { fetchCurrentRate, fetchUsdLegPredictions, PIVOT } from '../lib/predictionsData'

export interface Recommendation {
  recommendation: 'act_now' | 'wait' | 'volatile'
  current_rate: number
  expected_rate: number
  lower_bound: number
  upper_bound: number
  reference_horizon_days: number
  generated_at: string
}

// recommendations only ever gets written for USD-pivot pairs (both
// directions -- see backend/app/recommendations/jobs.py), so a cross pair
// like INR->EUR has no row to fetch. It's derived here from the two
// USD-pivot legs' predictions plus the pair's own current rate, the same
// approach usePredictions uses -- refitting the ML model per cross pair
// isn't practical (29*28 combinations).
async function deriveCrossRecommendation(base: string, quote: string): Promise<Recommendation | null> {
  const [usdToBase, usdToQuote, currentRate] = await Promise.all([
    fetchUsdLegPredictions(base),
    fetchUsdLegPredictions(quote),
    fetchCurrentRate(base, quote),
  ])
  const horizons = deriveCrossPredictions(usdToBase, usdToQuote)
  if (horizons.length === 0 || currentRate === null) return null

  const chosen = chooseRecommendation(currentRate, horizons)
  const generatedAt = [...usdToBase, ...usdToQuote].reduce(
    (oldest, p) => (p.generated_at < oldest ? p.generated_at : oldest),
    horizons[0].generated_at,
  )
  return { ...chosen, generated_at: generatedAt }
}

async function fetchDirectRecommendation(base: string, quote: string): Promise<Recommendation | null> {
  const { data, error } = await supabase
    .from('recommendations')
    .select('recommendation, current_rate, expected_rate, lower_bound, upper_bound, reference_horizon_days, generated_at')
    .eq('base_code', base)
    .eq('quote_code', quote)
    .order('generated_at', { ascending: false })
    .limit(1)
    .maybeSingle()

  if (error) throw new Error(error.message)
  return data
}

export function useRecommendations(base: string, quote: string) {
  const [rec, setRec] = useState<Recommendation | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!base || !quote) return
    let cancelled = false
    setLoading(true)
    setError(null)

    async function load() {
      try {
        const result =
          base === PIVOT || quote === PIVOT
            ? await fetchDirectRecommendation(base, quote)
            : await deriveCrossRecommendation(base, quote)

        if (cancelled) return
        setError(null)
        setRec(result)
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : String(err))
        setRec(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [base, quote])

  return { rec, loading, error }
}
