import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { RecommendationCard } from './RecommendationCard'

describe('RecommendationCard', () => {
  it('shows actionable empty state when rec is null', () => {
    render(<RecommendationCard rec={null} pair="EUR/SGD" />)
    expect(screen.getByText(/no forecast data yet/i)).toBeInTheDocument()
    expect(screen.getByText(/weekly/i)).toBeInTheDocument()
  })

  it('renders recommendation badge for act_now', () => {
    const rec = {
      recommendation: 'act_now' as const,
      current_rate: 1.45, expected_rate: 1.40,
      lower_bound: 1.38, upper_bound: 1.42,
      reference_horizon_days: 30,
      generated_at: '2026-08-24T00:00:00Z',
    }
    render(<RecommendationCard rec={rec} pair="EUR/SGD" />)
    expect(screen.getByText(/ACT NOW/)).toBeInTheDocument()
  })
})