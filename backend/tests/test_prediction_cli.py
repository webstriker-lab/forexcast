from unittest.mock import patch

from app.prediction.cli import main


def test_forecast_mode_calls_run_forecast():
    with patch(
        "app.prediction.cli.run_forecast", return_value=116
    ) as mock_forecast, patch("app.prediction.cli.run_backtest_job") as mock_backtest:
        main(["--mode", "forecast"])

    mock_forecast.assert_called_once()
    mock_backtest.assert_not_called()


def test_backtest_mode_calls_run_backtest_job():
    with patch("app.prediction.cli.run_forecast") as mock_forecast, patch(
        "app.prediction.cli.run_backtest_job", return_value=116
    ) as mock_backtest:
        main(["--mode", "backtest"])

    mock_backtest.assert_called_once()
    mock_forecast.assert_not_called()
