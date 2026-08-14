# ForexCast — Data Ingestion Pipeline (Design)

**Status:** Approved for planning
**Date:** 2026-08-14
**Scope:** First data-ingestion increment — exchange rates only. See [Deferred](#deferred-gdelt--fred) below for what's explicitly out of scope here and why.

## 1. Goal

Populate `public.rates_cache` with real exchange-rate history and keep it current, on entirely free infrastructure, so the prediction engine (next roadmap item) has real data to backtest against as soon as it's built.

## 2. Scope

**In scope:**
- Daily ingestion of exchange rates for all Frankfurter-supported currencies via a GitHub Actions cron job.
- A one-time historical backfill of full available history (from `1999-01-04`, Frankfurter's earliest date — confirmed live) so the prediction engine's backtesting harness has data spanning multiple market regimes on day one. Storage is cheap enough under the pivot model (§5) that there's no reason to truncate short of the source's own limit.
- Expanding `public.currencies` to the full Frankfurter-supported set (~30 currencies), dropping `AED` (unsupported by the data source).

**Deferred — GDELT / FRED:**
The roadmap note in the foundation plan originally bundled Frankfurter (rates), GDELT (news), and FRED (macro indicators) into one "data ingestion pipeline" task. Neither GDELT nor FRED has a consumer yet — both only become useful once the prediction engine's regression/sentiment layer exists to use them. Building ingestion for data nothing reads yet is premature; GDELT and FRED ingestion will be scoped and built alongside the prediction engine task instead, where they have a real consumer to validate against. The foundation plan's roadmap note has been updated to reflect this split.

## 3. Data Source

**Frankfurter API** (`api.frankfurter.dev`) — free, no key, ECB reference rates, full history back to 1999. Verified directly against the live API during design:

- One call (`base=USD`, all other currency codes as `symbols`) returns a full day's rates for every currency in one response.
- One call can retrieve a multi-year range (`/v1/{start}..{end}`) — a 5.5-year, all-currency range request returned 1,435 business days in a single ~564KB response, no pagination.
- Non-trading days (weekends/holidays) aren't published; querying one returns the prior business day's data, correctly labeled with that day's actual date (not the requested date) — so a daily cron running every day of the week never mislabels data, and re-running on a non-trading day just re-upserts data already present (harmless, deduplicated by the existing `unique(base_code, quote_code, as_of)` constraint).
- Older dates have partial currency coverage (e.g. `ILS`, `BRL`, `CNY`, `INR` are absent from a `2000-01-03` query — those currencies weren't in ECB's published set that far back). The API omits missing currencies from the response rather than erroring; ingestion must handle partial responses per day, not assume all currencies are always present.

## 4. Currency Set

Frankfurter supports exactly 30 currencies (including EUR): `AUD, BRL, CAD, CHF, CNY, CZK, DKK, EUR, GBP, HKD, HUF, IDR, ILS, INR, ISK, JPY, KRW, MXN, MYR, NOK, NZD, PHP, PLN, RON, SEK, SGD, THB, TRY, USD, ZAR`. This lands directly in the original design spec's "~20-30 major currencies" target, and using the data source's own supported set (rather than hand-picking a subset) guarantees every seeded currency is actually fetchable.

`AED` (currently seeded, from the foundation migration) is **not** supported by Frankfurter and will be removed — nothing currently references it (no watchlist/alert rows exist), so this is a clean delete, not a soft-deactivation.

Migration: `supabase/migrations/0002_expand_currencies.sql` — deletes `AED`, inserts the 19 new currencies (`BRL, CZK, DKK, HKD, HUF, IDR, ILS, ISK, KRW, MXN, MYR, NOK, PHP, PLN, RON, SEK, THB, TRY, ZAR`) alongside the 11 already-seeded currencies Frankfurter does support.

## 5. Storage Model — USD Pivot

`rates_cache` stores only each currency's rate **against USD** (one row per currency per day, `base_code='USD'`), not every directed pair. Any other pair (e.g. EUR→INR) is computed on demand: `rate(A,B) = rate(USD,B) / rate(USD,A)`, using two rows from the *same* `as_of` date.

This is not an approximation — it's the same technique the data source itself uses. ECB natively publishes rates pivoted through EUR; Frankfurter's own USD-based views are computed from that by the identical division. Verified empirically during design on two independent dates (today and a date 3+ years back): computing USD→INR via the EUR pivot matched the directly-queried USD→INR to within display-rounding precision (~0.001%) both times. The identity holds because it's a no-arbitrage requirement of the rates being simultaneous, not a coincidence of any particular day's numbers — the one rule is that both legs of a division must come from the same `as_of` snapshot, never mixed across dates.

Storage cost: ~29 rows/day vs. ~870 rows/day for a full pairwise matrix — roughly 15x leaner, comfortably within Supabase free-tier limits even across the full historical backfill (~27 years back to 1999 is roughly 200,000 rows, vs. over 6M for the full matrix).

A pure helper function, `cross_rate(as_of, from_code, to_code)`, encapsulates the lookup + division and enforces the same-`as_of` rule structurally (it takes a single date and looks up both legs itself, rather than accepting two already-fetched rate values a caller could mismatch). No API route exposes it yet — this task only adds the function and its tests; the prediction engine and any future watchlist/dashboard code will import it directly when they need a cross-rate.

## 6. Components

- `backend/app/ingestion/frankfurter.py` — thin client: `fetch_latest(base, symbols) -> dict`, `fetch_range(base, symbols, start, end) -> dict`. Wraps `httpx` (already a dependency).
- `backend/app/ingestion/rates.py` — orchestration: reads active currencies from `public.currencies` (via Supabase REST, service-role key), calls the Frankfurter client, upserts rows into `rates_cache` via PostgREST with `on_conflict=base_code,quote_code,as_of` (batched for the backfill's ~200,000 rows — PostgREST/HTTP payload size limits mean this needs chunking, not one giant request).
- `backend/app/ingestion/cross_rate.py` — the `cross_rate(as_of, from_code, to_code)` helper described above.
- `backend/app/ingestion/cli.py` — entrypoint: `python -m app.ingestion.cli --mode daily` or `--mode backfill --years 5`, invoked by the GitHub Actions workflow.
- `.github/workflows/ingest-rates.yml` — scheduled daily (after ECB's ~16:00 CET publish time) plus `workflow_dispatch` (for manual runs, including backfill with a `mode` input).

## 7. Error Handling

- A failed daily fetch (network error, Frankfurter unreachable) fails the GitHub Actions run loudly — visible as a failed workflow run, not swallowed. Matches the project's "never fail silently" principle from the Phase 1 design spec.
- A currency missing from a given date's response is expected for old historical dates (per §3) and is skipped for that row only, not treated as a job failure.
- Backfill is idempotent and re-runnable: re-running it after a partial failure just re-upserts already-present rows (no-op via the unique constraint) and fills in whatever's missing.

## 8. Testing

- `frankfurter.py`: unit tests with mocked `httpx` responses (same pattern as the existing `test_health.py`) — correct parsing of `latest` and range responses, including the partial-coverage case.
- `rates.py`: unit tests for the upsert payload shape, `on_conflict` params, and batching logic, with mocked Supabase REST calls — no live network or database calls in the test suite.
- `cross_rate.py`: focused tests covering the arithmetic (matching the verified identity from §5) and same-`as_of` enforcement.

## 9. Ops — Manual Setup Required

`SUPABASE_URL` and `SUPABASE_SERVICE_KEY` need to be added as GitHub Actions repository secrets (Settings → Secrets and variables → Actions) before the workflow can run — a manual dashboard step, same category as the Render/Vercel environment variables from the deployment task.

## Definition of Done

- `supabase/migrations/0002_expand_currencies.sql` applied; `public.currencies` has the 30-currency Frankfurter-supported set, `AED` removed.
- Backfill populates `rates_cache` with USD-pivot daily rates for all supported currencies, back to Frankfurter's earliest available date (1999-01-04).
- The GitHub Actions workflow runs daily and successfully appends the current day's rates.
- `cross_rate()` is implemented and tested, ready for the prediction engine to consume.
- Backend test suite (including new ingestion tests) passes with no live network calls.
