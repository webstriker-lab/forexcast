from unittest.mock import patch

from app.recommendations.cli import main


def test_recommendations_mode_calls_run_recommendations():
    with patch(
        "app.recommendations.cli.run_recommendations", return_value=58
    ) as mock_recs, patch("app.recommendations.cli.run_alert_evaluation") as mock_alerts:
        main(["--mode", "recommendations"])

    mock_recs.assert_called_once()
    mock_alerts.assert_not_called()


def test_alerts_mode_calls_run_alert_evaluation():
    with patch("app.recommendations.cli.run_recommendations") as mock_recs, patch(
        "app.recommendations.cli.run_alert_evaluation", return_value=2
    ) as mock_alerts:
        main(["--mode", "alerts"])

    mock_alerts.assert_called_once()
    mock_recs.assert_not_called()
