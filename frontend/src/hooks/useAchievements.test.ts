import { renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAchievements } from './useAchievements'

vi.mock('../lib/supabaseClient', () => ({
  supabase: {
    from: () => ({
      select: () => ({
        order: () => ({ error: null, data: [] }),
        maybeSingle: () => ({ error: null, data: null }),
      }),
    }),
  },
}))

vi.mock('../lib/apiClient', () => ({
  getBadges: vi.fn().mockRejectedValue(new Error('network error')),
  checkinStreak: vi.fn(),
}))

describe('useAchievements', () => {
  it('resolves loading=false even when getBadges throws', async () => {
    const { result } = renderHook(() => useAchievements())
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
  })
})