# FRED Interest-Rate-Differential Regression Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the shipped prediction engine (2a) with a per-currency empirical regression of forecast error against FRED interest-rate differentials, fitted during the weekly backtest and applied to the daily forecast — with a clean, automatic fallback to the unadjusted 2a baseline for any currency lacking FRED coverage or a statistically significant fit.

**Architecture:** A new `backend/app/macro/` package handles all FRED I/O (fetching, storing, reading interest-rate observations) independently of the prediction package. `backend/app/prediction/backtest.py` and `backend/app/prediction/jobs.py` are extended — not rewritten — to optionally consume macro data: when a currency has no macro coverage, every extended code path degrades to exactly its pre-2b behavior.

**Tech Stack:** Python 3.12, httpx (FRED API + Supabase REST, matching every existing I/O module), scipy.stats.linregress (OLS regression fit — scipy is already a transitive `statsmodels` dependency, pinned directly by this plan), GitHub Actions (new weekly `macro.yml` cron).

**Spec:** [docs/superpowers/specs/2026-08-16-fred-macro-regression-design.md](../specs/2026-08-16-fred-macro-regression-design.md)

## Global Constraints

- No live network calls in the automated test suite — every FRED/Supabase call is mocked in tests. Live verification happens only in this plan's final manual task.
- A currency with no confirmed FRED series, or whose regression fit doesn't clear the quality gate (`min_samples=24`, `p_threshold=0.10`), must silently fall back to unadjusted 2a behavior — never an error.
- FRED unreachable, rate-limited, or any non-400 HTTP error during a scheduled job fails loudly (propagates, non-zero exit). An unrecognized `series_id` (HTTP 400) or a series with zero usable observations is an expected per-currency skip — logged, not raised.
- Never interpolate `${{ }}` directly into a workflow's `run:` shell body — route every dynamic value through an `env:` block first (the lesson from every prior plan's final review).
- Interest rates only in this task. Inflation and GDP ingestion are explicitly deferred — no task in this plan ingests them, and the roadmap doc's 2b entry must say so explicitly when marked shipped, not silently drop the mention.
- Every new `backend/app/macro/*.py` I/O module mirrors the established `_headers()`/`BATCH_SIZE`/`PAGE_SIZE` conventions from the sibling `app.ingestion.supabase_rest`, `app.prediction.supabase_rest`, and `app.recommendations.supabase_rest` modules.

## Prerequisite (blocks Task 3 and Task 12)

This plan needs a **new** FRED API key — free, self-service, no card required:

1. Sign up at https://fred.stlouisfed.org/docs/api/api_key.html (requires a free FRED account) and generate a 32-character API key.
2. Add it to `backend/.env` (already gitignored, matches how `SUPABASE_SERVICE_KEY` is handled locally): `FRED_API_KEY=<your key>`.
3. Also add it as a GitHub Actions repo secret named `FRED_API_KEY` (Settings → Secrets and variables → Actions → New repository secret) — needed before Task 12's live workflow run, but convenient to do now alongside step 2.

Task 3 (verifying real FRED series IDs) and Task 12 (live verification) both require a working key. Every other task only needs `backend/.env` to have *some* value for `FRED_API_KEY` (tests mock all real FRED calls) — but the real key from step 1 satisfies that too, so there's no reason to use a placeholder locally.

---

### Task 1: Schema, config, and dependencies

**Files:**
- Create: `supabase/migrations/0005_macro_rates.sql`
- Modify: `backend/app/config.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/.env.example`

**Interfaces:**
- Produces: `Settings.fred_api_key: str` (via `get_settings()`), consumed by Task 2's `fred_client.py`.
- Produces: `public.macro_rates` table and `backtest_stats.regression_slope`/`regression_intercept` columns, consumed by Tasks 5, 9, 10.

This task has no new application logic to unit-test — it's schema plus config plumbing that every later task depends on. Verify it by confirming the **existing** full test suite still passes after the change (a `Settings()` that now requires `fred_api_key` with no test env var set would break every existing test that imports `app.main`).

- [ ] **Step 1: Write the migration**

```sql
-- supabase/migrations/0005_macro_rates.sql

-- FRED interest-rate observations, one row per currency per date.
-- Internal computation state only, like backtest_stats -- no consumer
-- outside the prediction pipeline reads this directly.
create table public.macro_rates (
    currency_code text not null references public.currencies (code),
    as_of date not null,
    series_id text not null,
    rate numeric not null,
    primary key (currency_code, as_of)
);

alter table public.macro_rates enable row level security;
-- Deliberately no select policy: only the service role (which bypasses
-- RLS) reads or writes this table, matching backtest_stats' convention.

-- Nullable: NULL means "no regression fit for this currency/horizon --
-- use the unadjusted 2a baseline," the default/common case until a
-- currency both has FRED coverage and clears the fit's quality gate.
alter table public.backtest_stats
    add column regression_slope numeric,
    add column regression_intercept numeric;
```

- [ ] **Step 2: Add `fred_api_key` to `Settings`**

In `backend/app/config.py`, add the field alongside the existing ones:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_service_key: str
    frontend_origin: str = "http://localhost:5173"
    fred_api_key: str
```

- [ ] **Step 3: Set `FRED_API_KEY` in the test environment**

In `backend/tests/conftest.py`, add one line inside `pytest_configure`, alongside the existing three:

```python
def pytest_configure(config):
    os.environ["SUPABASE_URL"] = "https://example.supabase.co"
    os.environ["SUPABASE_SERVICE_KEY"] = "test-service-key"
    os.environ["FRONTEND_ORIGIN"] = "http://localhost:5173"
    os.environ["FRED_API_KEY"] = "test-fred-key"
```

- [ ] **Step 4: Run the full suite to confirm nothing broke**

Run: `cd backend && python -m pytest -q`
Expected: PASS, same count as before this task (no new tests added yet).

- [ ] **Step 5: Pin `scipy` explicitly**

In `backend/requirements.txt`, add a new line (it's currently only a transitive `statsmodels` dependency — Task 9 imports it directly, so pin it now):

```
scipy==1.17.1
```

Run: `cd backend && pip install -r requirements.txt` and confirm it completes without error (it should already be satisfied, since `statsmodels` already pulled it in).

- [ ] **Step 6: Document the new env var**

In `backend/.env.example`, add a line:

```
FRED_API_KEY=your-fred-api-key
```

- [ ] **Step 7: Apply the migration to the live Supabase project**

If `mcp__supabase__apply_migration` isn't already loaded: `ToolSearch(query="select:mcp__supabase__apply_migration")`.

`mcp__supabase__apply_migration(name="macro_rates", query="<the exact SQL from Step 1>")`

Verify: `mcp__supabase__execute_sql(query="select column_name from information_schema.columns where table_name = 'macro_rates' order by ordinal_position")` returns `currency_code, as_of, series_id, rate`, and `mcp__supabase__execute_sql(query="select column_name from information_schema.columns where table_name = 'backtest_stats' and column_name in ('regression_slope', 'regression_intercept')")` returns both new columns.

- [ ] **Step 8: Commit**

```bash
git add supabase/migrations/0005_macro_rates.sql backend/app/config.py backend/tests/conftest.py backend/requirements.txt backend/.env.example
git commit -m "feat(db): add macro_rates table and backtest_stats regression columns"
```

---

### Task 2: FRED API client

**Files:**
- Create: `backend/app/macro/__init__.py` (empty)
- Create: `backend/app/macro/fred_client.py`
- Test: `backend/tests/test_macro_fred_client.py`

**Interfaces:**
- Consumes: `app.config.get_settings().fred_api_key` (Task 1).
- Produces: `fetch_observations(series_id: str) -> list[tuple[str, float]] | None`, consumed by Task 6's `jobs.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_macro_fred_client.py
from unittest.mock import MagicMock, patch

