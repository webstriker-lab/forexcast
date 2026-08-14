from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.ingestion.frankfurter import fetch_latest, fetch_range


def test_fetch_latest_calls_correct_endpoint_and_returns_json():
    mock_response = MagicMock()
    mock_response.json.return_value = {"date": "2026-08-13", "rates": {"EUR": 0.867}}
    mock_response.raise_for_status.return_value = None
    with patch("app.ingestion.frankfurter.httpx.get", return_value=mock_response) as mock_get:
        result = fetch_latest("USD", ["EUR", "GBP"])

    assert result == {"date": "2026-08-13", "rates": {"EUR": 0.867}}
    mock_get.assert_called_once_with(
        "https://api.frankfurter.dev/v1/latest",
        params={"base": "USD", "symbols": "EUR,GBP"},
        timeout=30.0,
    )


def test_fetch_latest_raises_on_http_error():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "error", request=MagicMock(), response=MagicMock()
    )
    with patch("app.ingestion.frankfurter.httpx.get", return_value=mock_response):
        with pytest.raises(httpx.HTTPStatusError):
            fetch_latest("USD", ["EUR"])


def test_fetch_range_calls_correct_endpoint_and_returns_json():
    mock_response = MagicMock()
    mock_response.json.return_value = {"rates": {"2026-08-01": {"EUR": 0.86}}}
    mock_response.raise_for_status.return_value = None
    with patch("app.ingestion.frankfurter.httpx.get", return_value=mock_response) as mock_get:
        result = fetch_range("USD", ["EUR"], "2026-01-01", "2026-08-01")

    assert result == {"rates": {"2026-08-01": {"EUR": 0.86}}}
    mock_get.assert_called_once_with(
        "https://api.frankfurter.dev/v1/2026-01-01..2026-08-01",
        params={"base": "USD", "symbols": "EUR"},
        timeout=60.0,
    )
