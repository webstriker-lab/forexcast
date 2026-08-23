import { useEffect, useState } from 'react'
import { fetchRecommendationInsights, type RecommendationInsights } from '../lib/apiClient'

export function useRecommendationInsights(base: string, quote: string) {
  const [insights, setInsights] = useState<RecommendationInsights | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!base || !quote) return
    let cancelled = false
    setLoading(true)
    setError(null)

    fetchRecommendationInsights(base, quote)
      .then((data) => { if (!cancelled) { setInsights(data); setLoading(false) } })
      .catch((err) => { if (!cancelled) { setError(err instanceof Error ? err.message : String(err)); setLoading(false) } })

    return () => { cancelled = true }
  }, [base, quote])

  return { insights, loading, error }
}
