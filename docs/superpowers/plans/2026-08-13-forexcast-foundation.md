# ForexCast Foundation — Scaffolding, Auth & Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a deployed, working full-stack skeleton — Python/FastAPI backend, React/TypeScript frontend, Supabase database + auth — where a user can sign up, log in (email/password or Google), and see an authenticated dashboard shell that proves the frontend, backend, and database are correctly wired together, all on free-tier infrastructure.

**Architecture:** FastAPI backend verifies Supabase-issued JWTs and exposes a minimal `/health` and `/me` API. A Vite/React frontend (installable as a mobile PWA) handles auth via the Supabase JS client and calls the backend with the resulting access token. Postgres schema and row-level security live in Supabase, defined as SQL migrations in this repo. GitHub Actions runs backend and frontend tests on every push.

**Tech Stack:** Python 3.12 + FastAPI + PyJWT + httpx (backend); React 18 + TypeScript + Vite + react-router-dom + @supabase/supabase-js + vite-plugin-pwa (frontend); Supabase (Postgres + Auth, free tier); GitHub Actions (CI, free); Render (backend hosting, free tier) + Vercel (frontend hosting, free tier).

## Global Constraints

- Every external service must have a permanently free tier at this project's scale (Supabase, Render, Vercel, GitHub Actions) — no paid infrastructure.
- Frontend must be mobile-responsive and installable as a PWA — friends will use this primarily on phones.
- Every user-owned Postgres table must have Row-Level Security enabled, scoped to `auth.uid()`.
- Backend: Python/FastAPI. Frontend: React + TypeScript + Vite. No other frameworks.
- Every code task starts with a failing test before implementation (TDD).

## Roadmap (later plans, not part of this one)

This is the first of several plans implementing the [Phase 1 design spec](../specs/2026-08-13-forex-predictor-design.md). It only covers scaffolding, auth, and deployment — enough to prove the stack works end-to-end. Subsequent plans, each written and executed separately once the prior one is merged:

1. **Data ingestion pipeline (rates only)** — Frankfurter fetcher, `rates_cache` storage, GitHub Actions cron for scheduled refresh + one-time historical backfill. Shipped. See [design doc](../specs/2026-08-14-data-ingestion-pipeline-design.md).
2. **Prediction & backtesting engine — statistical baseline (2a)** — classical time-series model (ARIMA/exponential smoothing via `statsmodels`) off `rates_cache` alone, backtesting harness producing real measured confidence bands, low-confidence/volatility flagging, writes to the existing `predictions` table, 4 horizons (7/30/90/365-day), daily cron. No new external data sources or LLM calls. Fully self-contained and independently valuable — the honest numeric forecast on its own, before any macro/news adjustment. Shipped. See [design doc](../specs/2026-08-15-prediction-backtesting-engine-design.md).
   - **2b — FRED macro regression layer** — FRED ingestion (interest rates, inflation, GDP) + extends 2a's model with an interest-rate-differential regression adjustment. Depends on 2a existing. Was originally bundled with item 1's rates ingestion; deferred because it had no consumer until 2a exists. Shipped, interest rates only — inflation/GDP ingestion remains deferred (no consumer exists for either yet; revisit if 2c or a future model iteration wants them). See [design doc](../specs/2026-08-16-fred-macro-regression-design.md).
   - **2c — GDELT + LLM news-sentiment layer** — GDELT ingestion + a minimal LLM sentiment/event-scoring call + extends 2a's model with that adjustment. Depends on 2a existing, and needs at least a narrow LLM-calling slice (not necessarily the full multi-provider adapter from item 4 below — that's a separate, larger build). Was originally bundled with item 1's rates ingestion; deferred for the same reason as 2b, one level deeper (its consumer — an LLM call — doesn't exist yet either).
