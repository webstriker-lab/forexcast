# Deployment (free tier)

## Backend — Render

1. Create a free account at https://render.com.
2. New -> Blueprint, point it at this repo (`render.yaml` will be detected).
3. Set these environment variables in the Render dashboard:
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — required.
   - `FRONTEND_ORIGIN` — the Vercel URL from the step below (leave as
     `http://localhost:5173` until that URL exists, then update it).
   - `LLM_SETTINGS_PRIVATE_KEY` — required for the chat feature (`POST
     /chat`) to work at all. Generate a keypair with:
     `python -c "from nacl.public import PrivateKey; import base64; k = PrivateKey.generate(); print('PRIVATE=' + base64.b64encode(bytes(k)).decode()); print('PUBLIC=' + base64.b64encode(bytes(k.public_key)).decode())"`
     — set the `PRIVATE` value here, and set the `PUBLIC` value as the
     frontend's `VITE_LLM_SETTINGS_PUBLIC_KEY` below (they must be from the
     *same* generated pair).
4. Deploy. Note the resulting backend URL
   (e.g. `https://forexcast-api.onrender.com`).

## Scheduled jobs — GitHub Actions

The `.github/workflows/*.yml` cron jobs (rate ingestion, forecasting,
news-sentiment scoring, recommendations, notifications, macro data) run
independently of the Render web service — they need their own secrets
under the repo's **Settings -> Secrets and variables -> Actions**, not the
Render dashboard:

- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — every job needs these.
- `FRED_API_KEY` — `macro.yml` only.
- `OPENROUTER_API_KEY` (and optionally `LLM_API_KEY`/`LLM_PROVIDER` to
  force a specific provider) — `news.yml` only.
- `TELEGRAM_BOT_TOKEN` — `notify.yml` only.

Each job simply does nothing for its own feature if its key is missing —
a missing `TELEGRAM_BOT_TOKEN`, for instance, doesn't break rate
ingestion or forecasting.

## Frontend — Vercel

1. Create a free account at https://vercel.com.
2. Import this repo, set the project root to `frontend/`.
3. Set environment variables:
   - `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (from Supabase's
     Settings -> API page).
   - `VITE_API_BASE_URL` — the Render backend URL from above.
   - `VITE_LLM_SETTINGS_PUBLIC_KEY` — the `PUBLIC` value generated
     alongside Render's `LLM_SETTINGS_PRIVATE_KEY` above. Without this set,
     Settings will refuse to save an LLM API key (with a clear error, not
     silently) and the chat feature stays unusable, but everything else in
     the app works fine.
4. Deploy. Note the resulting frontend URL, then go back to Render and set
   `FRONTEND_ORIGIN` to this URL (redeploy the backend for it to take
   effect).

   Note: Vercel's `.vercel.app` subdomains are a global namespace shared
   across all Vercel users, not scoped to your account -- if the plain
   project name is already taken by someone else, Vercel silently
   assigns a suffixed alias instead (e.g. `forexcast-eight.vercel.app`
   rather than `forexcast.vercel.app`). Always confirm the actual URL via
   `vercel project ls` or the dashboard's "Domains" tab rather than
   assuming `<project-name>.vercel.app` -- this app's real production URL
   is **`https://forexcast-eight.vercel.app`**, not `forexcast.vercel.app`.

   Note: `frontend/vercel.json` is committed in the repo and auto-detected
   by Vercel — it adds a SPA rewrite rule so deep links like `/login` and
   `/dashboard` don't 404 on refresh. No manual configuration needed.
5. Also make sure Supabase's Authentication -> URL Configuration includes
   this Vercel URL in Site URL / Additional Redirect URLs (see
   `backend/SUPABASE_SETUP.md`), otherwise Google sign-in will redirect
   users to the wrong place.

## Smoke test

1. `curl https://<your-render-url>/health` — expect
   `{"status": "ok", "supabase_reachable": true}`.
2. Open `https://<your-vercel-url>/login`, click "Don't have an account?
   Sign up", and submit an email/password.
   - If Supabase's "Confirm email" setting is on (the default — see
     `backend/SUPABASE_SETUP.md`), you'll see a message asking you to check
     your email; click the confirmation link, then come back and log in
     with the same credentials.
   - If you disabled "Confirm email", signing up logs you in immediately.
3. Confirm you land on `/dashboard` and can add a currency pair (e.g.
   USD -> EUR) via the picker at the top — it should appear as a chip and
   show a rate chart once selected (empty until the ingestion/prediction
   jobs have run at least once).
