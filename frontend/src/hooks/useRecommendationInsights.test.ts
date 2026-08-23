import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { useRecommendationInsights } from './useRecommendationInsights'
import * as apiClient from '../lib/apiClient'

describe('useRecommendationInsights', () => {
  it('fetches insights and sets them', async () => {
    vi.spyOn(apiClient, 'fetchRecommendationInsights').mockResolvedValue({
      requires_llm_setup: false,
      sentiment: { score: 0.5, summary: 'Positive outlook' },
    })
    const { result } = renderHook(() => useRecommendationInsights('EUR', 'USD'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.insights?.sentiment?.score).toBe(0.5)
  })

  it('sets requires_llm_setup when key missing', async () => {
    vi.spyOn(apiClient, 'fetchRecommendationInsights').mockResolvedValue({
      requires_llm_setup: true,
      sentiment: null,
    })
    const { result } = renderHook(() => useRecommendationInsights('EUR', 'USD'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.insights?.requires_llm_setup).toBe(true)
  })
})
