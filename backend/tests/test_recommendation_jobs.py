from unittest.mock import patch

import pytest

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


from app.recommendations.jobs import run_alert_evaluation


def test_run_alert_evaluation_fires_and_deactivates_threshold_alert():
    alerts = [
        {
            "id": "alert-1",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "threshold",
            "threshold_rate": 85.0,
            "direction": "above",
        }
    ]
    with patch("app.recommendations.jobs.get_active_alerts", return_value=alerts), patch(
        "app.recommendations.jobs.get_current_rate", return_value=86.0
    ), patch("app.recommendations.jobs.record_alert_event") as mock_record, patch(
        "app.recommendations.jobs.deactivate_alert"
    ) as mock_deactivate:
        count = run_alert_evaluation()

    assert count == 1
    mock_record.assert_called_once()
    mock_deactivate.assert_called_once_with("alert-1")


def test_run_alert_evaluation_does_not_fire_uncrossed_threshold():
    alerts = [
        {
            "id": "alert-1",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "threshold",
            "threshold_rate": 85.0,
            "direction": "above",
        }
    ]
    with patch("app.recommendations.jobs.get_active_alerts", return_value=alerts), patch(
        "app.recommendations.jobs.get_current_rate", return_value=80.0
    ), patch("app.recommendations.jobs.record_alert_event") as mock_record, patch(
        "app.recommendations.jobs.deactivate_alert"
    ) as mock_deactivate:
        count = run_alert_evaluation()

    assert count == 0
    mock_record.assert_not_called()
    mock_deactivate.assert_not_called()


def test_run_alert_evaluation_raises_when_alerts_currency_has_no_current_rate():
    # This app's currency universe is fixed and known (unlike a genuinely
    # expected gap, e.g. a new currency awaiting its first backtest) -- a
    # missing current rate for an alert's currency is unexpected and must
    # fail loudly, not be silently skipped.
    alerts = [
        {
            "id": "alert-1",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "threshold",
            "threshold_rate": 85.0,
            "direction": "above",
        }
    ]
    with patch("app.recommendations.jobs.get_active_alerts", return_value=alerts), patch(
        "app.recommendations.jobs.get_current_rate", return_value=None
    ):
        with pytest.raises(ValueError, match="INR"):
            run_alert_evaluation()


def test_run_alert_evaluation_fires_recommendation_change_without_deactivating():
    alerts = [
        {
            "id": "alert-2",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "recommendation_change",
            "threshold_rate": None,
            "direction": None,
        }
    ]
    with patch("app.recommendations.jobs.get_active_alerts", return_value=alerts), patch(
        "app.recommendations.jobs.get_latest_two_recommendations",
        return_value=["act_now", "wait"],
    ), patch("app.recommendations.jobs.record_alert_event") as mock_record, patch(
        "app.recommendations.jobs.deactivate_alert"
    ) as mock_deactivate:
        count = run_alert_evaluation()

    assert count == 1
    mock_record.assert_called_once()
    mock_deactivate.assert_not_called()


def test_run_alert_evaluation_skips_unchanged_recommendation():
    alerts = [
        {
            "id": "alert-2",
            "base_code": "USD",
            "quote_code": "INR",
            "alert_type": "recommendation_change",
            "threshold_rate": None,
            "direction": None,
        }
    ]
    with patch("app.recommendations.jobs.get_active_alerts", return_value=alerts), patch(
        "app.recommendations.jobs.get_latest_two_recommendations",
        return_value=["wait", "wait"],
    ), patch("app.recommendations.jobs.record_alert_event") as mock_record:
        count = run_alert_evaluation()

    assert count == 0
    mock_record.assert_not_called()
