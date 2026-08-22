from unittest.mock import patch

from app.macro.cli import main


def test_main_calls_all_four_ingestion_jobs():
    with patch("app.macro.cli.run_macro_ingestion", return_value=42) as mock_rate, patch(
        "app.macro.cli.run_cpi_ingestion", return_value=1
    ) as mock_cpi, patch(
        "app.macro.cli.run_gdp_ingestion", return_value=2
    ) as mock_gdp, patch(
        "app.macro.cli.run_current_account_ingestion", return_value=3
    ) as mock_ca:
        main()

    mock_rate.assert_called_once()
    mock_cpi.assert_called_once()
    mock_gdp.assert_called_once()
    mock_ca.assert_called_once()


def test_main_propagates_errors():
    with patch("app.macro.cli.run_macro_ingestion", side_effect=RuntimeError("boom")):
        try:
            main()
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass


def test_main_propagates_errors_from_later_ingestion_jobs_too():
    with patch("app.macro.cli.run_macro_ingestion", return_value=0), patch(
        "app.macro.cli.run_cpi_ingestion", return_value=0
    ), patch("app.macro.cli.run_gdp_ingestion", side_effect=RuntimeError("boom")), patch(
        "app.macro.cli.run_current_account_ingestion"
    ) as mock_ca:
        try:
            main()
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass
    mock_ca.assert_not_called()
