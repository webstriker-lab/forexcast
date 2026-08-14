# Data Ingestion Pipeline (Rates Only) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate and continuously refresh `public.rates_cache` with real exchange-rate data (Frankfurter API, USD-pivot storage) via a one-time historical backfill and an ongoing GitHub Actions daily cron, so the prediction engine has real data to backtest against.

**Architecture:** A new `backend/app/ingestion/` package with three layers — a Frankfurter API client (reads), a Supabase REST I/O layer (reads active currencies, writes rate rows via PostgREST upsert), and orchestration functions (`run_daily`, `run_backfill`) that combine them. A `cross_rate()` pure-computation helper derives non-USD pairs from the stored USD-pivot rows on demand. A CLI entrypoint (`python -m app.ingestion.cli`) is what the GitHub Actions workflow actually invokes — the workflow itself has no ingestion logic, just environment + scheduling.

**Tech Stack:** Same as the existing backend — Python 3.12, `httpx` (already a dependency, no new ones added), pytest. Writes go directly to Supabase's PostgREST REST API using the existing `SUPABASE_SERVICE_KEY` — no new database driver.

**Spec:** `docs/superpowers/specs/2026-08-14-data-ingestion-pipeline-design.md`

## Global Constraints

- No new dependencies beyond what's already in `backend/requirements.txt` (`httpx` covers both the Frankfurter client and the Supabase REST writes).
- Every code task starts with a failing test before implementation (TDD).
- No live network calls in the automated test suite — all `httpx` calls are mocked. Live verification against the real Frankfurter API and the real Supabase project happens only in Task 8's manual steps.
- Frankfurter only in this plan — GDELT and FRED are explicitly out of scope (deferred to the prediction-engine task; see spec §2).
- Every external service used stays on its permanently free tier (Frankfurter: free, no key; GitHub Actions: free; Supabase: free tier already provisioned).

---

### Task 1: Currency migration — drop AED, add Frankfurter's 19 remaining currencies

**Files:**
- Create: `supabase/migrations/0002_expand_currencies.sql`

**Interfaces:**
- Produces: `public.currencies` now contains exactly the 30 currencies Frankfurter supports (11 previously-seeded + 19 new, `AED` removed) — consumed by Task 3's `get_active_currencies()`.

- [ ] **Step 1: Write `supabase/migrations/0002_expand_currencies.sql`**

```sql
-- Frankfurter (ECB reference rates) does not publish a rate for AED; drop it.
-- No dependent rows exist yet (no watchlist/alert entries reference it).
delete from public.currencies where code = 'AED';

-- Add the remaining currencies Frankfurter supports, to reach its full
-- 30-currency set (see design doc §4 for the verification behind this list).
insert into public.currencies (code, name) values
    ('BRL', 'Brazilian Real'),
    ('CZK', 'Czech Koruna'),
    ('DKK', 'Danish Krone'),
    ('HKD', 'Hong Kong Dollar'),
    ('HUF', 'Hungarian Forint'),
    ('IDR', 'Indonesian Rupiah'),
    ('ILS', 'Israeli New Shekel'),
    ('ISK', 'Icelandic Króna'),
    ('KRW', 'South Korean Won'),
    ('MXN', 'Mexican Peso'),
    ('MYR', 'Malaysian Ringgit'),
    ('NOK', 'Norwegian Krone'),
    ('PHP', 'Philippine Peso'),
    ('PLN', 'Polish Złoty'),
    ('RON', 'Romanian Leu'),
    ('SEK', 'Swedish Krona'),
    ('THB', 'Thai Baht'),
    ('TRY', 'Turkish Lira'),
    ('ZAR', 'South African Rand');
```

- [ ] **Step 2: Apply the migration to the live Supabase project**

If `mcp__supabase__apply_migration` and `mcp__supabase__execute_sql` aren't already loaded, load them first:

`ToolSearch(query="select:mcp__supabase__apply_migration,mcp__supabase__execute_sql,mcp__supabase__list_tables")`

Then call:

`mcp__supabase__apply_migration(name="0002_expand_currencies", query=<the SQL from Step 1>)`

Expected: `{"success": true}`.

- [ ] **Step 3: Verify the currency table**

