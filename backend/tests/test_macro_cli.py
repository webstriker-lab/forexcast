from unittest.mock import patch

from app.macro.cli import main


def test_main_calls_run_macro_ingestion():
    with patch("app.macro.cli.run_macro_ingestion", return_value=42) as mock_run:
        main()

    mock_run.assert_called_once()


def test_main_propagates_errors():
    with patch("app.macro.cli.run_macro_ingestion", side_effect=RuntimeError("boom")):
        try:
            main()
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass
