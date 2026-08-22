from unittest.mock import MagicMock, patch

import httpx
import pytest

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
            {"base_code": "EUR", "quote_code": "INR", "rate": 110.080738, "as_of": "2026-08-13"},
            {"base_code": "INR", "quote_code": "EUR", "rate": 0.009084, "as_of": "2026-08-13"},
        ]
    )
    assert count == 4


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
    assert len(upserted_rows) == 8
    assert {
        "base_code": "USD",
        "quote_code": "EUR",
        "rate": 0.9,
        "as_of": "2020-01-01",
    } in upserted_rows
    assert {
        "base_code": "EUR",
        "quote_code": "INR",
        "rate": 78.888889,
        "as_of": "2020-01-01",
    } in upserted_rows
    assert {
        "base_code": "INR",
        "quote_code": "EUR",
        "rate": 0.012676,
        "as_of": "2020-01-01",
    } in upserted_rows
    assert count == 8


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


def test_run_daily_propagates_fetch_error():
    with patch(
        "app.ingestion.rates.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.ingestion.rates.fetch_latest",
        side_effect=httpx.HTTPStatusError("error", request=MagicMock(), response=MagicMock()),
    ), patch("app.ingestion.rates.upsert_rates") as mock_upsert:
        with pytest.raises(httpx.HTTPStatusError):
            run_daily()

    mock_upsert.assert_not_called()


def test_run_daily_integration_across_module_boundaries():
    """Drives run_daily() through the real frankfurter and supabase_rest
    modules, mocking only at the httpx boundary, so a signature mismatch
    between modules would actually be caught.

    frankfurter.py and supabase_rest.py both call the same underlying
    `httpx.get` function object, so they must be dispatched from a single
    patch on `httpx.get` (patching each module's `httpx.get` separately
    would just have the second patch clobber the first, since both dotted
    paths resolve to the same object).
    """
    currencies_response = MagicMock()
    currencies_response.json.return_value = [{"code": "USD"}, {"code": "EUR"}, {"code": "INR"}]
    currencies_response.raise_for_status.return_value = None

    latest_response = MagicMock()
    latest_response.json.return_value = {
        "date": "2026-08-13",
        "rates": {"EUR": 0.867, "INR": 95.44},
    }
    latest_response.raise_for_status.return_value = None

    upsert_response = MagicMock()
    upsert_response.raise_for_status.return_value = None

    def fake_get(url, **kwargs):
        return latest_response if "frankfurter" in url else currencies_response

    with patch("httpx.get", side_effect=fake_get), patch(
        "app.ingestion.supabase_rest.httpx.post", return_value=upsert_response
    ) as mock_post:
        count = run_daily()

    assert count == 4
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/rates_cache"
    assert kwargs["json"] == [
        {"base_code": "USD", "quote_code": "EUR", "rate": 0.867, "as_of": "2026-08-13"},
        {"base_code": "USD", "quote_code": "INR", "rate": 95.44, "as_of": "2026-08-13"},
        {"base_code": "EUR", "quote_code": "INR", "rate": 110.080738, "as_of": "2026-08-13"},
        {"base_code": "INR", "quote_code": "EUR", "rate": 0.009084, "as_of": "2026-08-13"},
    ]
