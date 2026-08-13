import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchCurrentUser } from './apiClient'
import { supabase } from './supabaseClient'

vi.mock('./supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: vi.fn(),
    },
  },
}))

describe('fetchCurrentUser', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('throws when there is no access token', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: null },
    } as never)

    await expect(fetchCurrentUser()).rejects.toThrow('Not authenticated')
  })

  it('calls the backend with the bearer token and returns the user id', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: { access_token: 'abc123' } },
    } as never)
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ user_id: 'user-123' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchCurrentUser()

    expect(result).toEqual({ user_id: 'user-123' })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/me',
      expect.objectContaining({ headers: { Authorization: 'Bearer abc123' } }),
    )
  })

  it('throws when the backend responds with a non-ok status', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: { access_token: 'abc123' } },
    } as never)
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchCurrentUser()).rejects.toThrow('Request failed: 500')
  })
})
