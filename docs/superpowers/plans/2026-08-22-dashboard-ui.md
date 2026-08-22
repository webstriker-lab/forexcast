# Dashboard UI Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A React SPA that connects all backend pieces (items 1–5) into a user-facing product: currency pair picker, rate chart with predictions, recommendation display, alert management, LLM chat, and settings — all reading directly from Supabase via RLS.

**Tech Stack:** React 18, Vite, TypeScript, Tailwind CSS, @supabase/supabase-js v2, Chart.js, TweetNaCl.js, React Router v6, vite-plugin-pwa.

**Spec:** [docs/superpowers/specs/2026-08-22-dashboard-ui-design.md](../specs/2026-08-22-dashboard-ui-design.md)

## Global Constraints

- No backend API routes for data reads — all data fetched directly from Supabase via the JS client with RLS.
- The only backend call is `POST /chat` (JWT-authenticated).
- Mobile-first responsive design — every component must work on a 375px viewport.
- All Supabase keys are the anon key (public), never the service key in the frontend.
- TypeScript strict mode.

---

### Task 1: Project scaffolding

**Files:**
- Create: `frontend/` directory with Vite + React + TypeScript template
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.js`, `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`, `frontend/src/App.tsx`
- Create: `frontend/src/lib/supabase.ts`
- Create: `frontend/.env.example`

**Steps:**

- [ ] **Step 1: Scaffold the Vite project**

```bash
cd D:\FOREX-RATE-PREDICTING-APP
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

- [ ] **Step 2: Install dependencies**

```bash
npm install @supabase/supabase-js react-router-dom chart.js react-chartjs-2 tweetnacl
npm install -D tailwindcss @tailwindcss/vite
```

- [ ] **Step 3: Configure Tailwind**

In `vite.config.ts`, add the Tailwind plugin:
```ts
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

In `src/index.css`, add:
```css
@import "tailwindcss";
```

- [ ] **Step 4: Create Supabase client**

```ts
// src/lib/supabase.ts
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

- [ ] **Step 5: Create `.env.example`**

```
VITE_SUPABASE_URL=https://<project>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon-key>
VITE_BACKEND_URL=http://localhost:8000
```

- [ ] **Step 6: Verify dev server starts**

```bash
npm run dev
```

Expected: Vite dev server starts on http://localhost:5173

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold frontend with Vite + React + Tailwind"
```

---

### Task 2: Auth (login/signup/session)

**Files:**
- Create: `frontend/src/hooks/useAuth.ts`
- Create: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/App.tsx`

**Steps:**

- [ ] **Step 1: Create the auth hook**

```ts
// src/hooks/useAuth.ts
import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import type { Session, User } from '@supabase/supabase-js'

export function useAuth() {
  const [session, setSession] = useState<Session | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      setUser(session?.user ?? null)
      setLoading(false)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
      setUser(session?.user ?? null)
    })

    return () => subscription.unsubscribe()
  }, [])

  return { session, user, loading }
}
```

- [ ] **Step 2: Create the Login page**

```tsx
// src/pages/Login.tsx
import { useState } from 'react'
import { supabase } from '../lib/supabase'

export function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSignUp, setIsSignUp] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    const { error } = isSignUp
      ? await supabase.auth.signUp({ email, password })
      : await supabase.auth.signInWithPassword({ email, password })
    if (error) setError(error.message)
  }

  const handleGoogle = async () => {
    await supabase.auth.signInWithOAuth({ provider: 'google' })
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-8 p-8 bg-white rounded-lg shadow">
        <h2 className="text-2xl font-bold text-center">
          {isSignUp ? 'Create account' : 'Sign in'}
        </h2>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="email" placeholder="Email" value={email}
            onChange={e => setEmail(e.target.value)}
            className="w-full px-3 py-2 border rounded-md"
            required
          />
          <input
            type="password" placeholder="Password" value={password}
            onChange={e => setPassword(e.target.value)}
            className="w-full px-3 py-2 border rounded-md"
            required
          />
          <button type="submit" className="w-full py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
            {isSignUp ? 'Sign up' : 'Sign in'}
          </button>
        </form>
        <button onClick={handleGoogle} className="w-full py-2 border rounded-md hover:bg-gray-50">
          Continue with Google
        </button>
        <p className="text-center text-sm">
          {isSignUp ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button onClick={() => setIsSignUp(!isSignUp)} className="text-blue-600 underline">
            {isSignUp ? 'Sign in' : 'Sign up'}
          </button>
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Wire auth into App.tsx with protected routes**

```tsx
// src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './hooks/useAuth'
import { Login } from './pages/Login'
import { Dashboard } from './pages/Dashboard'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen flex items-center justify-center">Loading...</div>
  if (!user) return <Navigate to="/login" />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 4: Create a placeholder Dashboard page**

