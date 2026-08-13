import { useEffect, useState } from 'react'
import { fetchCurrentUser } from '../lib/apiClient'
import { useAuth } from '../contexts/AuthContext'

export default function Dashboard() {
  const { signOut } = useAuth()
  const [userId, setUserId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchCurrentUser()
      .then((data) => setUserId(data.user_id))
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load profile'))
  }, [])

  return (
    <div>
      <h1>Dashboard</h1>
      {error ? <p role="alert">{error}</p> : <p>Signed in as: {userId ?? 'loading...'}</p>}
      <button onClick={signOut}>Sign out</button>
    </div>
  )
}
