import type { Recommendation } from '../hooks/useRecommendations'

const STYLES = {
  act_now: { bg: 'bg-green-50 border-green-200', badge: 'bg-green-100 text-green-800', label: 'ACT NOW', emoji: '🟢' },
  wait: { bg: 'bg-yellow-50 border-yellow-200', badge: 'bg-yellow-100 text-yellow-800', label: 'WAIT', emoji: '🟡' },
  volatile: { bg: 'bg-red-50 border-red-200', badge: 'bg-red-100 text-red-800', label: 'VOLATILE', emoji: '🔴' },
}

interface Props {
  rec: Recommendation | null
  pair: string
}

export function RecommendationCard({ rec, pair }: Props) {
  if (!rec) {
    return (
      <div className="p-4 bg-white rounded-lg shadow text-gray-400 text-center">
        No recommendation available for {pair}
      </div>
    )
  }

  const style = STYLES[rec.recommendation]

  return (
    <div className={`p-4 rounded-lg border ${style.bg}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="font-semibold text-lg">{pair}</span>
        <span className={`px-3 py-1 rounded-full text-sm font-bold ${style.badge}`}>
          {style.emoji} {style.label}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-gray-500">Current:</span>{' '}
          <span className="font-medium">{rec.current_rate.toFixed(4)}</span>
        </div>
        <div>
          <span className="text-gray-500">Expected ({rec.reference_horizon_days}d):</span>{' '}
          <span className="font-medium">{rec.expected_rate.toFixed(4)}</span>
        </div>
        <div>
          <span className="text-gray-500">Range:</span>{' '}
          <span className="font-medium">{rec.lower_bound.toFixed(4)} – {rec.upper_bound.toFixed(4)}</span>
        </div>
        <div>
          <span className="text-gray-500">Updated:</span>{' '}
          <span className="font-medium">{new Date(rec.generated_at).toLocaleDateString()}</span>
        </div>
      </div>
    </div>
  )
}
