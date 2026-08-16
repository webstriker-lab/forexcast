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
