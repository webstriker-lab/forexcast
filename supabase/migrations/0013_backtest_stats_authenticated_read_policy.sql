-- Allow authenticated users to read backtest_stats.
-- The service role (used by the weekly backtest job) bypasses RLS and can still write.
DO $$
BEGIN
  CREATE POLICY "authenticated users can read backtest_stats"
    ON public.backtest_stats FOR SELECT TO authenticated USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