3. **Recommendation engine & alerts** — ACT NOW/WAIT/VOLATILE logic (continuous comparison of current rate to the forecast + its confidence band, reading `predictions`), plus evaluation of manual `alerts` (both `threshold` and `recommendation_change` types) — both write state to Supabase tables only. Explicitly excludes: notification dispatch itself (Telegram/email sending is item 5's job — evaluating "did this fire" is a self-contained, testable increment independent of whether delivery exists yet, unlike 2b/2c's situation) and any new backend API routes (no FastAPI endpoint exposes `predictions`/`rates_cache` today either — a future frontend queries Supabase directly via RLS, and this follows that same precedent; revisit only if the dashboard, item 6, turns out to need server-side computation a direct table read can't provide). Shipped. See [design doc](../specs/2026-08-15-recommendation-engine-design.md).
4. **LLM agent** — multi-provider adapter, tool-calling, chat.
5. **Notifications** — Telegram + email in-app linking and dispatch. Consumes the "fired" state item 3's alert evaluation already writes.
6. **Dashboard UI** — graph, chat panel, settings, currency-pair picker. Reads `predictions`/recommendation state directly from Supabase (see item 3's note) unless this task finds a concrete reason a backend API route is actually needed.

---

### Task 1: Backend scaffolding, settings, and health check

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/requirements-dev.txt`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/health.py`
- Test: `backend/tests/__init__.py`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `Settings` (pydantic-settings model) in `app.config` with fields `supabase_url: str`, `supabase_service_key: str`, `supabase_jwt_secret: str`; `get_settings()` — an `lru_cache`-wrapped accessor. `app` (FastAPI instance) in `app.main`, with `health.router` mounted.

- [ ] **Step 1: Create `backend/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
pydantic-settings==2.6.0
httpx==0.27.2
pyjwt==2.9.0
```

- [ ] **Step 2: Create `backend/requirements-dev.txt`**

```
pytest==8.3.3
```

- [ ] **Step 3: Create `backend/.env.example`**

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret
```

- [ ] **Step 4: Install dependencies**

Run: `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`
Expected: installs without errors.

- [ ] **Step 5: Create empty package markers**

Create `backend/app/__init__.py` (empty file) and `backend/app/routers/__init__.py` (empty file) and `backend/tests/__init__.py` (empty file).

- [ ] **Step 6: Write the failing test for `/health`**

`backend/tests/test_health.py`:

```python
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


client = TestClient(app)


def test_health_reports_ok_when_supabase_reachable():
    mock_response = MagicMock(status_code=200)
    with patch("app.routers.health.httpx.get", return_value=mock_response) as mock_get:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "supabase_reachable": True}
    mock_get.assert_called_once()


def test_health_reports_degraded_when_supabase_unreachable():
    with patch("app.routers.health.httpx.get", side_effect=Exception("connection refused")):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "supabase_reachable": False}
```

- [ ] **Step 7: Run the test to verify it fails**

Run: `pytest backend/tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'` (module doesn't exist yet).

- [ ] **Step 8: Implement `backend/app/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_service_key: str
    supabase_jwt_secret: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 9: Implement `backend/app/routers/health.py`**

```python
import httpx
from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    settings = get_settings()
    try:
        response = httpx.get(
            f"{settings.supabase_url}/rest/v1/",
            headers={"apikey": settings.supabase_service_key},
            timeout=5.0,
        )
        reachable = response.status_code < 500
    except Exception:
        reachable = False
    return {
        "status": "ok" if reachable else "degraded",
        "supabase_reachable": reachable,
    }
```

- [ ] **Step 10: Implement `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health