```tsx
// src/pages/Dashboard.tsx
export function Dashboard() {
  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <h1 className="text-2xl font-bold">ForexCast Dashboard</h1>
      <p className="text-gray-600">Coming soon...</p>
    </div>
  )
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: add Supabase auth with login/signup page"
```

---

### Task 3: Layout, navigation, and routing

**Files:**
- Create: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/App.tsx`

**Steps:**

- [ ] **Step 1: Create the Layout component**

```tsx
// src/components/Layout.tsx
import { Link, useLocation } from 'react-router-dom'
import { supabase } from '../lib/supabase'

const navItems = [
  { path: '/', label: 'Dashboard' },
  { path: '/alerts', label: 'Alerts' },
  { path: '/chat', label: 'Chat' },
  { path: '/settings', label: 'Settings' },
]

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()

  const handleSignOut = async () => {
    await supabase.auth.signOut()
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 flex items-center justify-between h-14">
          <div className="flex items-center gap-6">
            <span className="text-xl font-bold text-blue-600">ForexCast</span>
            {navItems.map(item => (
              <Link
                key={item.path}
                to={item.path}
                className={`text-sm font-medium ${
                  location.pathname === item.path ? 'text-blue-600' : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </div>
          <button onClick={handleSignOut} className="text-sm text-gray-600 hover:text-gray-900">
            Sign out
          </button>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 py-6">
        {children}
      </main>
    </div>
  )
}
```

- [ ] **Step 2: Update App.tsx to use Layout**

Wrap all protected routes in the Layout component.

- [ ] **Step 3: Commit**

```bash
git add frontend/
git commit -m "feat: add layout with navigation"
```

---

### Task 4: Pair picker and watchlist

**Files:**
- Create: `frontend/src/hooks/useWatchlist.ts`
- Create: `frontend/src/components/PairPicker.tsx`

**Steps:**

- [ ] **Step 1: Create the watchlist hook**

```ts
// src/hooks/useWatchlist.ts
import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'

export interface CurrencyPair {
  base_code: string
  quote_code: string
}

export function useWatchlist() {
  const [pairs, setPairs] = useState<CurrencyPair[]>([])
  const [selected, setSelected] = useState<CurrencyPair | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchWatchlist()
  }, [])

  const fetchWatchlist = async () => {
    const { data, error } = await supabase
      .from('watchlist')
      .select('base_code, quote_code')
      .order('created_at', { ascending: false })

    if (!error && data) {
      setPairs(data)
      if (data.length > 0 && !selected) setSelected(data[0])
    }
    setLoading(false)
  }

  const addPair = async (base: string, quote: string) => {
    const { error } = await supabase
      .from('watchlist')
      .insert({ base_code: base, quote_code: quote })
    if (!error) await fetchWatchlist()
    return !error
  }

  const removePair = async (base: string, quote: string) => {
    const { error } = await supabase
      .from('watchlist')
      .delete()
      .match({ base_code: base, quote_code: quote })
    if (!error) await fetchWatchlist()
  }

  return { pairs, selected, setSelected, addPair, removePair, loading }
}
```

- [ ] **Step 2: Create the PairPicker component**

```tsx
// src/components/PairPicker.tsx
import { useState } from 'react'
import type { CurrencyPair } from '../hooks/useWatchlist'

const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'JPY', 'AUD', 'CAD', 'CHF', 'CNY', 'SGD', 'NZD', 'AED']

interface Props {
  pairs: CurrencyPair[]
  selected: CurrencyPair | null
  onSelect: (pair: CurrencyPair) => void
  onAdd: (base: string, quote: string) => Promise<boolean>
  onRemove: (base: string, quote: string) => void
}

export function PairPicker({ pairs, selected, onSelect, onAdd, onRemove }: Props) {
  const [base, setBase] = useState('USD')
  const [quote, setQuote] = useState('EUR')

  const handleAdd = async () => {
    if (base === quote) return
    await onAdd(base, quote)
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <select value={base} onChange={e => setBase(e.target.value)} className="px-3 py-2 border rounded-md">
        {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
      <span className="text-gray-400">→</span>
      <select value={quote} onChange={e => setQuote(e.target.value)} className="px-3 py-2 border rounded-md">
        {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
      <button onClick={handleAdd} className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm">
        Add
      </button>
      <div className="flex flex-wrap gap-2 ml-4">
        {pairs.map(p => (
          <button
            key={`${p.base_code}-${p.quote_code}`}
            onClick={() => onSelect(p)}
            className={`px-3 py-1 rounded-full text-sm font-medium ${
              selected?.base_code === p.base_code && selected?.quote_code === p.quote_code
                ? 'bg-blue-600 text-white'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            }`}
          >
            {p.base_code}/{p.quote_code}
            <span onClick={(e) => { e.stopPropagation(); onRemove(p.base_code, p.quote_code) }}
              className="ml-1 text-xs opacity-60 hover:opacity-100">×</span>
          </button>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/
git commit -m "feat: add pair picker with watchlist CRUD"
```

---

### Task 5: Rate chart with predictions

**Files:**
- Create: `frontend/src/hooks/useRates.ts`
- Create: `frontend/src/hooks/usePredictions.ts`
- Create: `frontend/src/components/RateChart.tsx`

**Steps:**

- [ ] **Step 1: Create the rates hook**

```ts
// src/hooks/useRates.ts
import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'

export interface RateRow {
  as_of: string
  rate: number
}

export function useRates(base: string, quote: string) {
  const [rates, setRates] = useState<RateRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!base || !quote) return
    setLoading(true)
    supabase
      .from('rates_cache')
      .select('as_of, rate')
      .eq('base_code', base)
      .eq('quote_code', quote)
      .order('as_of', { ascending: true })
      .then(({ data }) => {
        setRates(data ?? [])
        setLoading(false)
      })
  }, [base, quote])

  return { rates, loading }
}
```

- [ ] **Step 2: Create the predictions hook**

```ts
// src/hooks/usePredictions.ts
import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'

export interface Prediction {
  horizon_days: number
  predicted_rate: number
  lower_bound: number
  upper_bound: number
  confidence: 'normal' | 'low'
  generated_at: string
}

export function usePredictions(base: string, quote: string) {
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!base || !quote) return
    setLoading(true)
    supabase
      .from('predictions')
      .select('horizon_days, predicted_rate, lower_bound, upper_bound, confidence, generated_at')
      .eq('base_code', base)
      .eq('quote_code', quote)
      .order('generated_at', { ascending: false })
      .then(({ data }) => {
        // Keep only the latest batch per horizon
        const latest = new Map<number, Prediction>()
        for (const row of data ?? []) {
          if (!latest.has(row.horizon_days)) latest.set(row.horizon_days, row)
        }
        setPredictions([...latest.values()].sort((a, b) => a.horizon_days - b.horizon_days))
        setLoading(false)
      })
  }, [base, quote])

  return { predictions, loading }
}
```

- [ ] **Step 3: Create the RateChart component**

```tsx
// src/components/RateChart.tsx
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  Filler, Tooltip, Legend
} from 'chart.js'
import type { RateRow } from '../hooks/useRates'
import type { Prediction } from '../hooks/usePredictions'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend)

interface Props {
  rates: RateRow[]
  predictions: Prediction[]
  pair: string
}

export function RateChart({ rates, predictions, pair }: Props) {
  if (rates.length === 0) {
    return <div className="h-64 flex items-center justify-center text-gray-400">No rate data available</div>
  }

  const labels = rates.map(r => r.as_of)
  const data = rates.map(r => r.rate)

  // Add prediction points at the end
  const lastDate = rates[rates.length - 1]?.as_of
  const predLabels = predictions.map(p => {
    const d = new Date(lastDate)
    d.setDate(d.getDate() + p.horizon_days)
    return d.toISOString().split('T')[0]
  })

  const chartData = {
    labels: [...labels, ...predLabels],
    datasets: [
      {
        label: pair,
        data: [...data, ...predictions.map(() => null)],
        borderColor: 'rgb(59, 130, 246)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
        pointRadius: 0,
      },
      {
        label: 'Predicted',
        data: [...Array(data.length - 1).fill(null), data[data.length - 1], ...predictions.map(p => p.predicted_rate)],
        borderColor: 'rgb(16, 185, 129)',
        borderDash: [5, 5],
        pointRadius: 4,
        pointBackgroundColor: predictions.map(p => p.confidence === 'low' ? 'rgb(245, 158, 11)' : 'rgb(16, 185, 129)'),
      },
      {
        label: 'Upper bound',
        data: [...Array(data.length - 1).fill(null), data[data.length - 1], ...predictions.map(p => p.upper_bound)],
        borderColor: 'rgba(16, 185, 129, 0.3)',
        borderDash: [2, 2],
        pointRadius: 0,
        fill: false,
      },
      {
        label: 'Lower bound',
        data: [...Array(data.length - 1).fill(null), data[data.length - 1], ...predictions.map(p => p.lower_bound)],
        borderColor: 'rgba(16, 185, 129, 0.3)',
        borderDash: [2, 2],
        pointRadius: 0,
        fill: '-1',
        backgroundColor: 'rgba(16, 185, 129, 0.1)',
      },
    ],
  }

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <Line data={chartData} options={{
        responsive: true,
        plugins: { legend: { position: 'bottom' } },
        scales: { x: { display: true, ticks: { maxTicksLimit: 10 } } },
      }} />
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: add rate chart with prediction overlays"
```

---

### Task 6: Recommendation card

**Files:**
- Create: `frontend/src/hooks/useRecommendations.ts`
- Create: `frontend/src/components/RecommendationCard.tsx`

**Steps:**

- [ ] **Step 1: Create the recommendations hook**

```ts
// src/hooks/useRecommendations.ts
import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'

export interface Recommendation {
  recommendation: 'act_now' | 'wait' | 'volatile'
  current_rate: number
  expected_rate: number
  lower_bound: number
  upper_bound: number
  reference_horizon_days: number
  generated_at: string
}

export function useRecommendations(base: string, quote: string) {
  const [rec, setRec] = useState<Recommendation | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!base || !quote) return
    setLoading(true)
    supabase
      .from('recommendations')
      .select('recommendation, current_rate, expected_rate, lower_bound, upper_bound, reference_horizon_days, generated_at')
      .eq('base_code', base)
      .eq('quote_code', quote)
      .order('generated_at', { ascending: false })
      .limit(1)
      .single()
      .then(({ data }) => {
        setRec(data)
        setLoading(false)
      })
  }, [base, quote])

  return { rec, loading }
}
```

- [ ] **Step 2: Create the RecommendationCard component**

```tsx
// src/components/RecommendationCard.tsx
import type { Recommendation } from '../hooks/useRecommendations'

const STYLES = {
  act_now: { bg: 'bg-green-50 border-green-200', badge: 'bg-green-100 text-green-800', label: 'ACT NOW' },
  wait: { bg: 'bg-yellow-50 border-yellow-200', badge: 'bg-yellow-100 text-yellow-800', label: 'WAIT' },
  volatile: { bg: 'bg-red-50 border-red-200', badge: 'bg-red-100 text-red-800', label: 'VOLATILE' },
}

interface Props {
  rec: Recommendation | null
  pair: string
}

export function RecommendationCard({ rec, pair }: Props) {
  if (!rec) return <div className="p-4 bg-white rounded-lg shadow text-gray-400">No recommendation yet</div>

  const style = STYLES[rec.recommendation]

  return (
    <div className={`p-4 rounded-lg border ${style.bg}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="font-semibold text-lg">{pair}</span>
        <span className={`px-3 py-1 rounded-full text-sm font-bold ${style.badge}`}>{style.label}</span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div><span className="text-gray-500">Current:</span> {rec.current_rate.toFixed(4)}</div>
        <div><span className="text-gray-500">Expected ({rec.reference_horizon_days}d):</span> {rec.expected_rate.toFixed(4)}</div>
        <div><span className="text-gray-500">Range:</span> {rec.lower_bound.toFixed(4)} – {rec.upper_bound.toFixed(4)}</div>
        <div><span className="text-gray-500">Updated:</span> {new Date(rec.generated_at).toLocaleDateString()}</div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/
git commit -m "feat: add recommendation card component"
```

---

### Task 7: Alert management

**Files:**
- Create: `frontend/src/hooks/useAlerts.ts`
- Create: `frontend/src/components/AlertManager.tsx`
- Create: `frontend/src/pages/Alerts.tsx`

**Steps:**

- [ ] **Step 1: Create the alerts hook**

```ts
// src/hooks/useAlerts.ts
import { useEffect, useState, useCallback } from 'react'
import { supabase } from '../lib/supabase'

export interface Alert {
  id: string
  base_code: string
  quote_code: string
  alert_type: 'threshold' | 'recommendation_change'
  threshold_rate: number | null
  direction: 'above' | 'below' | null
  is_active: boolean
  created_at: string
}

export function useAlerts() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)

  const fetchAlerts = useCallback(async () => {
    const { data } = await supabase
      .from('alerts')
      .select('*')
      .order('created_at', { ascending: false })
    setAlerts(data ?? [])
    setLoading(false)
  }, [])

  useEffect(() => { fetchAlerts() }, [fetchAlerts])

  const createAlert = async (alert: Omit<Alert, 'id' | 'is_active' | 'created_at'>) => {
    const { error } = await supabase.from('alerts').insert(alert)
    if (!error) await fetchAlerts()
    return !error
  }

  const toggleAlert = async (id: string, isActive: boolean) => {
    await supabase.from('alerts').update({ is_active: isActive }).eq('id', id)
    await fetchAlerts()
  }

  const deleteAlert = async (id: string) => {
    await supabase.from('alerts').delete().eq('id', id)
    await fetchAlerts()
  }

  return { alerts, loading, createAlert, toggleAlert, deleteAlert }
}
```

- [ ] **Step 2: Create the AlertManager component and Alerts page**

- [ ] **Step 3: Commit**

```bash
git add frontend/
git commit -m "feat: add alert management page"
```

---

### Task 8: Chat panel

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/ChatPanel.tsx`
- Create: `frontend/src/pages/Chat.tsx`

**Steps:**

- [ ] **Step 1: Create the API helper**

```ts
// src/lib/api.ts
import { supabase } from './supabase'

export async function chat(messages: { role: string; content: string }[]) {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')

  const res = await fetch(`${import.meta.env.VITE_BACKEND_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({ messages }),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }

  return res.json()
}
```

- [ ] **Step 2: Create the ChatPanel component**

```tsx
// src/components/ChatPanel.tsx
import { useState, useRef, useEffect } from 'react'
import { chat } from '../lib/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
  tool_calls?: { tool: string; arguments: Record<string, unknown>; result: unknown }[]
}

export function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || loading) return
    const userMsg: Message = { role: 'user', content: input.trim() }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setInput('')
    setLoading(true)

    try {
      const res = await chat(newMessages.map(m => ({ role: m.role, content: m.content })))
      setMessages([...newMessages, res.message])
    } catch (err) {
      setMessages([...newMessages, { role: 'assistant', content: `Error: ${err instanceof Error ? err.message : 'Unknown error'}` }])
    }
    setLoading(false)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] bg-white rounded-lg shadow">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-lg px-4 py-2 ${
              msg.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-900'
            }`}>
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.tool_calls && msg.tool_calls.length > 0 && (
                <details className="mt-2 text-xs opacity-70">
                  <summary>{msg.tool_calls.length} tool call(s)</summary>
                  {msg.tool_calls.map((tc, j) => (
                    <pre key={j} className="mt-1 overflow-x-auto">{tc.tool}({JSON.stringify(tc.arguments)})</pre>
                  ))}
                </details>
              )}
            </div>
          </div>
        ))}
        {loading && <div className="text-gray-400 text-sm">Thinking...</div>}
        <div ref={bottomRef} />
      </div>
      <div className="border-t p-4 flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder="Ask about any currency pair..."
          className="flex-1 px-4 py-2 border rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button onClick={handleSend} disabled={loading}
          className="px-6 py-2 bg-blue-600 text-white rounded-full hover:bg-blue-700 disabled:opacity-50">
          Send
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create the Chat page**

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: add chat panel with LLM agent integration"
```

