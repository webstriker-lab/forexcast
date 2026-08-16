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