app = FastAPI(title="ForexCast API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tightened to a real origin in the deployment task
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
```

- [ ] **Step 11: Run the test to verify it passes**

Run: `pytest backend/tests/test_health.py -v`
Expected: PASS (2 tests).

- [ ] **Step 12: Commit**

```bash
git add backend/requirements.txt backend/requirements-dev.txt backend/.env.example backend/app backend/tests
git commit -m "feat(backend): scaffold FastAPI app with health check"
```

---

### Task 2: Supabase JWT auth dependency and `/me` endpoint

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/app/routers/me.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `Settings.supabase_jwt_secret` and `get_settings()` from Task 1's `app.config`.
- Produces: `get_current_user(authorization: str | None) -> str` in `app.auth` (FastAPI dependency; raises `HTTPException(401)` on missing/invalid/expired token, otherwise returns the JWT `sub` claim as the user id). `me.router` with `GET /me` returning `{"user_id": "<sub>"}`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_auth.py`:

```python
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings

TEST_SECRET = "test-jwt-secret-please-do-not-use-in-prod"


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


client = TestClient(app)


def _make_token(sub="user-123", exp_delta=3600, aud="authenticated"):
    payload = {"sub": sub, "aud": aud, "exp": int(time.time()) + exp_delta}
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def test_me_with_valid_token_returns_user_id():
    token = _make_token()
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"user_id": "user-123"}


def test_me_without_token_returns_401():
    response = client.get("/me")
    assert response.status_code == 401


def test_me_with_expired_token_returns_401():
    token = _make_token(exp_delta=-3600)
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_with_wrong_secret_returns_401():
    token = jwt.encode(
        {"sub": "user-123", "aud": "authenticated", "exp": int(time.time()) + 3600},
        "wrong-secret",
        algorithm="HS256",
    )
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_auth.py -v`
Expected: FAIL with 404 (no `/me` route registered yet).

- [ ] **Step 3: Implement `backend/app/auth.py`**

```python
import jwt
from fastapi import Header, HTTPException

from app.config import get_settings


class AuthError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=401, detail=detail)


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("Token missing subject claim")
    return user_id
```

- [ ] **Step 4: Implement `backend/app/routers/me.py`**

```python
from fastapi import APIRouter, Depends

from app.auth import get_current_user

router = APIRouter()


@router.get("/me")
def read_current_user(user_id: str = Depends(get_current_user)) -> dict:
    return {"user_id": user_id}
```

- [ ] **Step 5: Wire the router into `backend/app/main.py`**

Modify the imports and router registration:

```python
from app.routers import health, me
```

```python
app.include_router(health.router)
app.include_router(me.router)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest backend/tests/test_auth.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Run the full backend suite**

Run: `pytest backend/tests -v`
Expected: PASS (6 tests total).

- [ ] **Step 8: Commit**

```bash
git add backend/app/auth.py backend/app/routers/me.py backend/app/main.py backend/tests/test_auth.py
git commit -m "feat(backend): verify Supabase JWTs and add /me endpoint"
```

---

### Task 3: Supabase project schema and row-level security

**Files:**
- Create: `supabase/migrations/0001_init_schema.sql`
- Create: `backend/SUPABASE_SETUP.md`

**Interfaces:**
- Produces: Postgres tables `public.currencies`, `public.watchlist`, `public.rates_cache`, `public.predictions`, `public.alerts`, `public.notification_settings`, `public.llm_settings` — consumed by name in later data-pipeline, recommendation, notification, and agent plans.

- [ ] **Step 1: Write `supabase/migrations/0001_init_schema.sql`**

```sql
-- Reference list of supported currencies (curated major currencies only).
create table public.currencies (
    code text primary key,
    name text not null,
    is_active boolean not null default true
);

insert into public.currencies (code, name) values
    ('USD', 'US Dollar'), ('EUR', 'Euro'), ('GBP', 'British Pound'),
    ('INR', 'Indian Rupee'), ('JPY', 'Japanese Yen'), ('AUD', 'Australian Dollar'),
    ('CAD', 'Canadian Dollar'), ('CHF', 'Swiss Franc'), ('CNY', 'Chinese Yuan'),
    ('SGD', 'Singapore Dollar'), ('NZD', 'New Zealand Dollar'), ('AED', 'UAE Dirham');

-- Per-user watched currency pairs.
create table public.watchlist (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    base_code text not null references public.currencies (code),
    quote_code text not null references public.currencies (code),
    created_at timestamptz not null default now(),
    unique (user_id, base_code, quote_code)
);

alter table public.watchlist enable row level security;

create policy "watchlist_owner_select" on public.watchlist
    for select using (auth.uid() = user_id);
create policy "watchlist_owner_insert" on public.watchlist
    for insert with check (auth.uid() = user_id);
create policy "watchlist_owner_update" on public.watchlist
    for update using (auth.uid() = user_id);
create policy "watchlist_owner_delete" on public.watchlist
    for delete using (auth.uid() = user_id);

-- Cached daily exchange rates (written by the backend/cron via service role only).
create table public.rates_cache (
    id bigserial primary key,
    base_code text not null references public.currencies (code),
    quote_code text not null references public.currencies (code),
    rate numeric not null,
    as_of date not null,
    fetched_at timestamptz not null default now(),
    unique (base_code, quote_code, as_of)
);

alter table public.rates_cache enable row level security;
create policy "rates_cache_public_read" on public.rates_cache
    for select using (true);

-- Generated predictions (written by the backend/cron via service role only).
create table public.predictions (
    id bigserial primary key,
    base_code text not null references public.currencies (code),
    quote_code text not null references public.currencies (code),
    horizon_days integer not null,
    predicted_rate numeric not null,
    lower_bound numeric not null,
    upper_bound numeric not null,
    confidence text not null check (confidence in ('normal', 'low')),
    generated_at timestamptz not null default now()
);

alter table public.predictions enable row level security;
create policy "predictions_public_read" on public.predictions
    for select using (true);

-- User-defined alerts.
create table public.alerts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    base_code text not null references public.currencies (code),
    quote_code text not null references public.currencies (code),
    alert_type text not null check (alert_type in ('threshold', 'recommendation_change')),
    threshold_rate numeric,
    direction text check (direction in ('above', 'below')),
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

alter table public.alerts enable row level security;

create policy "alerts_owner_select" on public.alerts
    for select using (auth.uid() = user_id);
create policy "alerts_owner_insert" on public.alerts
    for insert with check (auth.uid() = user_id);
create policy "alerts_owner_update" on public.alerts
    for update using (auth.uid() = user_id);
create policy "alerts_owner_delete" on public.alerts
    for delete using (auth.uid() = user_id);

-- Per-user notification linking state.
create table public.notification_settings (
    user_id uuid primary key references auth.users (id) on delete cascade,
    telegram_chat_id text,
    telegram_linked_at timestamptz,
    email_verified boolean not null default false,
    email_verified_at timestamptz
);

alter table public.notification_settings enable row level security;

create policy "notification_settings_owner_select" on public.notification_settings
    for select using (auth.uid() = user_id);
create policy "notification_settings_owner_insert" on public.notification_settings
    for insert with check (auth.uid() = user_id);
create policy "notification_settings_owner_update" on public.notification_settings
    for update using (auth.uid() = user_id);

-- Per-user LLM provider configuration.
create table public.llm_settings (
    user_id uuid primary key references auth.users (id) on delete cascade,
    provider text not null check (provider in ('gemini', 'openai', 'deepseek', 'groq', 'openrouter')),
    api_key_encrypted text not null,
    model text,
    updated_at timestamptz not null default now()
);

alter table public.llm_settings enable row level security;

create policy "llm_settings_owner_select" on public.llm_settings
    for select using (auth.uid() = user_id);
create policy "llm_settings_owner_insert" on public.llm_settings
    for insert with check (auth.uid() = user_id);
create policy "llm_settings_owner_update" on public.llm_settings
    for update using (auth.uid() = user_id);
```

- [ ] **Step 2: Write `backend/SUPABASE_SETUP.md` with manual setup instructions**

```markdown
# Supabase Setup

1. Create a free project at https://supabase.com (Free tier, no card required
   for the base plan at time of writing).
