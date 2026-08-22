import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function Login() {
  const { signInWithPassword, signUp, signInWithGoogle, resetPassword, session, loading } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [mode, setMode] = useState<'login' | 'signup' | 'forgot'>('login')
  const [submitting, setSubmitting] = useState(false)
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

  function showForgot() {
    setMode('forgot')
    setError(null)
    setMessage(null)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setMessage(null)
    setSubmitting(true)

    try {
      if (mode === 'signup') {
        const { error: signUpError } = await signUp(email, password)
        if (signUpError) {
          setError(signUpError)
          return
        }
        setMessage('Account created — check your email to confirm, then log in.')
      } else if (mode === 'forgot') {
        const { error: resetError } = await resetPassword(email)
        if (resetError) {
          setError(resetError)
          return
        }
        setMessage('Password reset link sent — check your email.')
      } else {
        const { error: signInError } = await signInWithPassword(email, password)
        if (signInError) {
          setError(signInError)
        }
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function handleGoogle() {
    setError(null)
    setSubmitting(true)
    try {
      await signInWithGoogle()
    } catch {
      setError('Google sign-in failed. Please try again.')
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-400">Loading...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center px-4">
      {/* Logo / Brand */}
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-blue-600">ForexCast</h1>
        <p className="text-gray-500 mt-1">Smart forex rate predictions & alerts</p>
      </div>

      {/* Card */}
      <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
        <h2 className="text-xl font-semibold text-gray-900 mb-6">
          {mode === 'login' ? 'Welcome back' : mode === 'signup' ? 'Create your account' : 'Reset your password'}
        </h2>

        {/* Google Sign-In (hidden on forgot password) */}
        {mode !== 'forgot' && (
          <>
            <button
              onClick={handleGoogle}
              disabled={submitting}
              className="w-full flex items-center justify-center gap-3 px-4 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              Continue with Google
            </button>

            {/* Divider */}
            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="bg-white px-3 text-gray-400">or</span>
              </div>
            </div>
          </>
        )}

        {/* Email/Password Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          {mode !== 'forgot' && (
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                minLength={6}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="w-full px-4 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting
              ? 'Please wait...'
              : mode === 'login'
                ? 'Log in'
                : mode === 'signup'
                  ? 'Sign up'
                  : 'Send reset link'}
          </button>
        </form>

        {/* Toggle mode */}
        {mode === 'forgot' ? (
          <p className="mt-6 text-center text-sm text-gray-500">
            <button
              type="button"
              onClick={() => { setMode('login'); setError(null); setMessage(null) }}
              className="text-blue-600 font-medium hover:text-blue-700"
            >
              Back to log in
            </button>
          </p>
        ) : (
          <>
            {mode === 'login' && (
              <p className="mt-3 text-center text-sm">
                <button
                  type="button"
                  onClick={showForgot}
                  className="text-blue-600 font-medium hover:text-blue-700"
                >
                  Forgot password?
                </button>
              </p>
            )}
            <p className="mt-3 text-center text-sm text-gray-500">
              {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}{' '}
              <button
                type="button"
                onClick={toggleMode}
                className="text-blue-600 font-medium hover:text-blue-700"
              >
                {mode === 'login' ? 'Sign up' : 'Log in'}
              </button>
            </p>
          </>
        )}

        {/* Error */}
        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700" role="alert">
            {error}
          </div>
        )}

        {/* Success message */}
        {message && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
            {message}
          </div>
        )}
      </div>

      {/* Footer */}
      <p className="mt-6 text-xs text-gray-400">
        By continuing, you agree to our Terms of Service
      </p>
    </div>
  )
}
