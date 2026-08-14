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
