import { describe, expect, it } from 'vitest'
import {
  chooseRecommendation,
  deriveCrossPredictions,
  interpolatePrediction,
  invertPrediction,
  type RawPrediction,
} from './predictionMath'

function pred(overrides: Partial<RawPrediction>): RawPrediction {
  return {
    horizon_days: 7,
    predicted_rate: 1,
    lower_bound: 0.9,
    upper_bound: 1.1,
    confidence: 'normal',
    generated_at: '2026-08-20T00:00:00Z',
    ...overrides,
  }
}

describe('invertPrediction', () => {
  it('reciprocates the rate and swaps bound order', () => {
    const usdToInr = pred({ predicted_rate: 95.44, lower_bound: 90, upper_bound: 100 })
    const inrToUsd = invertPrediction(usdToInr)

    expect(inrToUsd.predicted_rate).toBeCloseTo(1 / 95.44, 10)
    expect(inrToUsd.lower_bound).toBeCloseTo(1 / 100, 10)
    expect(inrToUsd.upper_bound).toBeCloseTo(1 / 90, 10)
    // lower must still be <= upper after the flip
    expect(inrToUsd.lower_bound).toBeLessThan(inrToUsd.upper_bound)
  })
})

describe('deriveCrossPredictions', () => {
  it('derives base->quote rate as usd_rate(quote)/usd_rate(base)', () => {
    // USD->EUR = 0.867, USD->INR = 95.44 => EUR->INR should be 95.44/0.867
    const usdToEur = [pred({ horizon_days: 7, predicted_rate: 0.867, lower_bound: 0.85, upper_bound: 0.88 })]
    const usdToInr = [pred({ horizon_days: 7, predicted_rate: 95.44, lower_bound: 93, upper_bound: 98 })]

    const [eurToInr] = deriveCrossPredictions(usdToEur, usdToInr)

    expect(eurToInr.predicted_rate).toBeCloseTo(95.44 / 0.867, 6)
    // positive-interval division: [lower, upper] = [q.lower/b.upper, q.upper/b.lower]
    expect(eurToInr.lower_bound).toBeCloseTo(93 / 0.88, 6)
    expect(eurToInr.upper_bound).toBeCloseTo(98 / 0.85, 6)
    expect(eurToInr.lower_bound).toBeLessThan(eurToInr.predicted_rate)
    expect(eurToInr.predicted_rate).toBeLessThan(eurToInr.upper_bound)
  })

  it('only pairs horizons present on both legs', () => {
    const usdToBase = [pred({ horizon_days: 7 }), pred({ horizon_days: 30 })]
    const usdToQuote = [pred({ horizon_days: 30 }), pred({ horizon_days: 90 })]

    const result = deriveCrossPredictions(usdToBase, usdToQuote)

    expect(result.map((r) => r.horizon_days)).toEqual([30])
  })

  it('marks the cross prediction low-confidence if either leg is low', () => {
    const usdToBase = [pred({ confidence: 'low' })]
    const usdToQuote = [pred({ confidence: 'normal' })]

    const [result] = deriveCrossPredictions(usdToBase, usdToQuote)

    expect(result.confidence).toBe('low')
  })
})

describe('chooseRecommendation', () => {
  it('picks act_now when the current rate already beats the best horizon', () => {
    const horizons = [
      pred({ horizon_days: 7, predicted_rate: 1.0 }),
      pred({ horizon_days: 30, predicted_rate: 1.05 }),
    ]

    const result = chooseRecommendation(1.1, horizons)

    expect(result.reference_horizon_days).toBe(30)
    expect(result.expected_rate).toBe(1.05)
    expect(result.recommendation).toBe('act_now')
  })

  it('picks wait when the best horizon still predicts higher than current', () => {
    const horizons = [pred({ horizon_days: 30, predicted_rate: 1.2 })]

    const result = chooseRecommendation(1.0, horizons)

    expect(result.recommendation).toBe('wait')
  })

  it('overrides to volatile when the reference horizon is low-confidence, even if current beats it', () => {
    const horizons = [pred({ horizon_days: 30, predicted_rate: 1.0, confidence: 'low' })]

    const result = chooseRecommendation(1.5, horizons)

    expect(result.recommendation).toBe('volatile')
  })

  it('throws on an empty horizon list', () => {
    expect(() => chooseRecommendation(1.0, [])).toThrow()
  })

  it('reports no_signal when current rate exactly equals the reference forecast', () => {
    // Exactly what happens when the reference horizon's backtest picked
    // the naive/no-change baseline -- must not silently read as act_now.
    const horizons = [pred({ horizon_days: 7, predicted_rate: 1.0 })]

    const result = chooseRecommendation(1.0, horizons)

    expect(result.recommendation).toBe('no_signal')
  })

  it('low confidence still wins over no_signal on an exact tie', () => {
    const horizons = [pred({ horizon_days: 7, predicted_rate: 1.0, confidence: 'low' })]

    const result = chooseRecommendation(1.0, horizons)

    expect(result.recommendation).toBe('volatile')
  })
})

describe('interpolatePrediction', () => {
  const p7 = pred({ horizon_days: 7, predicted_rate: 1.0, lower_bound: 0.9, upper_bound: 1.1, confidence: 'normal' })
  const p30 = pred({ horizon_days: 30, predicted_rate: 1.2, lower_bound: 1.1, upper_bound: 1.3, confidence: 'normal' })
  const p90 = pred({ horizon_days: 90, predicted_rate: 1.5, lower_bound: 1.3, upper_bound: 1.7, confidence: 'normal' })

  it('midpoint between 7d and 30d gives average of the two', () => {
    // t = (18-7)/(30-7) = 11/23; predicted = 1.0*(1-t) + 1.2*t
    const t = (18 - 7) / (30 - 7)
    const result = interpolatePrediction([p7, p30, p90], 18)
    expect(result.predicted_rate).toBeCloseTo(1.0 * (1 - t) + 1.2 * t, 10)
    expect(result.horizon_days).toBe(18)
    expect(result.source_lower_days).toBe(7)
    expect(result.source_upper_days).toBe(30)
  })

  it('exact horizon match returns that horizon unchanged', () => {
    const result = interpolatePrediction([p7, p30, p90], 30)
    expect(result.predicted_rate).toBe(p30.predicted_rate)
    expect(result.horizon_days).toBe(30)
    expect(result.source_lower_days).toBe(30)
    expect(result.source_upper_days).toBe(30)
  })

  it('below minimum snaps to shortest horizon', () => {
    const result = interpolatePrediction([p7, p30, p90], 3)
    expect(result.predicted_rate).toBe(p7.predicted_rate)
    expect(result.horizon_days).toBe(3)
    expect(result.source_lower_days).toBe(7)
    expect(result.source_upper_days).toBe(7)
  })

  it('above maximum snaps to longest horizon', () => {
    const result = interpolatePrediction([p7, p30, p90], 200)
    expect(result.predicted_rate).toBe(p90.predicted_rate)
    expect(result.horizon_days).toBe(200)
    expect(result.source_lower_days).toBe(90)
    expect(result.source_upper_days).toBe(90)
  })

  it('propagates low confidence if either bounding horizon is low', () => {
    const p7low = pred({ horizon_days: 7, confidence: 'low' })
    const result = interpolatePrediction([p7low, p30], 18)
    expect(result.confidence).toBe('low')
  })
})
