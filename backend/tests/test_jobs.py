# backend/tests/test_jobs.py
from unittest.mock import patch

import pytest

from app.prediction.backtest import summarize
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
    ), patch(
        "app.prediction.jobs.get_latest_series_value", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
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
    ), patch(
        "app.prediction.jobs.get_latest_series_value", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
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
    ), patch(
        "app.prediction.jobs.get_latest_series_value", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
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
            "regression_factor": "interest_rate",
            "regression_slope": 0.004,
            "regression_intercept": -0.01,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate",
        side_effect=lambda code: 0.06 if code == "EUR" else 0.01,  # differential = 0.05
    ), patch(
        "app.prediction.jobs.get_latest_series_value", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
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
            "regression_factor": "interest_rate",
            "regression_slope": 0.004,
            "regression_intercept": -0.01,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_series_value", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    assert rows[0]["predicted_rate"] == 0.91  # unadjusted -- no current differential


def test_run_forecast_uses_the_current_value_of_whichever_factor_won():
    # regression_factor="cpi" must pull today's CPI differential, not the
    # interest-rate one -- even though a (non-None) interest-rate
    # differential is also available, it must NOT be used for the
    # adjustment.
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
            "regression_factor": "cpi",
            "regression_slope": 0.004,
            "regression_intercept": -0.01,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate",
        side_effect=lambda code: 0.06 if code == "EUR" else 0.01,  # would-be differential = 0.05
    ), patch(
        "app.prediction.jobs.get_latest_series_value",
        side_effect=lambda table, code: (
            (2.5 if code == "EUR" else 2.0) if table == "macro_cpi" else None
        ),  # cpi differential = 0.5
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    expected_predicted = 0.91 * (1 + (0.004 * 0.5 + -0.01))
    assert rows[0]["predicted_rate"] == expected_predicted


def test_run_forecast_uses_naive_forecast_when_model_selected_is_naive():
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 99 + [0.95]),
    ), patch(
        "app.prediction.jobs.forecast", return_value=0.5,  # must NOT be used
    ), patch(
        "app.prediction.jobs.realized_volatility", return_value=0.01
    ), patch(
        "app.prediction.jobs.get_backtest_stats",
        return_value={
            "model_selected": "naive",
            "error_lower_pct": -0.02,
            "error_upper_pct": 0.03,
            "volatility_p90": 0.02,
            "regression_slope": None,
            "regression_intercept": None,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_series_value", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    # naive_forecast(rates, steps) == rates[-1] == 0.95, not the mocked
    # forecast() return value of 0.5.
    assert all(r["predicted_rate"] == 0.95 for r in rows)


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
        "app.prediction.jobs.get_series_history", return_value=[]
    ), patch(
        "app.prediction.jobs.run_backtest", return_value=fake_results
    ), patch("app.prediction.jobs.upsert_backtest_stats") as mock_upsert:
        count = run_backtest_job()

    assert count == 1  # horizon 30 skipped (no samples), only horizon 7 written
    rows = mock_upsert.call_args[0][0]
    assert rows[0]["quote_code"] == "EUR"
    assert rows[0]["horizon_days"] == 7
    assert rows[0]["sample_count"] == 3
    assert rows[0]["regression_factor"] is None
    assert rows[0]["regression_slope"] is None
    assert rows[0]["regression_intercept"] is None
    # No naive_errors provided in fake_results -> summarize() defaults to
    # the historical model, and that default must be persisted, not dropped.
    assert rows[0]["model_selected"] == "exponential_smoothing"


def test_run_backtest_job_stores_naive_when_backtest_selects_it():
    fake_results = {
        7: {
            "errors": [0.10, -0.10, 0.12],
            "naive_errors": [0.01, -0.01, 0.02],
            "trailing_vols": [0.01, 0.02, 0.03],
        },
    }
    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"] * 100, [0.9] * 100),
    ), patch(
        "app.prediction.jobs.get_macro_rate_series", return_value=[]
    ), patch(
        "app.prediction.jobs.get_series_history", return_value=[]
    ), patch(
        "app.prediction.jobs.run_backtest", return_value=fake_results
    ), patch("app.prediction.jobs.upsert_backtest_stats") as mock_upsert:
        run_backtest_job()

    rows = mock_upsert.call_args[0][0]
    assert rows[0]["model_selected"] == "naive"


def test_run_backtest_job_aligns_and_passes_interest_rate_factor():
    captured = {}

    def fake_run_backtest(rates, horizons, factors=None):
        captured["factors"] = factors
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
        "app.prediction.jobs.get_series_history", return_value=[]
    ), patch(
        "app.prediction.jobs.run_backtest", side_effect=fake_run_backtest
    ), patch("app.prediction.jobs.upsert_backtest_stats"):
        run_backtest_job()

    assert captured["factors"]["interest_rate"] == [0.04, 0.04]  # 0.05 - 0.01, forward-filled
    # The other three factors are present (all-None, since get_series_history
    # was mocked to return no observations) rather than silently omitted.
    assert set(captured["factors"].keys()) == {"interest_rate", "cpi", "gdp", "current_account"}
    assert captured["factors"]["cpi"] == [None, None]