Run: `mcp__supabase__execute_sql(query="select count(*) from public.currencies")`
Expected: `30`.

Run: `mcp__supabase__execute_sql(query="select code from public.currencies where code = 'AED'")`
Expected: empty result (no rows).

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/0002_expand_currencies.sql
git commit -m "feat(db): expand currency list to Frankfurter's 30-currency set"
```

---

### Task 2: Frankfurter API client

**Files:**
- Create: `backend/app/ingestion/__init__.py` (empty)
- Create: `backend/app/ingestion/frankfurter.py`
- Test: `backend/tests/test_frankfurter.py`

**Interfaces:**
- Produces: `fetch_latest(base: str, symbols: list[str]) -> dict` and `fetch_range(base: str, symbols: list[str], start: str, end: str) -> dict` in `app.ingestion.frankfurter`. Both raise `httpx.HTTPStatusError` on a non-2xx response (propagated, not caught) — consumed by Task 5's `run_daily`/`run_backfill`.

- [ ] **Step 1: Create the empty package marker**

Create `backend/app/ingestion/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing test**

`backend/tests/test_frankfurter.py`:

```python
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.ingestion.frankfurter import fetch_latest, fetch_range


def test_fetch_latest_calls_correct_endpoint_and_returns_json():
    mock_response = MagicMock()
    mock_response.json.return_value = {"date": "2026-08-13", "rates": {"EUR": 0.867}}
    mock_response.raise_for_status.return_value = None
    with patch("app.ingestion.frankfurter.httpx.get", return_value=mock_response) as mock_get:
        result = fetch_latest("USD", ["EUR", "GBP"])

    assert result == {"date": "2026-08-13", "rates": {"EUR": 0.867}}
    mock_get.assert_called_once_with(
        "https://api.frankfurter.dev/v1/latest",
        params={"base": "USD", "symbols": "EUR,GBP"},
        timeout=30.0,
    )


def test_fetch_latest_raises_on_http_error():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "error", request=MagicMock(), response=MagicMock()
    )
    with patch("app.ingestion.frankfurter.httpx.get", return_value=mock_response):
        with pytest.raises(httpx.HTTPStatusError):
            fetch_latest("USD", ["EUR"])


def test_fetch_range_calls_correct_endpoint_and_returns_json():
    mock_response = MagicMock()
    mock_response.json.return_value = {"rates": {"2026-08-01": {"EUR": 0.86}}}
    mock_response.raise_for_status.return_value = None
    with patch("app.ingestion.frankfurter.httpx.get", return_value=mock_response) as mock_get:
        result = fetch_range("USD", ["EUR"], "2026-01-01", "2026-08-01")

    assert result == {"rates": {"2026-08-01": {"EUR": 0.86}}}
    mock_get.assert_called_once_with(
        "https://api.frankfurter.dev/v1/2026-01-01..2026-08-01",
        params={"base": "USD", "symbols": "EUR"},
        timeout=60.0,
    )
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest backend/tests/test_frankfurter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion.frankfurter'`.

- [ ] **Step 4: Implement `backend/app/ingestion/frankfurter.py`**

```python
import httpx

FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"


def fetch_latest(base: str, symbols: list[str]) -> dict:
    response = httpx.get(
        f"{FRANKFURTER_BASE_URL}/latest",
        params={"base": base, "symbols": ",".join(symbols)},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_range(base: str, symbols: list[str], start: str, end: str) -> dict:
    response = httpx.get(
        f"{FRANKFURTER_BASE_URL}/{start}..{end}",
        params={"base": base, "symbols": ",".join(symbols)},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest backend/tests/test_frankfurter.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/__init__.py backend/app/ingestion/frankfurter.py backend/tests/test_frankfurter.py
git commit -m "feat(backend): add Frankfurter API client for rate ingestion"
```

---

### Task 3: Supabase REST I/O layer

**Files:**
- Create: `backend/app/ingestion/supabase_rest.py`
- Test: `backend/tests/test_supabase_rest.py`

