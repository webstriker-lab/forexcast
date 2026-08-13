import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function Login() {
  const { signInWithPassword, signUp, signInWithGoogle, session, loading } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const navigate = useNavigate()

  useEffect(() => {
    if (!loading && session) {
      navigate('/dashboard', { replace: true })
    }
  }, [session, loading, navigate])

  function toggleMode() {
    setMode((m) => (m === 'login' ? 'signup' : 'login'))
    setError(null)
    setMessage(null)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setMessage(null)

    if (mode === 'signup') {
      const { error: signUpError } = await signUp(email, password)
      if (signUpError) {
        setError(signUpError)
        return
      }
      setMessage('Account created — check your email to confirm, then log in.')
      return
    }

    const { error: signInError } = await signInWithPassword(email, password)
    if (signInError) {
      setError(signInError)
    }
  }

  return (
    <div>
      <h1>{mode === 'login' ? 'Log in' : 'Sign up'}</h1>
      <form onSubmit={handleSubmit}>
        <label htmlFor="email">Email</label>
        <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button type="submit">{mode === 'login' ? 'Log in' : 'Sign up'}</button>
      </form>
      <button onClick={signInWithGoogle}>Continue with Google</button>
      <button type="button" onClick={toggleMode}>
        {mode === 'login' ? "Don't have an account? Sign up" : 'Already have an account? Log in'}
      </button>
      {error && <p role="alert">{error}</p>}
      {message && <p>{message}</p>}
    </div>
  )
}
