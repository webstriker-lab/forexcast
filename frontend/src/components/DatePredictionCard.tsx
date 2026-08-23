import type { InterpolatedPrediction } from '../lib/predictionMath'

interface Props {
  prediction: InterpolatedPrediction
  pair: string
  targetDate: string
}

export function DatePredictionCard({ prediction, pair, targetDate }: Props) {
  const isLow = prediction.confidence === 'low'
  const isSameHorizon = prediction.source_lower_days === prediction.source_upper_days
  const sourceNote = isSameHorizon
    ? `Snapped to ${prediction.source_lower_days}-day forecast`
    : `Interpolated between ${prediction.source_lower_days}-day and ${prediction.source_upper_days}-day forecasts`

  return (
    <div
      className={`p-4 rounded-lg border ${
        isLow ? 'bg-yellow-50 border-yellow-200' : 'bg-blue-50 border-blue-200'
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-700">
          {pair} on {targetDate}
        </span>
        {isLow && (
          <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full font-medium">
            Low confidence
          </span>
        )}
      </div>
      <div className="text-2xl font-bold text-gray-900 mb-1">
        {prediction.predicted_rate.toFixed(4)}
      </div>
      <div className="text-sm text-gray-600">
        Range: {prediction.lower_bound.toFixed(4)} – {prediction.upper_bound.toFixed(4)}
      </div>
      <div className="text-xs text-gray-400 mt-2">{sourceNote}</div>
    </div>
  )
}
