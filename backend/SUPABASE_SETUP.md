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