from app.macro.fred_client import fetch_observations


def test_fetch_observations_returns_date_value_pairs():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "observations": [
            {"date": "2020-01-01", "value": "0.75"},
            {"date": "2020-02-01", "value": "0.80"},
        ]
    }
    with patch(
        "app.macro.fred_client.httpx.get", return_value=mock_response
    ) as mock_get:
        result = fetch_observations("IR3TIB01USM156N")

    assert result == [("2020-01-01", 0.75), ("2020-02-01", 0.80)]
    args, kwargs = mock_get.call_args
    assert args[0] == "https://api.stlouisfed.org/fred/series/observations"
    assert kwargs["params"]["series_id"] == "IR3TIB01USM156N"
    assert kwargs["params"]["api_key"] == "test-fred-key"
    assert kwargs["params"]["file_type"] == "json"


def test_fetch_observations_skips_missing_value_placeholder():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "observations": [
            {"date": "2020-01-01", "value": "0.75"},
            {"date": "2020-02-01", "value": "."},
        ]
    }
    with patch("app.macro.fred_client.httpx.get", return_value=mock_response):
        result = fetch_observations("IR3TIB01USM156N")

    assert result == [("2020-01-01", 0.75)]


def test_fetch_observations_returns_none_for_unrecognized_series():
    mock_response = MagicMock()
    mock_response.status_code = 400
    with patch("app.macro.fred_client.httpx.get", return_value=mock_response):
        result = fetch_observations("NOT_A_REAL_SERIES")

    assert result is None


def test_fetch_observations_returns_none_for_empty_observations():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"observations": []}
    with patch("app.macro.fred_client.httpx.get", return_value=mock_response):
        result = fetch_observations("IR3TIB01XXM156N")

    assert result is None


def test_fetch_observations_propagates_server_errors():
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=mock_response
    )
    with patch("app.macro.fred_client.httpx.get", return_value=mock_response):
        try:
            fetch_observations("IR3TIB01USM156N")
            assert False, "expected HTTPStatusError to propagate"
        except httpx.HTTPStatusError:
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_macro_fred_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.macro'`

- [ ] **Step 3: Create the empty package marker**

```bash
touch backend/app/macro/__init__.py
```

- [ ] **Step 4: Implement `fred_client.py`**

```python
# backend/app/macro/fred_client.py
import httpx

from app.config import get_settings

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch_observations(series_id: str) -> list[tuple[str, float]] | None:
    """Fetches a FRED series' full observation history (oldest to
    newest). Returns None when FRED doesn't recognize `series_id` (HTTP
    400) or the series has no usable observations -- both mean "no data
    for this currency," not an error, matching the same
    expected-gap-vs-real-error split used everywhere else in this app.
    Missing individual observations (FRED's "." placeholder for a
    not-yet-published or suppressed value) are skipped. Any other HTTP
    error (5xx, timeout, rate-limit) propagates -- those are unexpected
    and should fail the ingestion job loudly.
    """
    settings = get_settings()
    response = httpx.get(
        FRED_BASE_URL,
        params={
            "series_id": series_id,
            "api_key": settings.fred_api_key,
            "file_type": "json",
        },
        timeout=30.0,
    )
    if response.status_code == 400:
        return None
    response.raise_for_status()
    observations = response.json()["observations"]
    result = [
        (obs["date"], float(obs["value"]))
        for obs in observations
        if obs["value"] != "."
    ]
    return result if result else None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_macro_fred_client.py -v`
Expected: PASS, all 5 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/macro/__init__.py backend/app/macro/fred_client.py backend/tests/test_macro_fred_client.py
git commit -m "feat(backend): add FRED API client"
```

---

### Task 3: FRED series mapping (live research task)

**Files:**
- Create: `backend/app/macro/series_map.py`
- Test: `backend/tests/test_macro_series_map.py`

**Interfaces:**
- Produces: `FRED_SERIES: dict[str, str]` (currency_code -> FRED series_id), consumed by Task 6's `jobs.py`.

This task is **not** a normal TDD cycle — it's live research against the real FRED API, because guessing series IDs risks silently shipping wrong or nonexistent mappings. Do not invent series IDs; every entry in the final dict must be confirmed by an actual successful API response during this task.

**Candidate series pattern (to verify, not assume):** FRED hosts OECD short-term interbank-rate series named `IR3TIB01<country>M156N` (monthly) for many countries — confirmed to exist for at least Germany (`IR3TIB01DEM156N`), Japan (`IR3TIB01JPM156N`), Switzerland (`IR3TIB01CHM156N`), and the Euro Area (`IR3TIB01EZM156N`) during this plan's research. Some countries only publish an annual variant (`IR3TIB01<country>A156N`) or no OECD series at all. The primary country/area code to try per currency:

| currency_code | candidate country/area code | currency_code | candidate country/area code |
|---|---|---|---|
| USD | US | KRW | KR |
| EUR | EZ | MXN | MX |
| GBP | GB | MYR | MY |
| INR | IN | NOK | NO |
| JPY | JP | PHP | PH |
| AUD | AU | PLN | PL |
| CAD | CA | RON | RO |
| CHF | CH | SEK | SE |
| CNY | CN | THB | TH |
| SGD | SG | TRY | TR |
| NZD | NZ | ZAR | ZA |
| BRL | BR | HKD | HK |
| CZK | CZ | IDR | ID |
| DKK | DK | ILS | IL |
| HUF | HU | ISK | IS |

- [ ] **Step 1: Confirm `FRED_API_KEY` is a real, working key**

```bash
cd backend && python -c "
from app.config import get_settings
import httpx
key = get_settings().fred_api_key
r = httpx.get('https://api.stlouisfed.org/fred/series/observations', params={'series_id': 'IR3TIB01USM156N', 'api_key': key, 'file_type': 'json'})
print(r.status_code, len(r.json().get('observations', [])) if r.status_code == 200 else r.text[:200])
"
```

Expected: `200` and a nonzero observation count. If this fails with a 400 mentioning an invalid API key, **stop and report NEEDS_CONTEXT** — the Prerequisite section's `backend/.env` setup must be completed by a human before this task can proceed (do not fabricate or reuse a placeholder key; a wrong key produces silently-empty results for every currency, which would look identical to "no coverage").

- [ ] **Step 2: For each candidate above, verify the series exists**

For each `(currency_code, country_code)` pair in the table, try `IR3TIB01<country_code>M156N` first; if that returns 400 or zero observations, try `IR3TIB01<country_code>A156N`; if that also fails, the currency has no confirmed series and is omitted entirely. Use the same one-liner pattern as Step 1, substituting the series_id, for each candidate — do this for all 30 rows (including USD) before writing the dict, and keep a note of which succeeded at which variant.

- [ ] **Step 3: Write `series_map.py` with only confirmed entries**

```python
# backend/app/macro/series_map.py
# currency_code -> FRED series_id, for currencies with a confirmed OECD
# short-term interbank/policy-rate series. Verified against the live
# FRED API during implementation (see Task 3 of the FRED regression
# plan) -- a currency is present here only if a real API call returned
# a 200 with at least one observation for it. Currencies not present
# simply get no macro-adjustment; the rest of the pipeline treats that
# identically to "no coverage yet," never an error.
FRED_SERIES: dict[str, str] = {
    # Populated during Task 3 execution with only the confirmed
    # currency_code -> series_id pairs, e.g.:
    # "USD": "IR3TIB01USM156N",
    # "EUR": "IR3TIB01EZM156N",
    # ...
}
```

Replace the placeholder comment with the actual confirmed dict from Step 2 — every single key/value pair must correspond to a series_id that returned a real, non-empty 200 response during Step 2. Do not leave the dict empty or partially filled with guesses.

- [ ] **Step 4: Write a sanity test (no live network)**

```python
# backend/tests/test_macro_series_map.py
from app.macro.series_map import FRED_SERIES


