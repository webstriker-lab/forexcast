# Dashboard UI (Item 6) — Design Spec

Roadmap item 6 (see `docs/superpowers/plans/2026-08-13-forexcast-foundation.md`):
graph, chat panel, settings, currency-pair picker. Reads `predictions`/recommendation
state directly from Supabase (see item 3's note) unless this task finds a concrete
reason a backend API route is actually needed.

## 0. Scope

Item 6 is the entire frontend — a React SPA that connects all the backend pieces
built in items 1–5 into a user-facing product. It is the first frontend code in
this repo.

**In scope:**
- Supabase Auth (email+password + Google OAuth) — login/signup/session
- Currency pair picker (watchlist CRUD via Supabase RLS)
- Rate chart (historical rates from `rates_cache` + predictions with confidence bands from `predictions`)
- Recommendation display (ACT NOW / WAIT / VOLATILE from `recommendations`)
- Alert management (create/list/update/delete via Supabase RLS)
- Chat panel (calls `POST /chat` on the backend, shows tool calls)
- Settings page (LLM provider/key via sealed-box encryption to `llm_settings`, Telegram linking via `notification_settings`)
- PWA manifest + service worker for installability
- Mobile-responsive layout

**Out of scope (explicitly deferred):**
- Server-side rendering (SSR) — not needed; all data is client-fetchable via Supabase RLS
- Real-time subscriptions (Supabase Realtime) — polling or manual refresh is sufficient for daily-updated data
- Email notifications setup (item 5b) — the settings page will have a placeholder

## 1. Architecture

- **Framework:** React 18 + Vite (fast dev, small bundle)
- **Styling:** Tailwind CSS (matches the utility-first pattern, mobile-responsive by default)
- **Data layer:** `@supabase/supabase-js` v2 — direct client-side reads via RLS, no backend proxy for data
- **Auth:** `@supabase/supabase-js` auth module (email+password, Google OAuth)
- **Charting:** Chart.js via `react-chartjs-2` (lightweight, well-maintained, free)
- **Chat:** fetch to `POST /chat` on the backend (JWT from Supabase session)
- **Encryption:** TweetNaCl.js (`tweetnacl`) for sealed-box encryption of LLM API keys before writing to `llm_settings`
- **Routing:** React Router v6 (lightweight, standard)
- **PWA:** Vite PWA plugin (`vite-plugin-pwa`) — generates manifest + service worker

## 2. Data Flow

All data reads go directly to Supabase via the JS client, authenticated with the
user's JWT. RLS policies (defined in items 1–3's schema) ensure each user only
sees their own watchlist/alerts/settings, while rates/predictions/recommendations
are public-read.

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  React SPA  │────▶│  Supabase    │────▶│  Postgres   │
│  (Vite)     │◀────│  (JS Client) │◀────│  (RLS)      │
└──────┬──────┘     └──────────────┘     └─────────────┘
       │
       │ POST /chat (JWT auth)
       ▼
┌──────────────┐
│  FastAPI     │
│  Backend     │
└──────────────┘
```

## 3. Pages / Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/` | `Dashboard` | Main view: pair picker + chart + recommendation |
| `/alerts` | `Alerts` | List/create/edit/delete alerts |
| `/chat` | `Chat` | Conversational LLM agent interface |
| `/settings` | `Settings` | LLM provider config, Telegram linking |
| `/login` | `Login` | Auth (email+password, Google OAuth) |

## 4. Key Components

### 4.1 PairPicker
- Dropdown or searchable list of currency pairs from the `currencies` table
- Selected pair stored in URL params for shareability
- Writes to `watchlist` on selection (RLS insert)

### 4.2 RateChart
- Fetches `rates_cache` rows for the selected pair (last 365 days)
- Overlays `predictions` as dotted lines with shaded confidence bands
- Color-coded: green for normal confidence, orange for low confidence
- Responsive: collapses to a simpler view on mobile

### 4.3 RecommendationCard
- Fetches the latest `recommendations` row for the selected pair
- Displays: recommendation text (ACT NOW / WAIT / VOLATILE), current rate,
  expected rate, reference horizon
- Visual indicator: green/yellow/red badge

### 4.4 AlertManager
- Lists user's alerts from `alerts` table (RLS filtered)
- Create form: pair, type (threshold/recommendation_change), threshold+direction
- Toggle active/inactive, delete

### 4.5 ChatPanel
- Message list (user + assistant bubbles)
- Input field, send button
- Calls `POST /chat` with full message history (stateless backend)
- Shows tool calls in a collapsible section (from `tool_calls` response field)
- Scrolls to bottom on new messages

### 4.6 SettingsPage
- **LLM Provider:** dropdown (gemini, openai, deepseek, groq, openrouter)
- **API Key:** password field, encrypted client-side with TweetNaCl sealed-box
  before writing to `llm_settings` via Supabase RLS
- **Model:** optional text field (provider-specific model override)
- **Telegram:** button to generate link code, writes to `notification_settings`,
  shows status (linked/not linked)

## 5. Auth Flow

1. User visits `/login`
2. Signs in with email+password or Google OAuth (Supabase Auth)
3. Supabase returns a JWT + session
4. JWT stored in localStorage (Supabase default)
5. All subsequent Supabase client calls include the JWT automatically
6. `POST /chat` calls include `Authorization: Bearer <jwt>` header

## 6. PWA

- `manifest.json` with app name, icons, theme color
- Service worker caches static assets (Vite build output)
- Installable on mobile (Add to Home Screen)

## 7. Environment Variables

```
VITE_SUPABASE_URL=https://<project>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon-key>
VITE_BACKEND_URL=http://localhost:8000  # or deployed backend URL
```

## 8. File Structure

```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── public/
│   ├── manifest.json
│   └── icons/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── lib/
│   │   ├── supabase.ts          # Supabase client init
│   │   ├── encryption.ts        # TweetNaCl sealed-box helpers
│   │   └── api.ts               # POST /chat helper
│   ├── hooks/
│   │   ├── useAuth.ts           # Auth state + session
│   │   ├── useRates.ts          # Fetch rates_cache
│   │   ├── usePredictions.ts    # Fetch predictions
│   │   ├── useRecommendations.ts
│   │   ├── useAlerts.ts         # CRUD alerts
│   │   └── useWatchlist.ts      # Pair picker state
│   ├── components/
│   │   ├── Layout.tsx           # Nav + sidebar + content
│   │   ├── PairPicker.tsx
│   │   ├── RateChart.tsx
│   │   ├── RecommendationCard.tsx
│   │   ├── AlertManager.tsx
│   │   ├── ChatPanel.tsx
│   │   └── SettingsPage.tsx
│   └── pages/
│       ├── Dashboard.tsx
│       ├── Alerts.tsx
│       ├── Chat.tsx
│       ├── Settings.tsx
│       └── Login.tsx
```
