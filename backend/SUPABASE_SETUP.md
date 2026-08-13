# Supabase Setup

1. Create a free project at https://supabase.com (Free tier, no card required
   for the base plan at time of writing).
2. In Project Settings -> API, copy:
   - `Project URL` -> `SUPABASE_URL`
   - `service_role` secret key -> `SUPABASE_SERVICE_KEY`
   - `anon` public key -> `VITE_SUPABASE_ANON_KEY` (frontend)
3. In Project Settings -> API -> JWT Settings, copy the `JWT Secret` ->
   `SUPABASE_JWT_SECRET`. Note: this backend (`backend/app/auth.py`) only
   verifies tokens with the **legacy HS256 shared secret** — it does not
   support the newer asymmetric/JWKS-based signing keys that some
   newer Supabase projects use by default. Before copying the secret,
   confirm your project's JWT signing method is the legacy HS256 type
   (depending on your dashboard version, this may be under a "Legacy API
   Keys" or "JWT Settings" section rather than the default JWT signing keys
   view). If your project only offers asymmetric signing keys, every
   backend request will fail with a generic 401 and no useful diagnostic —
   switch the project to (or provision it with) the legacy HS256 secret
   first.
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