def test_fred_series_is_nonempty():
    assert len(FRED_SERIES) > 0


def test_fred_series_keys_and_values_are_strings():
    for currency_code, series_id in FRED_SERIES.items():
        assert isinstance(currency_code, str) and len(currency_code) == 3
        assert isinstance(series_id, str) and len(series_id) > 0


def test_usd_has_a_mapped_series():
    # USD's own rate is required for every differential (foreign - USD);
    # if USD itself has no confirmed series, the whole regression layer
    # can never activate for any currency.
    assert "USD" in FRED_SERIES
```

Run: `cd backend && python -m pytest tests/test_macro_series_map.py -v`
Expected: PASS, all 3 tests. If `test_usd_has_a_mapped_series` fails, Step 2 must be redone for USD specifically before proceeding — this is a hard blocker for the entire task, not a normal per-currency gap.

- [ ] **Step 5: Commit**

```bash
git add backend/app/macro/series_map.py backend/tests/test_macro_series_map.py
git commit -m "feat(backend): add verified FRED currency-to-series mapping"
```

---

### Task 4: Date alignment

**Files:**
- Create: `backend/app/macro/align.py`
- Test: `backend/tests/test_macro_align.py`

**Interfaces:**
- Produces: `align_as_of(dates: list[str], observations: list[tuple[str, float]]) -> list[float | None]`, consumed by Task 11's `prediction/jobs.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_macro_align.py
from app.macro.align import align_as_of


def test_align_as_of_forward_fills_sparse_observations():
    dates = ["2020-01-01", "2020-01-15", "2020-02-01", "2020-02-15"]
    observations = [("2020-01-10", 0.5), ("2020-02-01", 0.6)]
    result = align_as_of(dates, observations)
    assert result == [None, 0.5, 0.6, 0.6]


def test_align_as_of_exact_date_match():
    dates = ["2020-01-01"]
    observations = [("2020-01-01", 1.25)]
    assert align_as_of(dates, observations) == [1.25]


def test_align_as_of_empty_observations_returns_all_none():
    dates = ["2020-01-01", "2020-01-02"]
    assert align_as_of(dates, []) == [None, None]


def test_align_as_of_empty_dates_returns_empty_list():
    assert align_as_of([], [("2020-01-01", 1.0)]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_macro_align.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.macro.align'`

- [ ] **Step 3: Implement `align.py`**

```python
# backend/app/macro/align.py
def align_as_of(
    dates: list[str], observations: list[tuple[str, float]]
) -> list[float | None]:
    """Forward-fills `observations` (sparse, e.g. monthly FRED data,
    sorted oldest to newest) onto every entry of `dates` (dense, e.g.
    daily trading dates, also sorted oldest to newest): each date gets
    the most recent observation known as of that date. A date before the
    first observation gets None -- no macro data was known yet at that
    point in history. Both inputs must already be sorted ascending by
    date (a two-pointer merge, not a search).
    """
    result: list[float | None] = []
    obs_index = 0
    current_value: float | None = None
    for date in dates:
        while obs_index < len(observations) and observations[obs_index][0] <= date:
            current_value = observations[obs_index][1]
            obs_index += 1
        result.append(current_value)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_macro_align.py -v`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/macro/align.py backend/tests/test_macro_align.py
git commit -m "feat(backend): add macro-data date alignment"
```

---

### Task 5: Macro Supabase I/O

**Files:**
- Create: `backend/app/macro/supabase_rest.py`
- Test: `backend/tests/test_macro_supabase_rest.py`

**Interfaces:**
- Produces: `upsert_macro_rates(rows: list[dict]) -> None`, `get_macro_rate_series(currency_code: str) -> list[tuple[str, float]]`, `get_latest_macro_rate(currency_code: str) -> float | None`, consumed by Task 6's `jobs.py` and Task 11's `prediction/jobs.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_macro_supabase_rest.py
from unittest.mock import MagicMock, patch

from app.macro.supabase_rest import (
    get_latest_macro_rate,
    get_macro_rate_series,
    upsert_macro_rates,
)


def test_upsert_macro_rates_posts_with_merge_duplicates():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {"currency_code": "EUR", "as_of": "2020-01-01", "series_id": "IR3TIB01EZM156N", "rate": 0.5}
    ]
    with patch(
        "app.macro.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        upsert_macro_rates(rows)

    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/macro_rates"
    assert kwargs["params"] == {"on_conflict": "currency_code,as_of"}
    assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates"
    assert kwargs["json"] == rows


def test_get_macro_rate_series_returns_date_rate_tuples():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"as_of": "2020-01-01", "rate": 0.5},
        {"as_of": "2020-02-01", "rate": 0.6},
    ]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.macro.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_macro_rate_series("EUR")

    assert result == [("2020-01-01", 0.5), ("2020-02-01", 0.6)]
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["currency_code"] == "eq.EUR"
    assert kwargs["params"]["order"] == "as_of.asc"


def test_get_macro_rate_series_paginates():
    page_size = 1000
    first_page = [
        {"as_of": f"2020-{(i % 12) + 1:02d}-01", "rate": float(i)} for i in range(page_size)
    ]
    second_page = [{"as_of": "2099-01-01", "rate": 9.9}]
    first_response = MagicMock()
    first_response.json.return_value = first_page
    first_response.raise_for_status.return_value = None
    second_response = MagicMock()
    second_response.json.return_value = second_page
    second_response.raise_for_status.return_value = None
    with patch(
        "app.macro.supabase_rest.httpx.get",
        side_effect=[first_response, second_response],
    ) as mock_get:
        result = get_macro_rate_series("EUR")

    assert len(result) == page_size + 1
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[1].kwargs["params"]["offset"] == page_size


def test_get_latest_macro_rate_returns_most_recent_value():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"rate": 0.75}]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.macro.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_latest_macro_rate("EUR")

    assert result == 0.75
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["order"] == "as_of.desc"
    assert kwargs["params"]["limit"] == 1


def test_get_latest_macro_rate_returns_none_when_no_data():
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None
    with patch("app.macro.supabase_rest.httpx.get", return_value=mock_response):
        result = get_latest_macro_rate("EUR")

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_macro_supabase_rest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.macro.supabase_rest'`

- [ ] **Step 3: Implement `supabase_rest.py`**

