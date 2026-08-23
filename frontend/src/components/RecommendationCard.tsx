import type { Recommendation } from '../hooks/useRecommendations'
import type { RecommendationInsights } from '../lib/apiClient'

const STYLES = {
  act_now: { bg: 'bg-green-50 border-green-200', badge: 'bg-green-100 text-green-800', label: 'ACT NOW', emoji: '\uD83D\uDFE2' },
  wait: { bg: 'bg-yellow-50 border-yellow-200', badge: 'bg-yellow-100 text-yellow-800', label: 'WAIT', emoji: '\uD83D\uDFE1' },
  volatile: { bg: 'bg-red-50 border-red-200', badge: 'bg-red-100 text-red-800', label: 'VOLATILE', emoji: '\uD83D\uDD34' },
  // Deliberately neutral gray -- no directional edge for this pair; never reads as a confident call to act.
  no_signal: { bg: 'bg-gray-50 border-gray-200', badge: 'bg-gray-100 text-gray-700', label: 'NO SIGNAL', emoji: '\u26AA' },
}

interface Props {
  rec: Recommendation | null
  pair: string
  insights?: RecommendationInsights | null
}

export function RecommendationCard({ rec, pair, insights }: Props) {
  // Sentiment modifier: flip no_signal when statistical result is no_signal AND |score| > 0.4
  const effectiveRec = (() => {
    if (!rec || rec.recommendation !== 'no_signal') return rec
    const score = insights?.sentiment?.score
    if (score === undefined || score === null) return rec
    if (score < -0.4) return { ...rec, recommendation: 'act_now' as const }
    if (score > 0.4) return { ...rec, recommendation: 'wait' as const }
    return rec
  })()

  if (!effectiveRec) {
    return (
      <div className="p-4 bg-white rounded-lg shadow text-center space-y-1">
        <p className="text-gray-500 font-medium">No forecast data yet for {pair}</p>
        <p className="text-gray-400 text-sm">
          The weekly backtest job populates predictions \u2014 check back after the next scheduled run.
        </p>
      </div>
    )
  }

  const style = STYLES[effectiveRec.recommendation]

  const direction = effectiveRec.recommendation === 'wait' ? 'higher' : 'lower or flat'
  const sentimentLine = insights?.sentiment
    ? ` News sentiment: ${insights.sentiment.score >= 0 ? 'positive' : 'negative'} (${insights.sentiment.score.toFixed(2)}) \u2014 ${insights.sentiment.summary}`
    : ''
  const reasoning = `The ${effectiveRec.reference_horizon_days}-day forecast predicts ${effectiveRec.expected_rate.toFixed(4)} (${direction} from current ${effectiveRec.current_rate.toFixed(4)}).${sentimentLine}`

  return (
    <div className={`p-4 rounded-lg border ${style.bg}`}>
      {insights?.requires_llm_setup && (
        <div className="mb-3 text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded px-3 py-2">
          Add an LLM key in Settings to unlock news-aware recommendations.
        </div>
      )}
      <div className="flex items-center justify-between mb-3">
        <span className="font-semibold text-lg">{pair}</span>
        <span className={`px-3 py-1 rounded-full text-sm font-bold ${style.badge}`}>
          {style.emoji} {style.label}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-gray-500">Current:</span>{' '}
          <span className="font-medium">{effectiveRec.current_rate.toFixed(4)}</span>
        </div>
        <div>
          <span className="text-gray-500">Expected ({effectiveRec.reference_horizon_days}d):</span>{' '}
          <span className="font-medium">{effectiveRec.expected_rate.toFixed(4)}</span>
        </div>
        <div>
          <span className="text-gray-500">Range:</span>{' '}
          <span className="font-medium">{effectiveRec.lower_bound.toFixed(4)} \u2013 {effectiveRec.upper_bound.toFixed(4)}</span>
        </div>
        <div>
          <span className="text-gray-500">Updated:</span>{' '}
          <span className="font-medium">{new Date(effectiveRec.generated_at).toLocaleDateString()}</span>
        </div>
      </div>
      {effectiveRec.recommendation === 'no_signal' && (
        <p className="text-xs text-gray-500 mt-3">
          The backtested model has no directional edge for this pair right now \u2014 the range above is
          the honest historical spread, not a forecasted move.
        </p>
      )}
      <p className="text-xs text-gray-500 mt-3 italic">{reasoning}</p>
    </div>
  )
}
