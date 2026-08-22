export interface RawPrediction {
  horizon_days: number
  predicted_rate: number
  lower_bound: number
  upper_bound: number
  confidence: 'normal' | 'low'
  generated_at: string
}

// Inverts a USD->X prediction into the X->USD direction. Reciprocal is a
// decreasing function for positive numbers, so bound order flips: the new
// lower bound comes from the old upper bound, and vice versa. Mirrors
// backend/app/recommendations/engine.py's invert_prediction.
export function invertPrediction(p: RawPrediction): RawPrediction {
  return {
    horizon_days: p.horizon_days,
    predicted_rate: 1 / p.predicted_rate,
    lower_bound: 1 / p.upper_bound,
    upper_bound: 1 / p.lower_bound,
    confidence: p.confidence,
    generated_at: p.generated_at,
  }
}

// Derives base->quote predictions from two USD-pivot legs (USD->base and
// USD->quote), the same ratio backend/app/ingestion/rates.py uses to derive
// cross rates during ingestion. Refitting the backtest model for every
// cross-pair combination (29*28 of them) isn't practical, so cross
// predictions are computed arithmetically at read time instead of stored.
//
// predicted_rate is a straight ratio. Bounds use positive-interval
// division: [lower, upper] for quote/base is [quote.lower/base.upper,
// quote.upper/base.lower] -- the widest possible range the two
// independent intervals can produce, not an approximation.
export function deriveCrossPredictions(
  usdToBase: RawPrediction[],
  usdToQuote: RawPrediction[],
): RawPrediction[] {
  const baseByHorizon = new Map(usdToBase.map((p) => [p.horizon_days, p]))
  const result: RawPrediction[] = []
  for (const q of usdToQuote) {
    const b = baseByHorizon.get(q.horizon_days)
    if (!b) continue
    result.push({
      horizon_days: q.horizon_days,
      predicted_rate: q.predicted_rate / b.predicted_rate,
      lower_bound: q.lower_bound / b.upper_bound,
      upper_bound: q.upper_bound / b.lower_bound,
      confidence: q.confidence === 'low' || b.confidence === 'low' ? 'low' : 'normal',
      generated_at: q.generated_at < b.generated_at ? q.generated_at : b.generated_at,
    })
  }
  return result
}

export interface RecommendationResult {
  recommendation: 'act_now' | 'wait' | 'volatile' | 'no_signal'
  current_rate: number
  expected_rate: number
  lower_bound: number
  upper_bound: number
  reference_horizon_days: number
}

// Mirrors backend/app/recommendations/engine.py's choose_recommendation.
// favorable_high is always true there: both directions are put into their
// own "higher rate = more of the target currency = favorable" space
// before this runs (the reverse direction via invertPrediction), and that
// holds for any base->quote pair, not just USD-pivot ones.
//
// currentRate === reference.predicted_rate exactly is "no_signal", not
// act_now: it's what happens whenever the reference horizon's backtest
// picked the naive/no-change baseline -- there's no forecast basis to
// call that a directional signal. This equality is exact and reliable
// for USD-pivot pairs (backend: both values trace to the same
// rates_cache row). For a derived cross pair it's a best-effort check --
// currentRate comes from the materialized cross rate while
// reference.predicted_rate is a ratio of two independently-fetched
// USD-pivot predictions, so a naive-vs-naive tie can occasionally miss
// by a hair due to snapshot timing or floating-point division order.
export function chooseRecommendation(
  currentRate: number,
  horizons: RawPrediction[],
): RecommendationResult {
  if (horizons.length === 0) {
    throw new Error('no horizons to choose from')
  }
  const reference = horizons.reduce((best, h) => (h.predicted_rate > best.predicted_rate ? h : best))
  const recommendation =
    reference.confidence === 'low'
      ? 'volatile'
      : currentRate === reference.predicted_rate
        ? 'no_signal'
        : currentRate >= reference.predicted_rate
          ? 'act_now'
          : 'wait'
  return {
    recommendation,
    current_rate: currentRate,
    expected_rate: reference.predicted_rate,
    lower_bound: reference.lower_bound,
    upper_bound: reference.upper_bound,
    reference_horizon_days: reference.horizon_days,
  }
}
