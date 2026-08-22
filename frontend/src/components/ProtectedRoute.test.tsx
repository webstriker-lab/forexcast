import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ProtectedRoute from './ProtectedRoute'
import { useAuth } from '../contexts/AuthContext'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <div>secret dashboard</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<div>login page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute', () => {
  it('redirects to /login when there is no session', () => {
    vi.mocked(useAuth).mockReturnValue({
      session: null,
      loading: false,
      signInWithPassword: vi.fn(),
      signUp: vi.fn(),
      resetPassword: vi.fn(),
      signInWithGoogle: vi.fn(),
      signOut: vi.fn(),
    })
    renderAt('/dashboard')
    expect(screen.getByText('login page')).toBeInTheDocument()
  })

  it('renders children when a session exists', () => {
    vi.mocked(useAuth).mockReturnValue({
      // @ts-expect-error partial session object is sufficient for this test
      session: { access_token: 'token' },
      loading: false,
      signInWithPassword: vi.fn(),
      signUp: vi.fn(),
      resetPassword: vi.fn(),
      signInWithGoogle: vi.fn(),
      signOut: vi.fn(),
    })
    renderAt('/dashboard')
    expect(screen.getByText('secret dashboard')).toBeInTheDocument()
  })
})