```python
# backend/app/macro/supabase_rest.py
import httpx

from app.config import get_settings

BATCH_SIZE = 500
PAGE_SIZE = 1000


def _headers(prefer: str | None = None) -> dict:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def upsert_macro_rates(rows: list[dict]) -> None:
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/macro_rates",
            params={"on_conflict": "currency_code,as_of"},
            headers=_headers(prefer="resolution=merge-duplicates"),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()


def get_macro_rate_series(currency_code: str) -> list[tuple[str, float]]:
    settings = get_settings()
    result: list[tuple[str, float]] = []
    offset = 0
    while True:
        response = httpx.get(
            f"{settings.supabase_url}/rest/v1/macro_rates",
            params={
                "select": "as_of,rate",
                "currency_code": f"eq.{currency_code}",
                "order": "as_of.asc",
                "limit": PAGE_SIZE,
                "offset": offset,
            },
            headers=_headers(),
            timeout=30.0,
        )
        response.raise_for_status()
        rows = response.json()
        result.extend((row["as_of"], float(row["rate"])) for row in rows)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return result


def get_latest_macro_rate(currency_code: str) -> float | None:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/macro_rates",
        params={
            "select": "rate",
            "currency_code": f"eq.{currency_code}",
            "order": "as_of.desc",
            "limit": 1,
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return float(rows[0]["rate"]) if rows else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_macro_supabase_rest.py -v`
Expected: PASS, all 5 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/macro/supabase_rest.py backend/tests/test_macro_supabase_rest.py
git commit -m "feat(backend): add macro rates Supabase I/O layer"
```

---

### Task 6: Macro ingestion orchestration

**Files:**
- Create: `backend/app/macro/jobs.py`
- Test: `backend/tests/test_macro_jobs.py`

**Interfaces:**
- Consumes: `fetch_observations` (Task 2), `FRED_SERIES` (Task 3), `upsert_macro_rates` (Task 5).
- Produces: `run_macro_ingestion() -> int`, consumed by Task 7's `cli.py`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_macro_jobs.py
from unittest.mock import patch

from app.macro.jobs import run_macro_ingestion


def test_run_macro_ingestion_upserts_all_mapped_currencies():
    fake_series = {"USD": "IR3TIB01USM156N", "EUR": "IR3TIB01EZM156N"}
    fake_observations = {
        "IR3TIB01USM156N": [("2020-01-01", 0.5)],
        "IR3TIB01EZM156N": [("2020-01-01", 0.1), ("2020-02-01", 0.2)],
    }
    with patch("app.macro.jobs.FRED_SERIES", fake_series), patch(
        "app.macro.jobs.fetch_observations",
        side_effect=lambda series_id: fake_observations[series_id],
    ), patch("app.macro.jobs.upsert_macro_rates") as mock_upsert:
        count = run_macro_ingestion()

    assert count == 3
    rows = mock_upsert.call_args[0][0]
    assert {"currency_code": "USD", "as_of": "2020-01-01", "series_id": "IR3TIB01USM156N", "rate": 0.5} in rows
    assert {"currency_code": "EUR", "as_of": "2020-02-01", "series_id": "IR3TIB01EZM156N", "rate": 0.2} in rows


def test_run_macro_ingestion_skips_currency_with_no_data():
    fake_series = {"USD": "IR3TIB01USM156N", "XYZ": "IR3TIB01XXM156N"}
    with patch("app.macro.jobs.FRED_SERIES", fake_series), patch(
        "app.macro.jobs.fetch_observations",
        side_effect=lambda series_id: None if series_id == "IR3TIB01XXM156N" else [("2020-01-01", 0.5)],
    ), patch("app.macro.jobs.upsert_macro_rates") as mock_upsert:
        count = run_macro_ingestion()

    assert count == 1
    rows = mock_upsert.call_args[0][0]
    assert all(r["currency_code"] == "USD" for r in rows)


def test_run_macro_ingestion_propagates_unexpected_errors():
    fake_series = {"USD": "IR3TIB01USM156N"}
    with patch("app.macro.jobs.FRED_SERIES", fake_series), patch(
        "app.macro.jobs.fetch_observations", side_effect=RuntimeError("boom")
    ), patch("app.macro.jobs.upsert_macro_rates") as mock_upsert:
        try:
            run_macro_ingestion()
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass
    mock_upsert.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_macro_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.macro.jobs'`

- [ ] **Step 3: Implement `jobs.py`**

```python
# backend/app/macro/jobs.py
import logging

from app.macro.fred_client import fetch_observations
from app.macro.series_map import FRED_SERIES
from app.macro.supabase_rest import upsert_macro_rates

logger = logging.getLogger(__name__)


def run_macro_ingestion() -> int:
    """Refreshes every mapped currency's full FRED observation history.
    Unlike rates_cache, there's no backfill/daily split: FRED's monthly
    series are small (a few hundred rows per currency), so a full
    re-fetch every run is cheap and avoids incremental-update bugs. A
    currency whose series returns no data (fetch_observations -> None)
    is an expected skip, not an error; any other exception (network,
    5xx, rate-limit) propagates and fails the job.
    """
    rows = []
    for currency_code, series_id in FRED_SERIES.items():
        observations = fetch_observations(series_id)
        if observations is None:
            logger.warning(
                "Skipping %s: FRED series %s returned no data", currency_code, series_id
            )
            continue
        rows.extend(
            {
                "currency_code": currency_code,
                "as_of": date,
                "series_id": series_id,
                "rate": rate,
            }
            for date, rate in observations
        )
    if not rows and FRED_SERIES:
        logger.warning(
            "run_macro_ingestion produced zero rows despite %d mapped currencies -- "
            "check FRED_API_KEY and series_map.py",
            len(FRED_SERIES),
        )
    upsert_macro_rates(rows)
    return len(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_macro_jobs.py -v`
Expected: PASS, all 3 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/macro/jobs.py backend/tests/test_macro_jobs.py
git commit -m "feat(backend): add macro ingestion orchestration"
```

---

### Task 7: Macro CLI

**Files:**
- Create: `backend/app/macro/cli.py`
- Test: `backend/tests/test_macro_cli.py`

**Interfaces:**
- Consumes: `run_macro_ingestion` (Task 6).
- Produces: `main() -> None`, invoked by Task 8's `macro.yml` as `python -m app.macro.cli`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_macro_cli.py
from unittest.mock import patch

from app.macro.cli import main


def test_main_calls_run_macro_ingestion():
    with patch("app.macro.cli.run_macro_ingestion", return_value=42) as mock_run:
        main()

    mock_run.assert_called_once()


def test_main_propagates_errors():
    with patch("app.macro.cli.run_macro_ingestion", side_effect=RuntimeError("boom")):
        try:
            main()
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_macro_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.macro.cli'`

- [ ] **Step 3: Implement `cli.py`**

```python
# backend/app/macro/cli.py
from app.macro.jobs import run_macro_ingestion


def main() -> None:
    count = run_macro_ingestion()
    print(f"Upserted {count} macro rate rows")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_macro_cli.py -v`
Expected: PASS, both tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/macro/cli.py backend/tests/test_macro_cli.py
git commit -m "feat(backend): add macro ingestion CLI entrypoint"
```

---

### Task 8: Macro ingestion GitHub Actions workflow

**Files:**
- Create: `.github/workflows/macro.yml`

**Interfaces:**
- Consumes: `python -m app.macro.cli` (Task 7), repo secrets `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (existing), `FRED_API_KEY` (new — see Prerequisite).

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/macro.yml
name: Ingest macro rates

on:
  schedule:
    # Weekly, Sundays at 17:00 UTC -- two hours before predict.yml's
    # Sunday backtest cron (19:00 UTC), so the backtest always fits
    # against fresh macro data. FRED series update roughly monthly, so
    # this cadence keeps macro_rates current within days of any new
    # print without a wasteful daily fetch.
    - cron: '0 17 * * 0'
  workflow_dispatch:

jobs:
  ingest-macro:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - name: Run macro ingestion job
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
          FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
        run: python -m app.macro.cli
```

Note this workflow has no `${{ }}` anywhere inside a multi-line `run:` shell body (the single-line `run:` here is a plain command, not shell-interpolated) — consistent with every prior workflow's fix for this exact class of injection risk.

- [ ] **Step 2: Validate the YAML**

Run: `cd .github/workflows && python -c "import yaml; yaml.safe_load(open('macro.yml'))" && echo "valid"`
Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/macro.yml
git commit -m "ci: add scheduled GitHub Actions workflow for macro ingestion"
```

---

### Task 9: Regression fitting in the backtest

**Files:**
- Modify: `backend/app/prediction/backtest.py`
- Test: `backend/tests/test_backtest.py`

**Interfaces:**
- Produces: `run_backtest(rates, horizons, differentials=None) -> dict[int, dict]` (extended signature — omitted `differentials` must be byte-for-byte identical to pre-2b behavior), `fit_regression(errors, differentials, min_samples=24, p_threshold=0.10) -> dict | None`, `summarize(samples) -> dict` (extended return: adds `regression_slope`, `regression_intercept` keys). Consumed by Task 11's `prediction/jobs.py`.