**Interfaces:**
- Consumes: `get_settings()` from `app.config` (existing — `.supabase_url`, `.supabase_service_key`).
- Produces: `get_active_currencies() -> list[str]`, `upsert_rates(rows: list[dict]) -> None`, `get_usd_rate(as_of: str, currency_code: str) -> float | None` in `app.ingestion.supabase_rest`. Consumed by Task 4 (`get_usd_rate`) and Task 5 (`get_active_currencies`, `upsert_rates`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_supabase_rest.py`:

```python
from unittest.mock import MagicMock, patch

from app.ingestion.supabase_rest import get_active_currencies, get_usd_rate, upsert_rates


def test_get_active_currencies_returns_sorted_codes():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"code": "USD"}, {"code": "EUR"}, {"code": "AUD"}]
    mock_response.raise_for_status.return_value = None
    with patch("app.ingestion.supabase_rest.httpx.get", return_value=mock_response) as mock_get:
        result = get_active_currencies()

    assert result == ["AUD", "EUR", "USD"]
    args, kwargs = mock_get.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/currencies"
    assert kwargs["params"] == {"select": "code", "is_active": "eq.true"}
    assert kwargs["headers"]["apikey"] == "test-service-key"


def test_upsert_rates_sends_one_batch_when_under_batch_size():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [{"base_code": "USD", "quote_code": "EUR", "rate": 0.867, "as_of": "2026-08-13"}]
    with patch("app.ingestion.supabase_rest.httpx.post", return_value=mock_response) as mock_post:
        upsert_rates(rows)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/rates_cache"
    assert kwargs["params"] == {"on_conflict": "base_code,quote_code,as_of"}
    assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates"
    assert kwargs["json"] == rows


def test_upsert_rates_batches_large_row_sets():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {"base_code": "USD", "quote_code": "EUR", "rate": 0.867, "as_of": f"2026-01-{i:02d}"}
        for i in range(1, 11)
    ]
    with patch("app.ingestion.supabase_rest.httpx.post", return_value=mock_response) as mock_post:
        with patch("app.ingestion.supabase_rest.BATCH_SIZE", 4):
            upsert_rates(rows)

    assert mock_post.call_count == 3
    sent_row_counts = [len(call.kwargs["json"]) for call in mock_post.call_args_list]
    assert sent_row_counts == [4, 4, 2]


def test_get_usd_rate_for_usd_returns_one_without_a_request():
    with patch("app.ingestion.supabase_rest.httpx.get") as mock_get:
        result = get_usd_rate("2026-08-13", "USD")

    assert result == 1.0
    mock_get.assert_not_called()


def test_get_usd_rate_returns_value_when_found():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"rate": 0.867}]
    mock_response.raise_for_status.return_value = None
    with patch("app.ingestion.supabase_rest.httpx.get", return_value=mock_response) as mock_get:
        result = get_usd_rate("2026-08-13", "EUR")

    assert result == 0.867
    args, kwargs = mock_get.call_args
    assert kwargs["params"] == {
        "select": "rate",
        "base_code": "eq.USD",
        "quote_code": "eq.EUR",
        "as_of": "eq.2026-08-13",
    }


def test_get_usd_rate_returns_none_when_not_found():
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None
    with patch("app.ingestion.supabase_rest.httpx.get", return_value=mock_response):
        result = get_usd_rate("2026-08-13", "EUR")

    assert result is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_supabase_rest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion.supabase_rest'`.

- [ ] **Step 3: Implement `backend/app/ingestion/supabase_rest.py`**

```python
import httpx

from app.config import get_settings

BATCH_SIZE = 500


def _headers(prefer: str | None = None) -> dict:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def get_active_currencies() -> list[str]:
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/currencies",
        params={"select": "code", "is_active": "eq.true"},
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return sorted(row["code"] for row in response.json())


def upsert_rates(rows: list[dict]) -> None:
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/rates_cache",
            params={"on_conflict": "base_code,quote_code,as_of"},
            headers=_headers(prefer="resolution=merge-duplicates"),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()


def get_usd_rate(as_of: str, currency_code: str) -> float | None:
    if currency_code == "USD":
        return 1.0
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/rates_cache",
        params={
            "select": "rate",
            "base_code": "eq.USD",
            "quote_code": f"eq.{currency_code}",
            "as_of": f"eq.{as_of}",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    results = response.json()
    return float(results[0]["rate"]) if results else None
```

