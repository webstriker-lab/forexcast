import { supabase } from './supabaseClient'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

export async function fetchCurrentUser(): Promise<{ user_id: string }> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error('Not authenticated')

  const response = await fetch(`${API_BASE_URL}/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Request failed: ${response.status}`)
  return response.json()
}

export async function chat(messages: { role: string; content: string }[]) {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')

  const res = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({ messages }),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }

  return res.json()
}

export async function getDebtTimeline(): Promise<{
  debts: Record<string, unknown>
  summary: {
    total_balance: number
    total_minimum_payment: number
    debt_count: number
    weighted_average_rate: number
    currencies_missing_rate: string[]
  }
}> {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')

  const res = await fetch(`${API_BASE_URL}/planner/timeline/debts`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function getBadges(): Promise<Record<string, { name: string; emoji: string; description: string }>> {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')

  const res = await fetch(`${API_BASE_URL}/planner/badges`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function checkinStreak(): Promise<{ streaks: unknown; new_achievements: unknown[] }> {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')

  const res = await fetch(`${API_BASE_URL}/planner/streaks/checkin`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${session.access_token}` },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}