def test_run_backtest_job_builds_a_separate_factor_per_fundamental():
    captured = {}

    def fake_run_backtest(rates, horizons, factors=None):
        captured["factors"] = factors
        return {h: {"errors": [], "trailing_vols": []} for h in horizons}

    def fake_series_history(table, code):
        # distinct values per table so each factor is independently verifiable
        base = {"macro_cpi": 1.0, "macro_gdp": 2.0, "macro_current_account": 3.0}[table]
        return [("2020-01-01", base + (0.1 if code == "EUR" else 0.0))]

    with patch(
        "app.prediction.jobs.get_active_currencies", return_value=["USD", "EUR"]
    ), patch(
        "app.prediction.jobs.get_rate_series",
        return_value=(["2020-01-01"], [0.9]),
    ), patch(
        "app.prediction.jobs.get_macro_rate_series", return_value=[]
    ), patch(
        "app.prediction.jobs.get_series_history", side_effect=fake_series_history
    ), patch(
        "app.prediction.jobs.run_backtest", side_effect=fake_run_backtest
    ), patch("app.prediction.jobs.upsert_backtest_stats"):
        run_backtest_job()

    assert captured["factors"]["cpi"][0] == pytest.approx(0.1)
    assert captured["factors"]["gdp"][0] == pytest.approx(0.1)
    assert captured["factors"]["current_account"][0] == pytest.approx(0.1)


def test_backtest_and_forecast_regression_contract_are_compatible():
    """Integration check: the dict run_backtest_job would write to
    backtest_stats (built from a REAL summarize() call, not a mock) and
    the dict run_forecast reads back via get_backtest_stats must be the
    same shape, and a real fitted regression must genuinely be picked up
    and applied -- not just individually plausible in each function's
    own isolated unit tests.
    """
    import random

    random.seed(42)
    differentials = [i * 0.2 - 2.0 for i in range(30)]
    errors = [0.004 * d - 0.01 + random.uniform(-0.002, 0.002) for d in differentials]
    samples = {
        "errors": errors,
        "trailing_vols": [0.01] * 30,
        "factors": {"interest_rate": differentials},
    }
    summary = summarize(samples)
    assert summary["regression_factor"] == "interest_rate"  # sanity: fixture actually fits

    stats_dict_shape = {
        "error_lower_pct": summary["error_lower_pct"],
        "error_upper_pct": summary["error_upper_pct"],
        "volatility_p90": summary["volatility_p90"],
        "regression_factor": summary["regression_factor"],
        "regression_slope": summary["regression_slope"],
        "regression_intercept": summary["regression_intercept"],
    }

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
        "app.prediction.jobs.get_backtest_stats", return_value=stats_dict_shape
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate",
        side_effect=lambda code: 0.06 if code == "EUR" else 0.01,  # differential = 0.05
    ), patch(
        "app.prediction.jobs.get_latest_series_value", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    expected_predicted = 0.91 * (
        1 + (summary["regression_slope"] * 0.05 + summary["regression_intercept"])
    )
    assert rows[0]["predicted_rate"] == expected_predicted


def test_run_forecast_skips_adjustment_when_multiplier_is_non_positive():
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
            "regression_factor": "interest_rate",
            "regression_slope": -100.0,  # engineered to force a non-positive multiplier
            "regression_intercept": -0.01,
        },
    ), patch(
        "app.prediction.jobs.get_latest_macro_rate",
        side_effect=lambda code: 0.06 if code == "EUR" else 0.01,  # differential = 0.05
    ), patch(
        "app.prediction.jobs.get_latest_series_value", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment", return_value=None
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    assert rows[0]["predicted_rate"] == 0.91  # unadjusted -- multiplier would've been negative


def test_run_forecast_flags_low_confidence_on_news_shock_even_with_normal_volatility():
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
    ), patch(
        "app.prediction.jobs.get_latest_series_value", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment",
        return_value={"score": -0.85, "summary": "Major shock event."},
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    assert all(r["confidence"] == "low" for r in rows)  # 0.01 vol is normal, but |-0.85| >= 0.7


def test_run_forecast_stays_normal_confidence_for_mild_sentiment():
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
    ), patch(
        "app.prediction.jobs.get_latest_series_value", return_value=None
    ), patch(
        "app.prediction.jobs.get_latest_news_sentiment",
        return_value={"score": 0.2, "summary": "Routine coverage."},
    ), patch("app.prediction.jobs.insert_predictions") as mock_insert:
        run_forecast()

    rows = mock_insert.call_args[0][0]
    assert all(r["confidence"] == "normal" for r in rows)  # |0.2| < 0.7, volatility also normal
