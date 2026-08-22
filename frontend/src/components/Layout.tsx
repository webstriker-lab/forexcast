import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const navItems = [
  { path: '/dashboard', label: 'Dashboard' },
  { path: '/planner', label: 'Planner' },
  { path: '/alerts', label: 'Alerts' },
  { path: '/chat', label: 'Chat' },
  { path: '/settings', label: 'Settings' },
]

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const { signOut } = useAuth()

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 flex items-center justify-between h-14">
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="text-xl font-bold text-blue-600">ForexCast</Link>
            <div className="hidden sm:flex items-center gap-4">
              {navItems.map(item => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`text-sm font-medium transition-colors ${
                    location.pathname === item.path
                      ? 'text-blue-600'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
          <button
            onClick={signOut}
            className="text-sm text-gray-600 hover:text-gray-900 font-medium"
          >
            Sign out
          </button>
        </div>
        {/* Mobile nav */}
        <div className="sm:hidden border-t border-gray-100 px-4 py-2 flex gap-4 overflow-x-auto">
          {navItems.map(item => (
            <Link
              key={item.path}
              to={item.path}
              className={`text-sm font-medium whitespace-nowrap ${
                location.pathname === item.path ? 'text-blue-600' : 'text-gray-600'
              }`}
            >
              {item.label}
            </Link>
          ))}
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-6">
        {children}
      </main>
    </div>
  )
}