**Note:** `test_upsert_rates_batches_large_row_sets` patches the module-level `BATCH_SIZE` constant directly to keep the test fast (4 rows instead of 500) — this works because `upsert_rates` reads `BATCH_SIZE` from its own module namespace at call time, not as a captured default argument.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_supabase_rest.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/supabase_rest.py backend/tests/test_supabase_rest.py
git commit -m "feat(backend): add Supabase REST I/O layer for rate ingestion"
```

---

### Task 4: USD-pivot cross-rate helper

**Files:**
- Create: `backend/app/ingestion/cross_rate.py`
- Test: `backend/tests/test_cross_rate.py`

**Interfaces:**
- Consumes: `get_usd_rate(as_of: str, currency_code: str) -> float | None` from `app.ingestion.supabase_rest` (Task 3).
- Produces: `cross_rate(as_of: str, from_code: str, to_code: str) -> float` in `app.ingestion.cross_rate`. No consumer yet in this plan — this is ready for the prediction-engine task to import directly (see spec §5).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_cross_rate.py`:

```python
from unittest.mock import patch

import pytest

from app.ingestion.cross_rate import cross_rate


def test_same_currency_returns_one_without_lookup():
    with patch("app.ingestion.cross_rate.get_usd_rate") as mock_get:
        result = cross_rate("2026-08-13", "EUR", "EUR")

    assert result == 1.0
    mock_get.assert_not_called()


def test_computes_cross_rate_via_usd_pivot():
    def fake_get_usd_rate(as_of, code):
        return {"EUR": 2.0, "INR": 10.0}[code]

    with patch("app.ingestion.cross_rate.get_usd_rate", side_effect=fake_get_usd_rate):
        result = cross_rate("2026-08-13", "EUR", "INR")

    assert result == 5.0


def test_calls_get_usd_rate_with_correct_args():
    def fake_get_usd_rate(as_of, code):
        return {"EUR": 2.0, "INR": 10.0}[code]

    with patch(
        "app.ingestion.cross_rate.get_usd_rate", side_effect=fake_get_usd_rate
    ) as mock_get:
        cross_rate("2026-08-13", "EUR", "INR")

    mock_get.assert_any_call("2026-08-13", "EUR")
    mock_get.assert_any_call("2026-08-13", "INR")


def test_raises_when_from_rate_missing():
    def fake_get_usd_rate(as_of, code):
        return None if code == "EUR" else 10.0

    with patch("app.ingestion.cross_rate.get_usd_rate", side_effect=fake_get_usd_rate):
        with pytest.raises(ValueError, match="EUR"):
            cross_rate("2026-08-13", "EUR", "INR")


def test_raises_when_to_rate_missing():
    def fake_get_usd_rate(as_of, code):
        return 2.0 if code == "EUR" else None

    with patch("app.ingestion.cross_rate.get_usd_rate", side_effect=fake_get_usd_rate):
        with pytest.raises(ValueError, match="INR"):
            cross_rate("2026-08-13", "EUR", "INR")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_cross_rate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion.cross_rate'`.

- [ ] **Step 3: Implement `backend/app/ingestion/cross_rate.py`**

```python
from app.ingestion.supabase_rest import get_usd_rate


def cross_rate(as_of: str, from_code: str, to_code: str) -> float:
    if from_code == to_code:
        return 1.0

    from_rate = get_usd_rate(as_of, from_code)
    to_rate = get_usd_rate(as_of, to_code)

    if from_rate is None:
        raise ValueError(f"No USD rate for {from_code} on {as_of}")
    if to_rate is None:
        raise ValueError(f"No USD rate for {to_code} on {as_of}")

    return to_rate / from_rate
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_cross_rate.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/cross_rate.py backend/tests/test_cross_rate.py
git commit -m "feat(backend): add USD-pivot cross-rate helper"
```

---

### Task 5: Daily and backfill ingestion orchestration

**Files:**
- Create: `backend/app/ingestion/rates.py`
- Test: `backend/tests/test_rates.py`

