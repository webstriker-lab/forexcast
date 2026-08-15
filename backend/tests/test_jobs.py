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
        },
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
        },
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
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        count = run_forecast()

    assert count == 0
    mock_insert.assert_called_once_with([])


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
        "app.prediction.jobs.run_backtest", return_value=fake_results
    ), patch("app.prediction.jobs.upsert_backtest_stats") as mock_upsert:
        count = run_backtest_job()

    assert count == 1  # horizon 30 skipped (no samples), only horizon 7 written
    rows = mock_upsert.call_args[0][0]
    assert rows[0]["quote_code"] == "EUR"
    assert rows[0]["horizon_days"] == 7
    assert rows[0]["sample_count"] == 3
