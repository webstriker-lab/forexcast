# Supabase Setup

1. Create a free project at https://supabase.com (Free tier, no card required
   for the base plan at time of writing).
2. In Project Settings -> API, copy:
   - `Project URL` -> `SUPABASE_URL`
   - `service_role` secret key (or the newer `sb_secret_...` key) ->
     `SUPABASE_SERVICE_KEY`
   - `anon` public key (or the newer `sb_publishable_...` key) ->
     `VITE_SUPABASE_ANON_KEY` (frontend)
3. No `SUPABASE_JWT_SECRET` is needed. This backend
   (`backend/app/auth.py`) verifies tokens against Supabase's JWKS endpoint
   (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`) using the project's
   asymmetric signing key (ES256/RS256) — this is the default for new
   Supabase projects (Project Settings -> JWT Signing Keys). JWKS only
   publishes asymmetric public keys, so this does *not* work for a project
   whose current signing key is still the legacy HS256 shared secret; if
   yours is, either migrate it to an asymmetric key in that dashboard
   section, or note that new logins issued under a legacy-HS256-only
   project will fail auth here until you do.
4. In Authentication -> Providers, enable "Email" and "Google" (Google
   requires a free Google Cloud OAuth client ID/secret, configured per
   Supabase's Google provider docs).
   - Note: Supabase's "Confirm email" setting (Authentication -> Providers
     -> Email -> "Confirm email") is **ON by default**, meaning a user who
     signs up via email/password gets no session until they click the
     confirmation link sent to their inbox. For this project's private
     friend-group use case, you have two options:
     - **Disable it** (Authentication -> Providers -> Email -> toggle
       "Confirm email" off) for frictionless onboarding — anyone who signs
       up can log in immediately.
     - **Leave it on** — frictionless it is not, but it does stop randos
       from registering with an email they don't own. Users must click the
       confirmation link in their email before their first login; the
       frontend's signup form already shows a message telling them to do
       this.
   - Also under Authentication -> URL Configuration, set the **Site URL**
     and add to **Additional Redirect URLs** both your deployed Vercel URL
     (e.g. `https://your-app.vercel.app`) and `http://localhost:5173` for
     local dev. This is required for Google OAuth sign-in to redirect back
     to the app instead of Supabase's default URL.
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