**Interfaces:**
- Consumes: `fetch_latest`, `fetch_range` from `app.ingestion.frankfurter` (Task 2); `get_active_currencies`, `upsert_rates` from `app.ingestion.supabase_rest` (Task 3).
- Produces: `run_daily() -> int` and `run_backfill(start_date: str = "1999-01-04", end_date: str | None = None) -> int` in `app.ingestion.rates` (both return the number of rows upserted). Consumed by Task 6's CLI.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_rates.py`:

```python
from unittest.mock import patch

from app.ingestion.rates import run_backfill, run_daily


def test_run_daily_fetches_and_upserts_latest_rates():
    with patch(
        "app.ingestion.rates.get_active_currencies", return_value=["USD", "EUR", "INR"]
    ), patch(
        "app.ingestion.rates.fetch_latest",
        return_value={"date": "2026-08-13", "rates": {"EUR": 0.867, "INR": 95.44}},
    ) as mock_fetch, patch("app.ingestion.rates.upsert_rates") as mock_upsert:
        count = run_daily()

    mock_fetch.assert_called_once_with("USD", ["EUR", "INR"])
    mock_upsert.assert_called_once_with(
        [
            {"base_code": "USD", "quote_code": "EUR", "rate": 0.867, "as_of": "2026-08-13"},
            {"base_code": "USD", "quote_code": "INR", "rate": 95.44, "as_of": "2026-08-13"},
        ]
    )
    assert count == 2


def test_run_daily_excludes_usd_from_requested_symbols():
    with patch(
        "app.ingestion.rates.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.ingestion.rates.fetch_latest",
        return_value={"date": "2026-08-13", "rates": {"EUR": 0.867}},
    ) as mock_fetch, patch("app.ingestion.rates.upsert_rates"):
        run_daily()

    mock_fetch.assert_called_once_with("USD", ["EUR"])


def test_run_backfill_flattens_range_response_into_rows():
    with patch(
        "app.ingestion.rates.get_active_currencies", return_value=["USD", "EUR", "INR"]
    ), patch(
        "app.ingestion.rates.fetch_range",
        return_value={
            "rates": {
                "2020-01-01": {"EUR": 0.9, "INR": 71.0},
                "2020-01-02": {"EUR": 0.91, "INR": 71.5},
            }
        },
    ) as mock_fetch, patch("app.ingestion.rates.upsert_rates") as mock_upsert:
        count = run_backfill(start_date="2020-01-01", end_date="2020-01-02")

    mock_fetch.assert_called_once_with("USD", ["EUR", "INR"], "2020-01-01", "2020-01-02")
    upserted_rows = mock_upsert.call_args[0][0]
    assert len(upserted_rows) == 4
    assert {
        "base_code": "USD",
        "quote_code": "EUR",
        "rate": 0.9,
        "as_of": "2020-01-01",
    } in upserted_rows
    assert count == 4


def test_run_backfill_defaults_start_date_to_1999():
    with patch(
        "app.ingestion.rates.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.ingestion.rates.fetch_range", return_value={"rates": {}}
    ) as mock_fetch, patch("app.ingestion.rates.upsert_rates"):
        run_backfill(end_date="2020-01-01")

    mock_fetch.assert_called_once_with("USD", ["EUR"], "1999-01-04", "2020-01-01")


def test_run_backfill_defaults_end_date_to_today():
    with patch(
        "app.ingestion.rates.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.ingestion.rates.fetch_range", return_value={"rates": {}}
    ) as mock_fetch, patch("app.ingestion.rates.upsert_rates"):
        run_backfill(start_date="2020-01-01")

    args = mock_fetch.call_args[0]
    assert args[0] == "USD"
    assert args[1] == ["EUR"]
    assert args[2] == "2020-01-01"
    assert len(args[3]) == 10  # a YYYY-MM-DD string, not asserting the exact date
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_rates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion.rates'`.

- [ ] **Step 3: Implement `backend/app/ingestion/rates.py`**

