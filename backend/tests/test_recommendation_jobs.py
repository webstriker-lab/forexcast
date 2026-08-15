from unittest.mock import patch

from app.recommendations.jobs import run_recommendations

HORIZONS = [
    {"horizon_days": 7, "predicted_rate": 90.0, "lower_bound": 88.0, "upper_bound": 92.0, "confidence": "normal"},
    {"horizon_days": 30, "predicted_rate": 95.0, "lower_bound": 91.0, "upper_bound": 99.0, "confidence": "normal"},
]


def test_run_recommendations_writes_both_directions_per_currency():
    with patch(
        "app.recommendations.jobs.get_active_currencies", return_value=["USD", "INR"]
    ), patch(
        "app.recommendations.jobs.get_latest_predictions", return_value=HORIZONS
    ), patch(
        "app.recommendations.jobs.get_current_rate", return_value=85.0
    ), patch("app.recommendations.jobs.insert_recommendations") as mock_insert:
        count = run_recommendations()

    assert count == 2
    rows = mock_insert.call_args[0][0]
    forward = next(r for r in rows if r["base_code"] == "USD" and r["quote_code"] == "INR")
    reverse = next(r for r in rows if r["base_code"] == "INR" and r["quote_code"] == "USD")
    assert forward["recommendation"] == "wait"
    assert forward["reference_horizon_days"] == 30
    assert forward["current_rate"] == 85.0
    assert reverse["current_rate"] == 1 / 85.0
    assert reverse["expected_rate"] == 1 / 95.0


def test_run_recommendations_skips_currency_with_no_predictions():
    with patch(
        "app.recommendations.jobs.get_active_currencies", return_value=["USD", "INR"]
    ), patch(
        "app.recommendations.jobs.get_latest_predictions", return_value=[]
    ), patch(
        "app.recommendations.jobs.get_current_rate", return_value=85.0
    ), patch("app.recommendations.jobs.insert_recommendations") as mock_insert:
        count = run_recommendations()

    assert count == 0
    mock_insert.assert_called_once_with([])


def test_run_recommendations_skips_currency_with_no_current_rate():
    with patch(
        "app.recommendations.jobs.get_active_currencies", return_value=["USD", "INR"]
    ), patch(
        "app.recommendations.jobs.get_latest_predictions", return_value=HORIZONS
    ), patch(
        "app.recommendations.jobs.get_current_rate", return_value=None
    ), patch("app.recommendations.jobs.insert_recommendations") as mock_insert:
        count = run_recommendations()

    assert count == 0
    mock_insert.assert_called_once_with([])