---

### Task 9: Settings page (LLM config + Telegram linking)

**Files:**
- Create: `frontend/src/lib/encryption.ts`
- Create: `frontend/src/components/SettingsPage.tsx`
- Create: `frontend/src/pages/Settings.tsx`

**Steps:**

- [ ] **Step 1: Create encryption helpers**

```ts
// src/lib/encryption.ts
import nacl from 'tweetnacl'
import { decodeBase64 } from 'tweetnacl-util'

export function sealBox(message: string, publicKeyBase64: string): string {
  const pubKey = decodeBase64(publicKeyBase64)
  const messageBytes = new TextEncoder().encode(message)
  const sealed = nacl.box(messageBytes, nacl.randomBytes(nacl.box.nonceLength), pubKey)
  // Return as base64
  return btoa(String.fromCharCode(...sealed))
}
```

- [ ] **Step 2: Create the Settings page**

The settings page needs:
- LLM provider dropdown + API key input (encrypted before save)
- Model override (optional)
- Telegram linking status + link button

- [ ] **Step 3: Commit**

```bash
git add frontend/
git commit -m "feat: add settings page with LLM config and Telegram linking"
```

---

### Task 10: PWA manifest and final wiring

**Files:**
- Create: `frontend/public/manifest.json`
- Create: `frontend/public/icons/` (placeholder icons)
- Modify: `frontend/vite.config.ts` (add PWA plugin)

**Steps:**

- [ ] **Step 1: Install PWA plugin**

```bash
npm install -D vite-plugin-pwa
```

- [ ] **Step 2: Configure PWA in vite.config.ts**

- [ ] **Step 3: Create manifest.json**

- [ ] **Step 4: Wire all pages into App.tsx with final routing**

- [ ] **Step 5: Run `npm run build` to verify production build**

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: add PWA manifest and finalize dashboard"
```

---

### Task 11: Live verification

**Steps:**

- [ ] **Step 1: Create `.env` with real Supabase credentials**

- [ ] **Step 2: Start dev server and verify auth flow**

- [ ] **Step 3: Verify data loads (rates, predictions, recommendations)**

- [ ] **Step 4: Verify chat works end-to-end**

- [ ] **Step 5: Verify on mobile viewport**

- [ ] **Step 6: Final commit and push**