```python
from datetime import date

from app.ingestion.frankfurter import fetch_latest, fetch_range
from app.ingestion.supabase_rest import get_active_currencies, upsert_rates

PIVOT = "USD"


def _non_pivot_currencies() -> list[str]:
    return [code for code in get_active_currencies() if code != PIVOT]


def run_daily() -> int:
    symbols = _non_pivot_currencies()
    data = fetch_latest(PIVOT, symbols)
    as_of = data["date"]
    rows = [
        {"base_code": PIVOT, "quote_code": code, "rate": rate, "as_of": as_of}
        for code, rate in data["rates"].items()
    ]
    upsert_rates(rows)
    return len(rows)


def run_backfill(start_date: str = "1999-01-04", end_date: str | None = None) -> int:
    symbols = _non_pivot_currencies()
    end_date = end_date or date.today().isoformat()
    data = fetch_range(PIVOT, symbols, start_date, end_date)
    rows = [
        {"base_code": PIVOT, "quote_code": code, "rate": rate, "as_of": as_of}
        for as_of, day_rates in data["rates"].items()
        for code, rate in day_rates.items()
    ]
    upsert_rates(rows)
    return len(rows)
```

**Note:** neither function requires special-case logic for a currency missing from a given historical date's response (see design spec §3) — `day_rates.items()` only ever contains whatever Frankfurter actually returned for that date, so a missing currency is naturally skipped for that row without any extra branching.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_rates.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/rates.py backend/tests/test_rates.py
git commit -m "feat(backend): add daily and backfill rate ingestion orchestration"
```

---

### Task 6: CLI entrypoint

**Files:**
- Create: `backend/app/ingestion/cli.py`
- Test: `backend/tests/test_cli.py`

**Interfaces:**
- Consumes: `run_daily() -> int`, `run_backfill(start_date, end_date) -> int` from `app.ingestion.rates` (Task 5).
- Produces: `main(argv: list[str] | None = None) -> None` in `app.ingestion.cli`, runnable as `python -m app.ingestion.cli --mode daily` or `--mode backfill [--start-date ...] [--end-date ...]`. Consumed by Task 7's GitHub Actions workflow.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_cli.py`:

```python
from unittest.mock import patch

from app.ingestion.cli import main


def test_daily_mode_calls_run_daily():
    with patch("app.ingestion.cli.run_daily", return_value=29) as mock_daily, patch(
        "app.ingestion.cli.run_backfill"
    ) as mock_backfill:
        main(["--mode", "daily"])

    mock_daily.assert_called_once()
    mock_backfill.assert_not_called()


def test_backfill_mode_calls_run_backfill_with_dates():
    with patch("app.ingestion.cli.run_daily") as mock_daily, patch(
        "app.ingestion.cli.run_backfill", return_value=200000
    ) as mock_backfill:
        main(["--mode", "backfill", "--start-date", "2020-01-01", "--end-date", "2020-01-02"])

    mock_backfill.assert_called_once_with(start_date="2020-01-01", end_date="2020-01-02")
    mock_daily.assert_not_called()


def test_backfill_mode_defaults_dates():
    with patch("app.ingestion.cli.run_daily"), patch(
        "app.ingestion.cli.run_backfill", return_value=0
    ) as mock_backfill:
        main(["--mode", "backfill"])

    mock_backfill.assert_called_once_with(start_date="1999-01-04", end_date=None)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion.cli'`.

- [ ] **Step 3: Implement `backend/app/ingestion/cli.py`**

```python
import argparse

from app.ingestion.rates import run_backfill, run_daily


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ForexCast rate ingestion")
    parser.add_argument("--mode", choices=["daily", "backfill"], required=True)
    parser.add_argument("--start-date", default="1999-01-04")
    parser.add_argument("--end-date", default=None)
    args = parser.parse_args(argv)

    if args.mode == "daily":
        count = run_daily()
    else:
        count = run_backfill(start_date=args.start_date, end_date=args.end_date)

    print(f"Upserted {count} rate rows ({args.mode})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_cli.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full backend suite to confirm nothing broke**

Run: `pytest backend/tests -v`
Expected: PASS (all tests — the 10 from the foundation plan plus the new ingestion tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/cli.py backend/tests/test_cli.py
git commit -m "feat(backend): add rate ingestion CLI entrypoint"
```

---

### Task 7: GitHub Actions scheduled workflow

**Files:**
- Create: `.github/workflows/ingest-rates.yml`

**Interfaces:**
- Consumes: `backend/requirements.txt` (existing), `python -m app.ingestion.cli` (Task 6).
- Produces: none consumed by later tasks — this is a leaf task.

- [ ] **Step 1: Create `.github/workflows/ingest-rates.yml`**

```yaml
name: Ingest exchange rates

on:
  # 17:00 UTC covers ECB's ~16:00 CET/CEST publish time year-round (CET is
  # UTC+1 in winter, CEST is UTC+2 in summer, so 17:00 UTC is safely after
  # publication in both cases).
  schedule:
    - cron: '0 17 * * *'
  workflow_dispatch:
    inputs:
      mode:
        description: 'Ingestion mode'
        required: true
        default: 'daily'
        type: choice
        options:
          - daily
          - backfill
      start_date:
        description: 'Backfill start date (YYYY-MM-DD), defaults to 1999-01-04'
        required: false
        default: ''
      end_date:
        description: 'Backfill end date (YYYY-MM-DD), defaults to today'
        required: false
        default: ''

jobs:
  ingest:
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
      - name: Run ingestion
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
        run: |
          MODE="${{ github.event.inputs.mode || 'daily' }}"
          if [ "$MODE" = "backfill" ]; then
            ARGS="--mode backfill"
            if [ -n "${{ github.event.inputs.start_date }}" ]; then
              ARGS="$ARGS --start-date ${{ github.event.inputs.start_date }}"
            fi
            if [ -n "${{ github.event.inputs.end_date }}" ]; then
              ARGS="$ARGS --end-date ${{ github.event.inputs.end_date }}"
            fi
            python -m app.ingestion.cli $ARGS
          else
            python -m app.ingestion.cli --mode daily
          fi
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ingest-rates.yml
git commit -m "ci: add scheduled GitHub Actions workflow for rate ingestion"
```

---

### Task 8: Manual setup and end-to-end verification

- [ ] **Step 1: Add GitHub Actions repository secrets**

On GitHub: repo → Settings → Secrets and variables → Actions → New repository secret. Add two secrets:
- `SUPABASE_URL` — same value as `backend/.env`'s `SUPABASE_URL`.
- `SUPABASE_SERVICE_KEY` — same value as `backend/.env`'s `SUPABASE_SERVICE_KEY`.

- [ ] **Step 2: Trigger a manual backfill run**

On GitHub: repo → Actions → "Ingest exchange rates" → Run workflow → mode = `backfill` (leave start/end date blank to use the full 1999-01-04-to-today default) → Run workflow.

Wait for it to complete. Expected: green checkmark, no failed steps.

- [ ] **Step 3: Verify the backfill actually populated data**

If `mcp__supabase__execute_sql` isn't already loaded: `ToolSearch(query="select:mcp__supabase__execute_sql")`.

Run: `mcp__supabase__execute_sql(query="select count(*) from public.rates_cache")`
Expected: a large number (roughly 150,000–220,000, given ~29 currencies × ~27 years of business days, accounting for the partial-coverage gaps in early years noted in the design spec).

Run: `mcp__supabase__execute_sql(query="select min(as_of), max(as_of) from public.rates_cache")`
Expected: `min` at or near `1999-01-04`, `max` at or near today's date.

- [ ] **Step 4: Trigger a manual daily run to confirm the ongoing path works independently of backfill**

On GitHub: repo → Actions → "Ingest exchange rates" → Run workflow → mode = `daily` → Run workflow. Expected: green checkmark.

- [ ] **Step 5: Run the full backend test suite one more time**

Run: `pytest backend/tests -v`
Expected: PASS, all tests, no live network calls made.

- [ ] **Step 6: Confirm nothing is left uncommitted**

Run: `git status --short`
Expected: clean (empty output) — every prior task already committed its own changes.

## Definition of Done

- `public.currencies` has exactly 30 rows matching Frankfurter's supported set; `AED` is gone.
- `pytest backend/tests -v` passes, including all new ingestion tests, with zero live network calls.
- A manual `workflow_dispatch` backfill run completes successfully and `rates_cache` contains data spanning from 1999-01-04 to today.
- A manual `workflow_dispatch` daily run completes successfully.
- The scheduled trigger (`cron: '0 17 * * *'`) is present in the committed workflow file, so it will run automatically going forward with no further action needed.
- `cross_rate()` is implemented, tested, and ready for the prediction-engine task to import.
