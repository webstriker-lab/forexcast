from unittest.mock import patch

from app.news.cli import main


def test_main_calls_run_news_sentiment():
    with patch("app.news.cli.run_news_sentiment", return_value=17) as mock_run:
        main()

    mock_run.assert_called_once()


def test_main_propagates_errors():
    with patch("app.news.cli.run_news_sentiment", side_effect=RuntimeError("boom")):
        try:
            main()
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass
