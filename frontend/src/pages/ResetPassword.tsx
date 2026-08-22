import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabaseClient'

export default function ResetPassword() {
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setMessage(null)

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters')
      return
    }

    setSubmitting(true)
    try {
      const { error: updateError } = await supabase.auth.updateUser({ password })
      if (updateError) {
        setError(updateError.message)
        return
      }
      setMessage('Password updated! Redirecting to login...')
      setTimeout(() => navigate('/login', { replace: true }), 2000)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center px-4">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-blue-600">ForexCast</h1>
      </div>

      <div className="w-full max-w-md bg-white rounded-xl shadow-md p-8">
        <h2 className="text-xl font-semibold text-gray-900 mb-6">Set new password</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
              New password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              minLength={6}
              autoFocus
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div>
            <label htmlFor="confirm-password" className="block text-sm font-medium text-gray-700 mb-1">
              Confirm new password
            </label>
            <input
              id="confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="••••••••"
              required
              minLength={6}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full px-4 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Please wait...' : 'Update password'}
          </button>
        </form>

        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700" role="alert">
            {error}
          </div>
        )}
        {message && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
            {message}
          </div>
        )}
      </div>
    </div>
  )
}