**Before changing anything:** run the existing suite for this file and confirm it's green — `cd backend && python -m pytest tests/test_backtest.py -v` should show 3 passing tests (`test_run_backtest_produces_fewer_samples_for_longer_horizons`, `test_run_backtest_fits_only_on_data_up_to_each_origin`, `test_summarize_computes_percentiles_and_sample_count`). These three tests must **still pass, completely unmodified**, after this task — that's the proof the `differentials=None` path is unchanged.

- [ ] **Step 1: Write the new failing tests (add to the existing file, don't remove the 3 above)**

```python
# Add to backend/tests/test_backtest.py, alongside the existing tests
# and imports. Add `fit_regression` to the existing import line:
#   from app.prediction.backtest import fit_regression, run_backtest, summarize


def test_run_backtest_collects_differentials_parallel_to_errors():
    rates = [100.0 + i for i in range(150)]
    # MIN_HISTORY=60, ORIGIN_SPACING=30 -> origins at 60, 90, 120
    differentials = [0.01 * i for i in range(150)]
    results = run_backtest(rates, horizons=[7], differentials=differentials)
    assert results[7]["differentials"] == [
        differentials[60], differentials[90], differentials[120]
    ]
    assert len(results[7]["differentials"]) == len(results[7]["errors"])


def test_run_backtest_differentials_none_entries_pass_through():
    rates = [100.0 + i for i in range(150)]
    differentials = [None] * 70 + [0.5] * 80  # unknown until day 70
    results = run_backtest(rates, horizons=[7], differentials=differentials)
    # origin 60 falls in the None region, origins 90/120 don't
    assert results[7]["differentials"] == [None, 0.5, 0.5]


def test_fit_regression_recovers_known_slope_with_enough_significant_samples():
    # Deterministic synthetic data with a real linear relationship plus
    # small noise -- verified by hand: scipy.stats.linregress on this
    # exact data recovers slope=0.00408 (true 0.004) with p-value~2e-23,
    # comfortably clearing both the min_samples=24 and p_threshold=0.10
    # gates.
    import random
    random.seed(42)
    differentials = [i * 0.2 - 2.0 for i in range(30)]
    errors = [0.004 * d + -0.01 + random.uniform(-0.002, 0.002) for d in differentials]
    result = fit_regression(errors, differentials)
    assert result is not None
    assert abs(result["slope"] - 0.004) < 0.001
    assert abs(result["intercept"] - (-0.01)) < 0.001


def test_fit_regression_returns_none_below_min_samples():
    # Only 5 samples -- rejected by the min_samples=24 gate regardless of
    # fit quality (this data is a perfect fit, verified by hand: p-value
    # ~1.2e-30, which would otherwise easily clear p_threshold).
    differentials = [0.1, 0.2, 0.3, 0.4, 0.5]
    errors = [0.001, 0.002, 0.003, 0.004, 0.005]
    assert fit_regression(errors, differentials) is None


def test_fit_regression_returns_none_when_relationship_is_not_significant():
    # 30 samples (clears min_samples) but no real relationship -- verified
    # by hand: p-value~0.76, well above p_threshold=0.10.
    differentials = list(range(30))
    errors = [0.01 if i % 2 == 0 else -0.01 for i in range(30)]
    assert fit_regression(errors, differentials) is None


def test_summarize_stores_none_regression_when_no_differentials_key():
    samples = {
        "errors": [-2.0, -1.0, 0.0, 1.0, 2.0],
        "trailing_vols": [0.01, 0.02, 0.03, 0.04, 0.05],
    }
    result = summarize(samples)
    assert result["regression_slope"] is None
    assert result["regression_intercept"] is None


def test_summarize_fits_and_applies_regression_to_bounds():
    import random
    random.seed(7)
    differentials = [i * 0.2 - 2.0 for i in range(30)]
    errors = [0.004 * d - 0.01 + random.uniform(-0.001, 0.001) for d in differentials]
    samples = {
        "errors": errors,
        "trailing_vols": [0.01] * 30,
        "differentials": differentials,
    }
    result = summarize(samples)
    assert result["regression_slope"] is not None
    assert abs(result["regression_slope"] - 0.004) < 0.001
    # Post-adjustment residuals must be tighter than the raw error spread,
    # since the regression explains away the systematic component.
    raw_spread = max(errors) - min(errors)
    fitted_spread = result["error_upper_pct"] - result["error_lower_pct"]
    assert fitted_spread < raw_spread


def test_summarize_falls_back_to_raw_error_for_unpaired_origins():
    # A regression IS fit (24 paired samples, the minimum to clear
    # min_samples), plus 3 additional origins with no known differential
    # and a wild raw error (0.5) -- those 3 must contribute their RAW
    # error as-is (not silently dropped, not incorrectly "adjusted" via
    # the fitted line), since that's what production would actually do
    # for a day with no current differential. Verified by hand: with 3
    # such outliers among 27 total samples, the 90th-percentile rank
    # (26 * 0.9 = 23.4) falls just past the paired block into the
    # outlier block, giving error_upper_pct~0.20 -- if the unpaired
    # entries were wrongly dropped (24 samples total) or wrongly
    # regression-adjusted (extrapolating the fitted line with no real
    # differential), this would come out far smaller.
    import random
    random.seed(3)
    paired_differentials = [i * 0.2 - 2.0 for i in range(24)]
    paired_errors = [
        0.004 * d - 0.01 + random.uniform(-0.001, 0.001) for d in paired_differentials
    ]
    differentials = paired_differentials + [None, None, None]
    errors = paired_errors + [0.5, 0.5, 0.5]
    samples = {
        "errors": errors,
        "trailing_vols": [0.01] * 27,
        "differentials": differentials,
    }
    result = summarize(samples)
    assert result["regression_slope"] is not None
    assert result["error_upper_pct"] > 0.1
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `cd backend && python -m pytest tests/test_backtest.py -v`
Expected: the 3 pre-existing tests still PASS; the new ones FAIL (`fit_regression` not defined, `differentials` param not accepted, `KeyError: 'differentials'`).

- [ ] **Step 3: Implement the extension**

```python
# backend/app/prediction/backtest.py
from scipy.stats import linregress

from app.prediction.horizons import trading_day_steps
from app.prediction.model import forecast
from app.prediction.stats import percentile, realized_volatility

ORIGIN_SPACING = 30  # trading days between backtest origins
MIN_HISTORY = 60  # minimum trading days of lead-in before the first origin


def run_backtest(
    rates: list[float],
    horizons: list[int],
    differentials: list[float | None] | None = None,
) -> dict[int, dict]:
    """Rolling-origin backtest for one currency's USD-pivot rate series
    (`rates`, ordered oldest to newest). For each horizon, returns the raw
    forecast-error and trailing-volatility samples collected across every
    usable origin -- summarize() turns these into the stats actually
    stored in backtest_stats.

    Origins are spaced ORIGIN_SPACING trading days apart, starting after
    MIN_HISTORY days of lead-in so every fit has a reasonable amount of
    data. An origin only contributes a sample for a given horizon if
    enough future data exists to know the real outcome -- this is why
    longer horizons end up with fewer usable samples than shorter ones
    (see design spec Sec 5).

    `differentials`, when given, is parallel to `rates` (same length,
    oldest to newest) -- the interest-rate differential known as of each
    date, or None where macro coverage doesn't exist yet for that date.
    When provided, each horizon's results additionally collect a
    `"differentials"` list in lock-step with `"errors"` (same length,
    same order), which summarize() uses to fit a regression. Omitting
    `differentials` (the default) leaves every horizon's results
    identical in shape to the pre-2b implementation -- this is a purely
    additive extension, not a behavior change, for any caller that
    doesn't pass it.
    """
    n = len(rates)
    results: dict[int, dict] = {h: {"errors": [], "trailing_vols": []} for h in horizons}
    if differentials is not None:
        for h in horizons:
            results[h]["differentials"] = []

    for origin in range(MIN_HISTORY, n, ORIGIN_SPACING):
        history = rates[: origin + 1]
        trailing_vol = realized_volatility(rates, origin + 1)
        for horizon_days in horizons:
            steps = trading_day_steps(horizon_days)
            target_index = origin + steps
            if target_index >= n:
                continue
            predicted = forecast(history, steps)
            actual = rates[target_index]
            results[horizon_days]["errors"].append((actual - predicted) / predicted)
            results[horizon_days]["trailing_vols"].append(trailing_vol)
            if differentials is not None:
                results[horizon_days]["differentials"].append(differentials[origin])

    return results


def fit_regression(
    errors: list[float],
    differentials: list[float],
    min_samples: int = 24,
    p_threshold: float = 0.10,
) -> dict | None:
    """Fits `relative_error ~ a + b * differential` via ordinary least
    squares. Returns None -- meaning "not enough evidence this
    currency's rate differential predicts anything, don't adjust it" --
    when there are fewer than `min_samples` paired observations, or when
    the fitted slope's p-value doesn't clear `p_threshold`. `errors` and
    `differentials` must already be paired 1:1 (equal length, no None
    entries) -- callers filter out unpaired samples before calling this.
    """
    if len(errors) < min_samples:
        return None
    result = linregress(differentials, errors)
    if result.pvalue >= p_threshold:
        return None
    return {"slope": result.slope, "intercept": result.intercept}


def summarize(samples: dict) -> dict:
    """Turns one horizon's raw backtest samples into the stats stored in
    backtest_stats: empirical 10th/90th percentile forecast error (added
    to a fresh point forecast to build lower_bound/upper_bound), the 90th
    percentile of historically observed trailing volatility (the
    threshold today's live volatility is compared against for the
    confidence flag), and -- new in 2b -- a fitted interest-rate
    differential regression, when `samples` includes a `"differentials"`
    list and enough of its entries are non-None to clear fit_regression's
    quality gate.

    When a regression IS fit, error_lower_pct/error_upper_pct are
    recomputed from the POST-adjustment residuals, not the raw baseline
    errors -- otherwise the confidence band would misrepresent the
    adjusted model's real historical accuracy. An origin with no known
    differential can't be adjusted (there's nothing to apply the
    regression to), so its RAW baseline error is used as-is for that
    entry -- this matches what the daily forecast job actually does when
    today's current differential is unavailable (see
    app.prediction.jobs.run_forecast): no adjustment, baseline as-is.
    """
    errors = samples["errors"]
    diffs = samples.get("differentials")

    regression = None
    if diffs:
        paired = [(e, d) for e, d in zip(errors, diffs) if d is not None]
        if paired:
            regression = fit_regression(
                [e for e, _ in paired], [d for _, d in paired]
            )

    if regression:
        residuals = [
            e - (regression["slope"] * d + regression["intercept"]) if d is not None else e
            for e, d in zip(errors, diffs)
        ]
    else:
        residuals = errors

    return {
        "error_lower_pct": percentile(sorted(residuals), 10),
        "error_upper_pct": percentile(sorted(residuals), 90),
        "volatility_p90": percentile(sorted(samples["trailing_vols"]), 90),
        "sample_count": len(errors),
        "regression_slope": regression["slope"] if regression else None,
        "regression_intercept": regression["intercept"] if regression else None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_backtest.py -v`
Expected: PASS, all tests (the original 3 plus the 8 new ones).

- [ ] **Step 5: Commit**

```bash
git add backend/app/prediction/backtest.py backend/tests/test_backtest.py
git commit -m "feat(backend): fit interest-rate-differential regression in the backtest"
```

---

### Task 10: Prediction Supabase I/O extension

**Files:**
- Modify: `backend/app/prediction/supabase_rest.py`
- Test: `backend/tests/test_prediction_supabase_rest.py`

**Interfaces:**
- Produces: `get_backtest_stats(quote_code, horizon_days) -> dict | None` (extended return: adds `regression_slope`, `regression_intercept` keys, both possibly `None`). `upsert_backtest_stats` unchanged in code (rows now simply carry 2 more keys). Consumed by Task 11's `prediction/jobs.py`.

- [ ] **Step 1: Update the existing tests**

Modify `backend/tests/test_prediction_supabase_rest.py`'s two `get_backtest_stats` tests and the `upsert_backtest_stats` test:

```python
def test_get_backtest_stats_returns_stats_when_found():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.015,
            "regression_slope": 0.004,
            "regression_intercept": -0.01,
        }
    ]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.prediction.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_backtest_stats("EUR", 30)

    assert result == {
        "error_lower_pct": -0.02,
        "error_upper_pct": 0.03,
        "volatility_p90": 0.015,
        "regression_slope": 0.004,
        "regression_intercept": -0.01,
    }
    args, kwargs = mock_get.call_args
    assert kwargs["params"] == {
        "select": "error_lower_pct,error_upper_pct,volatility_p90,regression_slope,regression_intercept",
        "quote_code": "eq.EUR",
        "horizon_days": "eq.30",
    }