2. In Project Settings -> API, copy:
   - `Project URL` -> `SUPABASE_URL`
   - `service_role` secret key -> `SUPABASE_SERVICE_KEY`
   - `anon` public key -> `VITE_SUPABASE_ANON_KEY` (frontend)
3. In Project Settings -> API -> JWT Settings, copy the `JWT Secret` ->
   `SUPABASE_JWT_SECRET`.
4. In Authentication -> Providers, enable "Email" and "Google" (Google
   requires a free Google Cloud OAuth client ID/secret, configured per
   Supabase's Google provider docs).
5. In the SQL Editor, paste and run `supabase/migrations/0001_init_schema.sql`.
6. Verify: run `select table_name from information_schema.tables where
   table_schema = 'public';` and confirm all 7 tables
   (currencies, watchlist, rates_cache, predictions, alerts,
   notification_settings, llm_settings) are listed.
7. Verify RLS: in the SQL Editor, run
   `select * from public.watchlist;` while authenticated as the `anon` role
   (Supabase's SQL editor runs as a superuser by default — use the API
   "Run as" feature or the REST API with the anon key to confirm an
   unauthenticated request returns an empty result, not an error and not
   other users' rows).
```

- [ ] **Step 3: Manual verification**

Follow `backend/SUPABASE_SETUP.md` steps 1-7 against a real free Supabase
project. Confirm the table list query in step 6 returns all 7 tables, and the
RLS check in step 7 behaves as documented.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/0001_init_schema.sql backend/SUPABASE_SETUP.md
git commit -m "feat(db): add Supabase schema migration and setup guide"
```

---

### Task 4: Frontend scaffolding (Vite + React + TypeScript + PWA)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/setupTests.ts`
- Create: `frontend/.env.example`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: `App` (default export) in `frontend/src/App.tsx` — a `BrowserRouter`-wrapped component; later tasks add routes and wrap it with `AuthProvider`.

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "forexcast-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest"
  },
  "dependencies": {
    "@supabase/supabase-js": "^2.45.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "jsdom": "^25.0.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "vite-plugin-pwa": "^0.20.0",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.ts`**

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'ForexCast',
        short_name: 'ForexCast',
        display: 'standalone',
        start_url: '/',
        theme_color: '#0f172a',
        icons: [],
      },
    }),
  ],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
    env: {
      VITE_SUPABASE_URL: 'https://test.supabase.co',
      VITE_SUPABASE_ANON_KEY: 'test-anon-key',
      VITE_API_BASE_URL: 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 3: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4: Create `frontend/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 5: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ForexCast</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create `frontend/src/setupTests.ts`**

```ts
import '@testing-library/jest-dom'
```

- [ ] **Step 7: Create `frontend/.env.example`**

```
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_API_BASE_URL=http://localhost:8000
```

- [ ] **Step 8: Write the failing test**

`frontend/src/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the home placeholder', () => {
    render(<App />)
    expect(screen.getByText('ForexCast')).toBeInTheDocument()
  })
})
```

- [ ] **Step 9: Install dependencies**

Run: `npm install --prefix frontend`
Expected: installs without errors.

- [ ] **Step 10: Run the test to verify it fails**

Run: `npm run test --prefix frontend -- --run`
Expected: FAIL (`./App` has no default export / file doesn't exist).

- [ ] **Step 11: Implement `frontend/src/App.tsx`**

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'

function Home() {
  return <div>ForexCast</div>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 12: Implement `frontend/src/main.tsx`**

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 13: Run the test to verify it passes**

Run: `npm run test --prefix frontend -- --run`
Expected: PASS (1 test).

- [ ] **Step 14: Verify the production build succeeds**

Run: `npm run build --prefix frontend`
Expected: builds without TypeScript errors.

- [ ] **Step 15: Commit**

```bash
git add frontend/package.json frontend/vite.config.ts frontend/tsconfig.json frontend/tsconfig.node.json frontend/index.html frontend/src frontend/.env.example
git commit -m "feat(frontend): scaffold Vite/React/TypeScript PWA shell"
```

---

### Task 5: Supabase client and AuthContext

**Files:**
- Create: `frontend/src/lib/supabaseClient.ts`
- Create: `frontend/src/contexts/AuthContext.tsx`
- Test: `frontend/src/contexts/AuthContext.test.tsx`

**Interfaces:**
- Consumes: `import.meta.env.VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` (Task 4's Vite env config).
- Produces: `supabase` client in `frontend/src/lib/supabaseClient.ts`. `AuthProvider` (component) and `useAuth()` hook in `frontend/src/contexts/AuthContext.tsx`, returning `{ session: Session | null, loading: boolean, signInWithPassword(email, password): Promise<{error: string | null}>, signInWithGoogle(): Promise<void>, signOut(): Promise<void> }`.

- [ ] **Step 1: Write the failing test**

`frontend/src/contexts/AuthContext.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'

vi.mock('../lib/supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
      signInWithPassword: vi.fn(),
      signInWithOAuth: vi.fn(),
      signOut: vi.fn(),
    },
  },
}))

function Probe() {
  const { session, loading } = useAuth()
  if (loading) return <div>loading</div>
  return <div>{session ? 'authenticated' : 'anonymous'}</div>
}

describe('AuthProvider', () => {
  it('starts loading then resolves to anonymous with no session', async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByText('anonymous')).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test --prefix frontend -- --run AuthContext`
Expected: FAIL (module `./AuthContext` doesn't exist).

- [ ] **Step 3: Implement `frontend/src/lib/supabaseClient.ts`**

```ts
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment configuration')
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

- [ ] **Step 4: Implement `frontend/src/contexts/AuthContext.tsx`**

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from '../lib/supabaseClient'

interface AuthContextValue {
  session: Session | null
  loading: boolean
  signInWithPassword: (email: string, password: string) => Promise<{ error: string | null }>
  signInWithGoogle: () => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })

    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession)
    })

    return () => listener.subscription.unsubscribe()
  }, [])

  async function signInWithPassword(email: string, password: string) {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    return { error: error ? error.message : null }
  }

  async function signInWithGoogle() {
    await supabase.auth.signInWithOAuth({ provider: 'google' })
  }

  async function signOut() {
    await supabase.auth.signOut()
  }

  return (
    <AuthContext.Provider
      value={{ session, loading, signInWithPassword, signInWithGoogle, signOut }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm run test --prefix frontend -- --run AuthContext`
Expected: PASS (1 test).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/supabaseClient.ts frontend/src/contexts/AuthContext.tsx frontend/src/contexts/AuthContext.test.tsx
git commit -m "feat(frontend): add Supabase client and AuthContext"
```

---

### Task 6: Login page and route

**Files:**
- Create: `frontend/src/pages/Login.tsx`
- Test: `frontend/src/pages/Login.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `useAuth()` from Task 5's `AuthContext`.
- Produces: `Login` (default export) in `frontend/src/pages/Login.tsx`. `App` now wraps its routes in `AuthProvider` and registers `/login`.

- [ ] **Step 1: Write the failing test**

`frontend/src/pages/Login.test.tsx`:

```tsx
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
    fireEvent.click(screen.getByText('Log in'))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Invalid credentials'),
    )
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test --prefix frontend -- --run Login`
Expected: FAIL (module `./Login` doesn't exist).

- [ ] **Step 3: Implement `frontend/src/pages/Login.tsx`**

```tsx
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function Login() {
  const { signInWithPassword, signInWithGoogle } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const { error: signInError } = await signInWithPassword(email, password)
    if (signInError) {
      setError(signInError)
      return
    }
    navigate('/dashboard')
  }

  return (
    <div>
      <h1>Log in</h1>
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
        <button type="submit">Log in</button>
      </form>
      <button onClick={signInWithGoogle}>Continue with Google</button>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
```

- [ ] **Step 4: Modify `frontend/src/App.tsx`** to wrap routes in `AuthProvider` and add `/login`

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import Login from './pages/Login'

function Home() {
  return <div>ForexCast</div>
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm run test --prefix frontend -- --run Login`
Expected: PASS (1 test).

- [ ] **Step 6: Run the full frontend suite to check nothing broke**

Run: `npm run test --prefix frontend -- --run`
Expected: PASS (all tests, including Task 4's `App.test.tsx`).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Login.tsx frontend/src/pages/Login.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add login page with email/password and Google sign-in"
```

---

### Task 7: Protected route, API client, and Dashboard

**Files:**
- Create: `frontend/src/components/ProtectedRoute.tsx`
- Test: `frontend/src/components/ProtectedRoute.test.tsx`
- Create: `frontend/src/lib/apiClient.ts`
- Test: `frontend/src/lib/apiClient.test.ts`
- Create: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `useAuth()` (Task 5), backend `GET /me` (Task 2).
- Produces: `ProtectedRoute` (default export, wraps children, redirects to `/login` if unauthenticated). `fetchCurrentUser(): Promise<{user_id: string}>` in `frontend/src/lib/apiClient.ts`. `Dashboard` (default export) in `frontend/src/pages/Dashboard.tsx`.

- [ ] **Step 1: Write the failing test for ProtectedRoute**

`frontend/src/components/ProtectedRoute.test.tsx`:

```tsx
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
      signInWithGoogle: vi.fn(),
      signOut: vi.fn(),
    })
    renderAt('/dashboard')
    expect(screen.getByText('secret dashboard')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test --prefix frontend -- --run ProtectedRoute`
Expected: FAIL (module doesn't exist).

- [ ] **Step 3: Implement `frontend/src/components/ProtectedRoute.tsx`**

```tsx
import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()
  if (loading) return <div>Loading...</div>
  if (!session) return <Navigate to="/login" replace />
  return <>{children}</>
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test --prefix frontend -- --run ProtectedRoute`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing test for apiClient**

`frontend/src/lib/apiClient.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchCurrentUser } from './apiClient'
import { supabase } from './supabaseClient'

vi.mock('./supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: vi.fn(),
    },
  },
}))

describe('fetchCurrentUser', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('throws when there is no access token', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: null },
    } as never)

    await expect(fetchCurrentUser()).rejects.toThrow('Not authenticated')
  })

  it('calls the backend with the bearer token and returns the user id', async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: { access_token: 'abc123' } },
    } as never)
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ user_id: 'user-123' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchCurrentUser()

    expect(result).toEqual({ user_id: 'user-123' })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/me',
      expect.objectContaining({ headers: { Authorization: 'Bearer abc123' } }),
    )
  })
})
```

- [ ] **Step 6: Run test to verify it fails**

Run: `npm run test --prefix frontend -- --run apiClient`
Expected: FAIL (module doesn't exist).

- [ ] **Step 7: Implement `frontend/src/lib/apiClient.ts`**

```ts
import { supabase } from './supabaseClient'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

export async function fetchCurrentUser(): Promise<{ user_id: string }> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new Error('Not authenticated')

  const response = await fetch(`${API_BASE_URL}/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error(`Request failed: ${response.status}`)
  return response.json()
}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `npm run test --prefix frontend -- --run apiClient`
Expected: PASS (2 tests).

- [ ] **Step 9: Implement `frontend/src/pages/Dashboard.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { fetchCurrentUser } from '../lib/apiClient'
import { useAuth } from '../contexts/AuthContext'

export default function Dashboard() {
  const { signOut } = useAuth()
  const [userId, setUserId] = useState<string | null>(null)

  useEffect(() => {
    fetchCurrentUser()
      .then((data) => setUserId(data.user_id))
      .catch(() => setUserId(null))
  }, [])

  return (
    <div>
      <h1>Dashboard</h1>
      <p>Signed in as: {userId ?? 'loading...'}</p>
      <button onClick={signOut}>Sign out</button>
    </div>
  )
}
```

- [ ] **Step 10: Modify `frontend/src/App.tsx`** to add the protected `/dashboard` route

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import ProtectedRoute from './components/ProtectedRoute'

function Home() {
  return <div>ForexCast</div>
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
```

- [ ] **Step 11: Run the full frontend suite**

Run: `npm run test --prefix frontend -- --run`
Expected: PASS (all tests).

- [ ] **Step 12: Verify the production build still succeeds**

Run: `npm run build --prefix frontend`
Expected: builds without TypeScript errors.

- [ ] **Step 13: Commit**

```bash
git add frontend/src/components/ProtectedRoute.tsx frontend/src/components/ProtectedRoute.test.tsx frontend/src/lib/apiClient.ts frontend/src/lib/apiClient.test.ts frontend/src/pages/Dashboard.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add protected dashboard wired to the backend"
```

---

### Task 8: Continuous integration

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `backend/requirements.txt`, `backend/requirements-dev.txt` (Task 1), `frontend/package.json` (Task 4).
- Produces: none consumed by later tasks — this is a leaf task.

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest -v

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npm run test -- --run
      - run: npm run build
```

- [ ] **Step 2: Verify locally before pushing**

Run: `pytest backend/tests -v`
Expected: PASS.

Run: `npm run test --prefix frontend -- --run && npm run build --prefix frontend`
Expected: PASS, build succeeds.

- [ ] **Step 3: Commit and push, then confirm the Actions run is green**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run backend and frontend test suites on push"
git push
```

Then check the repository's Actions tab and confirm both `backend` and
`frontend` jobs pass.

---

### Task 9: Free-tier deployment

**Files:**
- Create: `render.yaml`
- Create: `DEPLOYMENT.md`
- Modify: `backend/app/config.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_health.py`
- Modify: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `Settings` (Task 1), `app` (Task 1/2).
- Produces: `Settings.frontend_origin: str` (new field, default `"http://localhost:5173"`), used by CORS config — no other task depends on this.

- [ ] **Step 1: Modify `backend/app/config.py`** to add a configurable frontend origin

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_service_key: str
    supabase_jwt_secret: str
    frontend_origin: str = "http://localhost:5173"
```

- [ ] **Step 2: Modify `backend/app/main.py`** to use it for CORS

```python
from app.config import get_settings
from app.routers import health, me

app = FastAPI(title="ForexCast API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(me.router)
```

- [ ] **Step 3: Modify `backend/tests/test_health.py` and `backend/tests/test_auth.py`** fixtures to set the new env var (keeps tests explicit even though the field has a default)

Add this line inside `_configure_settings` in both files, alongside the existing `monkeypatch.setenv(...)` calls:

```python
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173")
```

- [ ] **Step 4: Run the full backend suite to confirm nothing broke**

Run: `pytest backend/tests -v`
Expected: PASS (all tests).

- [ ] **Step 5: Create `render.yaml`**

```yaml
services:
  - type: web
    name: forexcast-api
    env: python
    plan: free
    buildCommand: pip install -r backend/requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend
    envVars:
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SERVICE_KEY
        sync: false
      - key: SUPABASE_JWT_SECRET
        sync: false
      - key: FRONTEND_ORIGIN
        sync: false
```

- [ ] **Step 6: Create `DEPLOYMENT.md`**

```markdown
# Deployment (free tier)

## Backend — Render

1. Create a free account at https://render.com.
2. New -> Blueprint, point it at this repo (`render.yaml` will be detected).
3. Set the four environment variables (`SUPABASE_URL`,
   `SUPABASE_SERVICE_KEY`, `SUPABASE_JWT_SECRET`, `FRONTEND_ORIGIN`) in the
   Render dashboard — `FRONTEND_ORIGIN` should be the Vercel URL from the
   step below (leave as `http://localhost:5173` until that URL exists, then
   update it).
4. Deploy. Note the resulting backend URL
   (e.g. `https://forexcast-api.onrender.com`).

## Frontend — Vercel

1. Create a free account at https://vercel.com.
2. Import this repo, set the project root to `frontend/`.
3. Set environment variables: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
   (from Supabase), and `VITE_API_BASE_URL` (the Render backend URL from
   above).
4. Deploy. Note the resulting frontend URL, then go back to Render and set
   `FRONTEND_ORIGIN` to this URL (redeploy the backend for it to take
   effect).

## Smoke test

1. `curl https://<your-render-url>/health` — expect
   `{"status": "ok", "supabase_reachable": true}`.
2. Open `https://<your-vercel-url>/login` in a browser, sign up with email,
   and confirm you land on `/dashboard` showing `Signed in as: <your user
   id>`.
```

- [ ] **Step 7: Commit**

```bash
git add render.yaml DEPLOYMENT.md backend/app/config.py backend/app/main.py backend/tests/test_health.py backend/tests/test_auth.py
git commit -m "feat(deploy): add free-tier Render/Vercel deployment config"
```

- [ ] **Step 8: Manual deployment and smoke test**

Follow `DEPLOYMENT.md` end to end against real free Render/Vercel accounts.
Confirm both checks in the "Smoke test" section pass.

---

## Definition of Done

- `pytest backend/tests -v` passes (10 tests across health/auth).
- `npm run test --prefix frontend -- --run` passes (all frontend tests).
- `npm run build --prefix frontend` succeeds.
- GitHub Actions CI is green on the repo's default branch.
- The deployed frontend allows signup/login (email or Google) and shows an
  authenticated dashboard with the correct user id, proving Supabase Auth,
  the FastAPI backend, and the React frontend are correctly wired together
  end to end on entirely free infrastructure.
