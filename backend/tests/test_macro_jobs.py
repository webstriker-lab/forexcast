from unittest.mock import patch

from app.macro.jobs import (
    run_cpi_ingestion,
    run_current_account_ingestion,
    run_gdp_ingestion,
    run_macro_ingestion,
    run_series_ingestion,
)


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


# --- generic run_series_ingestion, reused by the three new fundamentals
# (run_macro_ingestion above keeps its own dedicated implementation,
# untouched) ---


def test_run_series_ingestion_upserts_all_mapped_currencies_to_the_given_table():
    fake_series = {"USD": "CPALTT01USM659N", "EUR": "CPHPTT01EZM659N"}
    fake_observations = {
        "CPALTT01USM659N": [("2020-01-01", 2.5)],
        "CPHPTT01EZM659N": [("2020-01-01", 1.1), ("2020-02-01", 1.2)],
    }
    with patch(
        "app.macro.jobs.fetch_observations",
        side_effect=lambda series_id: fake_observations[series_id],
    ), patch("app.macro.jobs.upsert_series") as mock_upsert:
        count = run_series_ingestion(fake_series, "macro_cpi")

    assert count == 3
    table_arg, rows = mock_upsert.call_args[0]
    assert table_arg == "macro_cpi"
    assert {"currency_code": "USD", "as_of": "2020-01-01", "series_id": "CPALTT01USM659N", "rate": 2.5} in rows
    assert {"currency_code": "EUR", "as_of": "2020-02-01", "series_id": "CPHPTT01EZM659N", "rate": 1.2} in rows


def test_run_series_ingestion_skips_currency_with_no_data():
    fake_series = {"USD": "CPALTT01USM659N", "XYZ": "CPALTT01XXM659N"}
    with patch(
        "app.macro.jobs.fetch_observations",
        side_effect=lambda series_id: None if series_id == "CPALTT01XXM659N" else [("2020-01-01", 2.5)],
    ), patch("app.macro.jobs.upsert_series") as mock_upsert:
        count = run_series_ingestion(fake_series, "macro_cpi")

    assert count == 1
    _, rows = mock_upsert.call_args[0]
    assert all(r["currency_code"] == "USD" for r in rows)


def test_run_series_ingestion_propagates_unexpected_errors():
    fake_series = {"USD": "CPALTT01USM659N"}
    with patch(
        "app.macro.jobs.fetch_observations", side_effect=RuntimeError("boom")
    ), patch("app.macro.jobs.upsert_series") as mock_upsert:
        try:
            run_series_ingestion(fake_series, "macro_cpi")
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass
    mock_upsert.assert_not_called()


def test_cpi_gdp_current_account_wrappers_target_the_right_map_and_table():
    with patch("app.macro.jobs.run_series_ingestion", return_value=7) as mock_run:
        assert run_cpi_ingestion() == 7
        assert run_gdp_ingestion() == 7
        assert run_current_account_ingestion() == 7

    tables = [call.args[1] for call in mock_run.call_args_list]
    assert tables == ["macro_cpi", "macro_gdp", "macro_current_account"]