def test_get_backtest_stats_returns_none_regression_fields_when_null():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.015,
            "regression_slope": None,
            "regression_intercept": None,
        }
    ]
    mock_response.raise_for_status.return_value = None
    with patch("app.prediction.supabase_rest.httpx.get", return_value=mock_response):
        result = get_backtest_stats("EUR", 30)

    assert result["regression_slope"] is None
    assert result["regression_intercept"] is None


def test_get_backtest_stats_returns_none_when_not_found():
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None
    with patch("app.prediction.supabase_rest.httpx.get", return_value=mock_response):
        result = get_backtest_stats("EUR", 30)

    assert result is None


def test_upsert_backtest_stats_posts_with_merge_duplicates():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {
            "quote_code": "EUR",
            "horizon_days": 30,
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.015,
            "sample_count": 240,
            "regression_slope": 0.004,
            "regression_intercept": -0.01,
        }
    ]
    with patch(
        "app.prediction.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        upsert_backtest_stats(rows)

    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/backtest_stats"
    assert kwargs["params"] == {"on_conflict": "quote_code,horizon_days"}
    assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates"
    assert kwargs["json"] == rows
```

(Leave `test_get_rate_series_*` and `test_insert_predictions_posts_batch` untouched — this task doesn't affect them.)

- [ ] **Step 2: Run tests to verify the modified ones fail**

Run: `cd backend && python -m pytest tests/test_prediction_supabase_rest.py -v`
Expected: `test_get_backtest_stats_returns_stats_when_found` and the new `test_get_backtest_stats_returns_none_regression_fields_when_null` FAIL (KeyError / dict mismatch — the select list and return dict don't have the new fields yet). `test_upsert_backtest_stats_posts_with_merge_duplicates` still PASSES (the function body doesn't change), which is expected — the assertion still holds because `upsert_backtest_stats` just forwards whatever `rows` it's given.

- [ ] **Step 3: Extend `get_backtest_stats`**

In `backend/app/prediction/supabase_rest.py`, replace the function body (leave `upsert_backtest_stats` untouched):

```python
def get_backtest_stats(quote_code: str, horizon_days: int) -> dict | None:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/backtest_stats",
        params={
            "select": "error_lower_pct,error_upper_pct,volatility_p90,regression_slope,regression_intercept",
            "quote_code": f"eq.{quote_code}",
            "horizon_days": f"eq.{horizon_days}",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    row = results[0]
    return {
        "error_lower_pct": float(row["error_lower_pct"]),
        "error_upper_pct": float(row["error_upper_pct"]),
        "volatility_p90": float(row["volatility_p90"]),
        "regression_slope": float(row["regression_slope"]) if row["regression_slope"] is not None else None,
        "regression_intercept": float(row["regression_intercept"]) if row["regression_intercept"] is not None else None,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_prediction_supabase_rest.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/prediction/supabase_rest.py backend/tests/test_prediction_supabase_rest.py
git commit -m "feat(backend): extend backtest_stats I/O for regression columns"
```

---

### Task 11: Apply the regression in the prediction jobs

**Files:**
- Modify: `backend/app/prediction/jobs.py`
- Test: `backend/tests/test_jobs.py`

**Interfaces:**
- Consumes: `run_backtest`/`summarize` (Task 9, extended), `get_backtest_stats` (Task 10, extended), `align_as_of` (Task 4), `get_macro_rate_series`/`get_latest_macro_rate` (Task 5).
- Produces: `run_forecast() -> int`, `run_backtest_job() -> int` (same signatures as before — this task changes their bodies, not their interfaces, so nothing outside `app.prediction` needs to change).

- [ ] **Step 1: Update the existing tests**

Modify `backend/tests/test_jobs.py`'s import line and existing tests, then add new ones. Full replacement:

```python
# backend/tests/test_jobs.py
from unittest.mock import patch

from app.prediction.jobs import run_backtest_job, run_forecast


def test_run_forecast_builds_prediction_rows_from_backtest_stats():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": None,
            "regression_intercept": None,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        count = run_forecast()

    assert count == 4  # one row per horizon (7/30/90/365) for the one non-USD currency
    rows = mock_insert.call_args[0][0]
    assert all(r["base_code"] == "USD" and r["quote_code"] == "EUR" for r in rows)
    assert all(r["confidence"] == "normal" for r in rows)  # 0.01 vol < 0.02 p90
    first = rows[0]
    assert first["predicted_rate"] == 0.91
    assert first["lower_bound"] == 0.91 * (1 + (-0.02))
    assert first["upper_bound"] == 0.91 * (1 + 0.03)


def test_run_forecast_flags_low_confidence_when_volatility_exceeds_p90():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.05
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": None,
            "regression_intercept": None,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    assert all(r["confidence"] == "low" for r in rows)


def test_run_forecast_skips_horizon_with_no_backtest_stats_yet():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        count = run_forecast()

    assert count == 0
    mock_insert.assert_called_once_with([])


def test_run_forecast_applies_regression_when_stored_and_current_differential_known():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": 0.004,
            "regression_intercept": -0.01,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate",
        side_effect=lambda code: 0.06 if code == "EUR" else 0.01,  # differential = 0.05
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    expected_predicted = 0.91 * (1 + (0.004 * 0.05 + -0.01))
    assert rows[0]["predicted_rate"] == expected_predicted
    assert rows[0]["lower_bound"] == expected_predicted * (1 + (-0.02))
    assert rows[0]["upper_bound"] == expected_predicted * (1 + 0.03)


def test_run_forecast_skips_adjustment_when_current_differential_unknown():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.91
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": 0.004,
            "regression_intercept": -0.01,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    assert rows[0]["predicted_rate"] == 0.91  # unadjusted -- no current differential


def test_run_backtest_job_summarizes_and_upserts_per_currency_and_horizon():
    fake_results = {
        7: {"errors": [-0.01, 0.0, 0.01], "trailing_vols": [0.01, 0.02, 0.03]},
        30: {"errors": [], "trailing_vols": []},
    }
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.get_macro_rate_series", return_value=[]
    ), patch(
        "app.prediction.jobs.run_backtest", return_value=fake_results
    ), patch("app.prediction.jobs.upsert_backtest_stats") as mock_upsert:
        count = run_backtest_job()

    assert count == 1  # horizon 30 skipped (no samples), only horizon 7 written
    rows = mock_upsert.call_args[0][0]
    assert rows[0]["quote_code"] == "EUR"
    assert rows[0]["horizon_days"] == 7
    assert rows[0]["sample_count"] == 3
    assert rows[0]["regression_slope"] is None
    assert rows[0]["regression_intercept"] is None


def test_run_backtest_job_aligns_and_passes_differentials():
    captured = {}

    def fake_run_backtest(rates, horizons, differentials=None):
        captured["differentials"] = differentials
        return {h: {"errors": [], "trailing_vols": []} for h in horizons}

    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01", "2020-01-02"], [0.9, 0.91]),
    ), patch(
        "app.prediction.jobs.get_macro_rate_series",
        side_effect=lambda code: [("2020-01-01", 0.05)] if code == "EUR" else [("2020-01-01", 0.01)],
    ), patch(
        "app.prediction.jobs.run_backtest", side_effect=fake_run_backtest
    ), patch("app.prediction.jobs.upsert_backtest_stats"):
        run_backtest_job()

    assert captured["differentials"] == [0.04, 0.04]  # 0.05 - 0.01, forward-filled
```

- [ ] **Step 2: Run tests to verify the new/modified ones fail**

Run: `cd backend && python -m pytest tests/test_jobs.py -v`
Expected: several FAIL (`get_latest_macro_rate`/`get_macro_rate_series` not imported into `app.prediction.jobs` yet, `run_forecast` doesn't apply any adjustment yet, `run_backtest_job` doesn't compute differentials yet).

- [ ] **Step 3: Implement the extension**

Replace the full contents of `backend/app/prediction/jobs.py`:

```python
# backend/app/prediction/jobs.py
import logging

from app.ingestion.supabase_rest import get_active_currencies
from app.macro.align import align_as_of
from app.macro.supabase_rest import get_latest_macro_rate, get_macro_rate_series
from app.prediction.backtest import run_backtest, summarize
from app.prediction.horizons import trading_day_steps
from app.prediction.model import forecast
from app.prediction.stats import realized_volatility
from app.prediction.supabase_rest import (
    get_backtest_stats,
    get_rate_series,
    insert_predictions,
    upsert_backtest_stats,
)

logger = logging.getLogger(__name__)

PIVOT = "USD"
HORIZONS = [7, 30, 90, 365]


def _predictable_currencies() -> list[str]:
    return [code for code in get_active_currencies() if code != PIVOT]


def run_forecast() -> int:
    """Daily job: for every USD-quoted currency, fit today's model and
    forecast each horizon, building a confidence band from that pair's
    most recent backtest_stats and flagging low-confidence when current
    volatility exceeds its own historical 90th percentile. A (currency,
    horizon) with no backtest_stats yet (e.g. before the first weekly
    backtest has run) is skipped for that row only, not treated as an
    error.

    When backtest_stats has a fitted regression for a (currency, horizon)
    AND today's current interest-rate differential is available, the
    baseline point forecast is adjusted by that regression before the
    confidence band is applied -- otherwise the baseline is used exactly
    as in 2a.
    """
    currencies = _predictable_currencies()
    rows = []
    for quote_code in currencies:
        _dates, rates = get_rate_series(quote_code)
        if len(rates) < 2:
            logger.warning(
                "Skipping %s: insufficient rate history (%d rows)",
                quote_code,
                len(rates),
            )
            continue
        current_vol = realized_volatility(rates, len(rates))

        foreign_rate = get_latest_macro_rate(quote_code)
        usd_rate = get_latest_macro_rate(PIVOT)
        current_differential = (
            foreign_rate - usd_rate
            if foreign_rate is not None and usd_rate is not None
            else None
        )

        for horizon_days in HORIZONS:
            stats = get_backtest_stats(quote_code, horizon_days)
            if stats is None:
                logger.info(
                    "Skipping %s horizon=%d: no backtest_stats yet",
                    quote_code,
                    horizon_days,
                )
                continue
            steps = trading_day_steps(horizon_days)
            predicted_rate = forecast(rates, steps)
            if stats["regression_slope"] is not None and current_differential is not None:
                predicted_rate *= 1 + (
                    stats["regression_slope"] * current_differential
                    + stats["regression_intercept"]
                )
            confidence = "low" if current_vol > stats["volatility_p90"] else "normal"
            rows.append(
                {
                    "base_code": PIVOT,
                    "quote_code": quote_code,
                    "horizon_days": horizon_days,
                    "predicted_rate": predicted_rate,
                    "lower_bound": predicted_rate * (1 + stats["error_lower_pct"]),
                    "upper_bound": predicted_rate * (1 + stats["error_upper_pct"]),
                    "confidence": confidence,
                }
            )
    if not rows and currencies:
        logger.warning(
            "run_forecast produced zero prediction rows despite %d predictable "
            "currencies -- check backtest_stats is populated",
            len(currencies),
        )
    insert_predictions(rows)
    return len(rows)


def run_backtest_job() -> int:
    """Weekly job: re-runs the rolling-origin backtest for every USD-quoted
    currency and refreshes backtest_stats. A (currency, horizon) with no
    usable backtest samples is skipped for that row only.

    Also fits an interest-rate-differential regression per (currency,
    horizon) when macro_rates has coverage: the currency's and USD's
    interest-rate histories are each forward-filled onto the rate
    series' own dates (app.macro.align.align_as_of), then subtracted to
    build the differential series run_backtest uses. A currency with no
    macro coverage at all gets an all-None differential array, which
    flows through to summarize() as "no regression fit" -- identical to
    2a's behavior for that currency.
    """
    rows = []
    for quote_code in _predictable_currencies():
        dates, rates = get_rate_series(quote_code)

        usd_observations = get_macro_rate_series(PIVOT)
        foreign_observations = get_macro_rate_series(quote_code)
        usd_aligned = align_as_of(dates, usd_observations)
        foreign_aligned = align_as_of(dates, foreign_observations)
        differentials = [
            (f - u) if f is not None and u is not None else None
            for f, u in zip(foreign_aligned, usd_aligned)
        ]

        results = run_backtest(rates, HORIZONS, differentials=differentials)
        for horizon_days, samples in results.items():
            if not samples["errors"]:
                logger.info(
                    "Skipping %s horizon=%d: no backtest samples",
                    quote_code,
                    horizon_days,
                )
                continue
            summary = summarize(samples)
            rows.append(
                {
                    "quote_code": quote_code,
                    "horizon_days": horizon_days,
                    "error_lower_pct": summary["error_lower_pct"],
                    "error_upper_pct": summary["error_upper_pct"],
                    "volatility_p90": summary["volatility_p90"],
                    "sample_count": summary["sample_count"],
                    "regression_slope": summary["regression_slope"],
                    "regression_intercept": summary["regression_intercept"],
                }
            )
    upsert_backtest_stats(rows)
    return len(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_jobs.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && python -m pytest -q`
Expected: PASS, every test in the suite (this is the first point where all of Tasks 1-11's changes are exercised together).

- [ ] **Step 6: Commit**

```bash
git add backend/app/prediction/jobs.py backend/tests/test_jobs.py
git commit -m "feat(backend): apply interest-rate-differential regression to the daily forecast"
```

---

### Task 12: Live verification

No new GitHub Actions secrets beyond `FRED_API_KEY` (already added per the Prerequisite section) are needed — `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are already configured.

- [ ] **Step 1: Trigger the macro ingestion workflow**

On GitHub: repo → Actions → "Ingest macro rates" → Run workflow → Run workflow. Wait for a green checkmark.

- [ ] **Step 2: Verify `macro_rates` populated**

If `mcp__supabase__execute_sql` isn't already loaded: `ToolSearch(query="select:mcp__supabase__execute_sql")`.

`mcp__supabase__execute_sql(query="select count(*) as rows, count(distinct currency_code) as currencies from public.macro_rates")`
Expected: a nonzero row count, and `currencies` matching however many entries `FRED_SERIES` ended up with after Task 3's live verification (could be fewer than 29 — that's expected, not a failure).

`mcp__supabase__execute_sql(query="select currency_code, as_of, series_id, rate from public.macro_rates where currency_code = 'USD' order by as_of desc limit 3")`
Expected: 3 rows with recent-looking dates and plausible interest-rate values (a small positive number, typically under 20).

- [ ] **Step 3: Trigger the weekly backtest**

On GitHub: repo → Actions → "Generate predictions" → Run workflow → mode = `backtest` → Run workflow. Wait for a green checkmark.

- [ ] **Step 4: Verify the regression columns**

`mcp__supabase__execute_sql(query="select quote_code, horizon_days, regression_slope, regression_intercept, sample_count from public.backtest_stats where regression_slope is not null order by quote_code, horizon_days limit 10")`

If this returns zero rows, that means no currency's live data cleared the significance gate this run -- **not necessarily a bug** (see the spec's Definition of Done: this is a property of the real data, not something the code can guarantee). In that case, instead run:

`mcp__supabase__execute_sql(query="select count(*) as total, count(regression_slope) as fitted from public.backtest_stats")`

and confirm `total` matches the expected currency×horizon count and `fitted` is a plausible (possibly zero) subset of it -- i.e. confirm the column exists and is being written, even if nothing cleared the gate today.

- [ ] **Step 5: Trigger the daily forecast**

On GitHub: repo → Actions → "Generate predictions" → Run workflow → mode = `forecast` → Run workflow. Wait for a green checkmark.

- [ ] **Step 6: Verify the forecast output is sane**

`mcp__supabase__execute_sql(query="select p.quote_code, p.horizon_days, p.predicted_rate, b.regression_slope from public.predictions p join public.backtest_stats b on b.quote_code = p.quote_code and b.horizon_days = p.horizon_days where p.generated_at = (select max(generated_at) from public.predictions) order by p.quote_code, p.horizon_days limit 20")`

For any row where `regression_slope` is not null, spot-check by hand that `predicted_rate` looks like a plausible adjustment (not a wild multiple of a sane baseline) -- e.g. compare against the same currency/horizon's value from before this plan started, if you have it, or simply confirm the value is in the same order of magnitude as the currency's typical rate. For rows where `regression_slope` is null, confirm the currency/horizon still has a sane `predicted_rate` at all (proving the unadjusted fallback path works end-to-end in production, not just in mocked tests).

