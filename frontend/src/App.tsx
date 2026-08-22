import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Link, useNavigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Alerts from './pages/Alerts'
import Chat from './pages/Chat'
import Settings from './pages/Settings'
import Planner from './pages/Planner'
import Debts from './pages/Debts'
import Goals from './pages/Goals'
import Achievements from './pages/Achievements'
import ProtectedRoute from './components/ProtectedRoute'

function Home() {
  const { session, loading } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (!loading && session) {
      navigate('/dashboard', { replace: true })
    }
  }, [session, loading, navigate])

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center">
      <h1 className="text-4xl font-bold text-blue-600 mb-4">ForexCast</h1>
      <p className="text-gray-600 mb-8 text-center max-w-md">
        Currency exchange rate predictions powered by statistical models and AI.
      </p>
      <Link
        to="/login"
        className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition-colors"
      >
        Get Started
      </Link>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/alerts" element={<ProtectedRoute><Alerts /></ProtectedRoute>} />
          <Route path="/chat" element={<ProtectedRoute><Chat /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
          <Route path="/planner" element={<ProtectedRoute><Planner /></ProtectedRoute>} />
          <Route path="/planner/debts" element={<ProtectedRoute><Debts /></ProtectedRoute>} />
          <Route path="/planner/goals" element={<ProtectedRoute><Goals /></ProtectedRoute>} />
          <Route path="/planner/achievements" element={<ProtectedRoute><Achievements /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
