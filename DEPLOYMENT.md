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
3. Confirm you land on `/dashboard` showing `Signed in as: <your user id>`.
