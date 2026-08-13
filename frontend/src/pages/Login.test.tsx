import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import Login from './Login'
import { useAuth } from '../contexts/AuthContext'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

describe('Login', () => {
  it('shows an error message when sign-in fails', async () => {
    vi.mocked(useAuth).mockReturnValue({
      session: null,
      loading: false,
      signInWithPassword: vi.fn().mockResolvedValue({ error: 'Invalid credentials' }),
      signUp: vi.fn(),
      signInWithGoogle: vi.fn(),
      signOut: vi.fn(),
    })

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Invalid credentials'),
    )
  })

  it('shows a success message when signup succeeds', async () => {
    const signUp = vi.fn().mockResolvedValue({ error: null })
    vi.mocked(useAuth).mockReturnValue({
      session: null,
      loading: false,
      signInWithPassword: vi.fn(),
      signUp,
      signInWithGoogle: vi.fn(),
      signOut: vi.fn(),
    })

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByText("Don't have an account? Sign up"))
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secretpw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign up' }))

    await waitFor(() =>
      expect(
        screen.getByText('Account created — check your email to confirm, then log in.'),
      ).toBeInTheDocument(),
    )
    expect(signUp).toHaveBeenCalledWith('a@b.com', 'secretpw')
  })

  it('shows an error message when signup fails', async () => {
    const signUp = vi.fn().mockResolvedValue({ error: 'Email already registered' })
    vi.mocked(useAuth).mockReturnValue({
      session: null,
      loading: false,
      signInWithPassword: vi.fn(),
      signUp,
      signInWithGoogle: vi.fn(),
      signOut: vi.fn(),
    })

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByText("Don't have an account? Sign up"))
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secretpw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign up' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Email already registered'),
    )
  })
})