- [ ] **Step 7: Run the full backend test suite one more time**

Run: `cd backend && python -m pytest -q`
Expected: PASS, every test, no live network calls in the suite itself.

- [ ] **Step 8: Confirm nothing is left uncommitted**

Run: `git status --short`
Expected: clean.

## Definition of Done

- `supabase/migrations/0005_macro_rates.sql` applied; `macro_rates` exists with its RLS policy, `backtest_stats` has the two new nullable columns.
- A real `FRED_API_KEY` is set both in `backend/.env` (local/CI-adjacent use) and as a GitHub Actions repo secret.
- `series_map.py` contains only currency→series_id mappings individually confirmed against the live FRED API, not guessed.
- A scheduled `macro.yml` run populates `macro_rates` for every currency with a confirmed FRED series.
- The weekly backtest job runs end-to-end against live data, correctly leaving `regression_slope`/`regression_intercept` `NULL` wherever coverage or significance doesn't support a fit.
- The daily forecast job produces a correctly adjusted `predicted_rate` for any currency/horizon with a fitted regression and current differential data, and an output unchanged from 2a's behavior for any currency/horizon without one.
- Backend test suite (including all new macro-package tests and the extended prediction tests) passes with no live network calls.
- Roadmap doc's 2b entry is marked shipped, explicitly noting inflation/GDP ingestion remains deferred.
