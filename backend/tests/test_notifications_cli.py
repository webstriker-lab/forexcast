# backend/tests/test_notifications_cli.py
from unittest.mock import patch

from app.notifications.cli import main


def test_main_calls_run_notifications():
    with patch(
        "app.notifications.cli.run_notifications", return_value={"linked": 1, "sent": 2}
    ) as mock_run:
        main()

    mock_run.assert_called_once()


def test_main_propagates_errors():
    with patch(
        "app.notifications.cli.run_notifications", side_effect=RuntimeError("boom")
    ):
        try:
            main()
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass
