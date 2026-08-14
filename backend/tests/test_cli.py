from unittest.mock import patch

import pytest

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


def test_daily_mode_propagates_run_daily_error():
    with patch(
        "app.ingestion.cli.run_daily", side_effect=RuntimeError("boom")
    ), patch("app.ingestion.cli.run_backfill") as mock_backfill:
        with pytest.raises(RuntimeError):
            main(["--mode", "daily"])

    mock_backfill.assert_not_called()
