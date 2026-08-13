# ForexCast — Forex Rate Predictor (Phase 1 Design)

**Status:** Approved for planning
**Date:** 2026-08-13
**Scope:** Phase 1 only — the forex prediction product. The debt savings planner
and motivational-charms/gamification module is explicitly out of scope for this
spec; see [Phase 2](#phase-2--explicitly-out-of-scope-tracked-for-later) below.

## 1. Problem & Users

Ashwath and a small group of friends want a tool to decide *when* to convert
money between currencies — for travel, remittances, and paying off
foreign-currency obligations. The core question the app answers is not "what
will the rate be" in isolation, but **"should I act now, or is it worth
waiting?"** — grounded in real data, not vibes, and honest about how
unreliable forex forecasting fundamentally is.

Users: a private group (Ashwath + friends), each with their own account,
watched currency pairs, and alerts. Not a public product.

## 2. Architecture

- **Backend:** Python (FastAPI). Owns the forecasting pipeline, the LLM agent
  (tool-calling), and all external data fetching. Python is chosen because the
  mature, free time-series/statistics tooling (`statsmodels`, `pandas`) lives
  there — no reason to reimplement forecasting math in JS.
- **Frontend:** React, mobile-responsive (installable as a PWA — no app store
  needed, but usable full-screen from a phone home screen). Dashboard, graph,
  chat panel, settings.
- **Database + Auth:** Supabase free tier. Postgres for rates, predictions,
  alerts, and user settings; built-in email+password and Google OAuth cover
  the login requirement; row-level security isolates each user's data.
- **Scheduling:** GitHub Actions cron (free), self-contained in the repo. Runs
  scheduled jobs against the database directly (rate refresh, prediction
  recompute, alert/recommendation evaluation, notification dispatch) without
  depending on a backend web server staying awake — important because free
  web-hosting tiers sleep when idle. This was chosen over delegating to the
  user's personal Hermes Agent instance (which also offers cron-via-REST)
  specifically so the app is self-contained: anyone who deploys their own copy
  gets working schedules with no external dependency on Ashwath's own
  infrastructure staying up.
- **Hosting:** frontend on a free static/edge host (e.g. Vercel/Netlify free
  tier); backend on a free web-service tier (e.g. Render free tier), accepting
  that on-demand requests may cold-start — acceptable at this scale since
  usage is a small friend group, and none of the time-sensitive work (data
  refresh, alerts) depends on the backend being awake.

## 3. Data Sources (all free)

- **Exchange rates:** Frankfurter API — free, no key, ECB reference rates,
  full history. Covers the ~20-30 major currencies in scope.
- **News/events:** GDELT — free, no key, global news/event database. Used as
  raw input to the LLM news-analysis step (see §5). Event types are **not**
  restricted to a fixed list (war, elections, sanctions, etc. are examples,
  not the complete set) — the LLM extracts and summarizes whatever is
  actually relevant to a given currency pair from the available headlines,
  in its own words.
- **Macroeconomic indicators:** FRED API — free (requires a free key),
  interest rates, inflation, GDP, used as regression features.

Currency scope: a curated list of ~20-30 major, liquid currencies (USD, EUR,
GBP, INR, JPY, AUD, CAD, etc.). Exotic/thinly-traded currencies are excluded
because free data sources and news coverage are too sparse to produce a
trustworthy forecast for them.

## 4. Prediction Pipeline

- **Model:** a classical statistical time-series model (exponential smoothing
  / ARIMA via `statsmodels`) as the numeric baseline, adjusted by a regression
  layer using interest-rate differentials (from FRED) and an LLM-derived
  news-sentiment/event score (from GDELT). Deep learning (LSTM/Transformer) is
  deliberately deferred: forex prices are close to a random walk, and without
  large data/compute investment, deep models rarely beat well-tuned classical
  ones for this problem — they'd also be harder to backtest and explain on a
  free-tier budget.
- **Backtesting:** every model run is backtested against held-out historical
  windows to compute actual historical error (e.g. MAE at 30/90/365-day
  horizons). That measured error — not a guessed number — becomes the
  confidence band shown on the graph.
- **Low-confidence handling:** when recent volatility is far outside
  historical norms (e.g. a shock event), the pipeline flags the pair as
  low-confidence/volatile rather than emitting a falsely precise number.
- **Horizons:** 7-day, 30-day, 90-day, and 1-year predictions, recomputed
  daily by the scheduled job.

## 5. Recommendation Engine

Rather than a single "notify at threshold" rule, the system continuously
compares the current real rate to where the forecast (with its confidence
band) says the rate is heading, and produces one of:

- **ACT NOW** — current rate is near the best point the model expects within
  the user's horizon.
- **WAIT (~N days)** — model expects a more favorable rate soon, shown with
  its own confidence band.
- **VOLATILE / LOW CONFIDENCE** — the model declines to recommend because
  recent conditions are outside historical norms.

This recommendation is what drives proactive notifications (e.g. it flips
from WAIT to ACT NOW) and what the LLM agent narrates in plain language. On
top of it, users can still set manual hard thresholds (e.g. "tell me the
moment USD→INR crosses 85") for concrete fixed goals — this is simple,
deterministic, and complements the smarter recommendation rather than
replacing it.

## 6. LLM Agent

- **Role:** research + explain + chat — not the forecaster. The numeric model
  (§4) owns the actual prediction; the LLM turns raw news into structured
  signal (an input to §4) and turns numeric output into plain-language
  explanation, and provides a conversational interface over the same tools
  the UI uses.
- **Provider-agnostic:** each user configures their own API key in Settings,
  choosing from Google Gemini, OpenAI, DeepSeek, Groq, or OpenRouter (which
  can itself route to many additional models, free and paid). A single
  adapter layer normalizes tool-calling across providers, since most already
  expose OpenAI-compatible chat/tool APIs. Keys are stored encrypted,
  per-user, in Supabase.
- **Tools exposed to the agent:** `get_forecast(pair, horizon)`,
  `get_news_summary(pair)`, `get_recommendation(pair)`, `create_alert`,
  `list_alerts`, `update_alert`, `delete_alert`. The chat interface is a thin
  natural-language layer over these same tools — anything doable in the UI
  (e.g. "alert me if EUR/USD drops below 1.05") is doable by asking the agent,
  and its answers are grounded in the actual tool outputs, never invented.

## 7. Notifications

- **Channels:** Telegram and email, both required to reach users reliably on
  mobile and inbox.
- **In-app setup (no manual configuration):** a Settings page lets a user link
  Telegram by clicking a button that opens a deep link to message the app's
  bot with a one-time connect code, and verify an email address inline —
  no manual bot setup or external steps.
- **Triggers:** recommendation changes (e.g. WAIT → ACT NOW), manual threshold
  crossings, and volatility flags.

## 8. Auth & Accounts

Simple login via Supabase Auth: email+password or Google OAuth. Each user has
their own watched currency pairs, alerts, LLM provider/API key, and
notification settings, isolated via row-level security.

## 9. Error Handling

- If a data source (rates/news/macro) is unreachable, the app serves the last
  successfully cached value and visibly marks it as stale — never fails
  silently or fabricates a value.
- If backtested error for a pair is too high to be meaningful, the UI shows
  "insufficient reliable data for this pair" instead of a misleading graph.
- Every prediction view carries a persistent "not financial advice"
  disclaimer, given forex's inherent unpredictability and the real-money
  decisions this tool informs.

## 10. Testing Strategy

- The backtesting harness (§4) doubles as the core correctness check for the
  forecasting model — measured error must stay within documented bounds.
- Unit tests for recommendation logic (ACT NOW / WAIT / VOLATILE thresholds)
  and alert evaluation.
- Integration tests for the agent's tool-calling — does it call the correct
  tool for a given question, does it refuse to invent numbers when tool data
  is unavailable.
- Manual verification of the dashboard and chat on mobile viewport sizes.

## Phase 2 — Explicitly Out of Scope (tracked for later)

Debt savings planner (input debt/income/savings, get a payoff timeline and
milestone tracking, multi-currency debt using the forecast from Phase 1) plus
motivational charms/gamification (mascot, streaks, badges). This gets its own
design spec after Phase 1 ships, reusing the currency data layer built here.
