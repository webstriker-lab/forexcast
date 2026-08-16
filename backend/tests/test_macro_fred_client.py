from unittest.mock import MagicMock, patch

from app.macro.fred_client import fetch_observations


def test_fetch_observations_returns_date_value_pairs():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "observations": [
            {"date": "2020-01-01", "value": "0.75"},
            {"date": "2020-02-01", "value": "0.80"},
        ]
    }
    with patch(
        "app.macro.fred_client.httpx.get", return_value=mock_response
    ) as mock_get:
        result = fetch_observations("IR3TIB01USM156N")

    assert result == [("2020-01-01", 0.75), ("2020-02-01", 0.80)]
    args, kwargs = mock_get.call_args
    assert args[0] == "https://api.stlouisfed.org/fred/series/observations"
    assert kwargs["params"]["series_id"] == "IR3TIB01USM156N"
    assert kwargs["params"]["api_key"] == "test-fred-key"
    assert kwargs["params"]["file_type"] == "json"


def test_fetch_observations_skips_missing_value_placeholder():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "observations": [
            {"date": "2020-01-01", "value": "0.75"},
            {"date": "2020-02-01", "value": "."},
        ]
    }
    with patch("app.macro.fred_client.httpx.get", return_value=mock_response):
        result = fetch_observations("IR3TIB01USM156N")

    assert result == [("2020-01-01", 0.75)]


def test_fetch_observations_returns_none_for_unrecognized_series():
    mock_response = MagicMock()
    mock_response.status_code = 400
    with patch("app.macro.fred_client.httpx.get", return_value=mock_response):
        result = fetch_observations("NOT_A_REAL_SERIES")

    assert result is None


def test_fetch_observations_returns_none_for_empty_observations():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"observations": []}
    with patch("app.macro.fred_client.httpx.get", return_value=mock_response):
        result = fetch_observations("IR3TIB01XXM156N")

    assert result is None


def test_fetch_observations_propagates_server_errors():
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=mock_response
    )
    with patch("app.macro.fred_client.httpx.get", return_value=mock_response):
        try:
            fetch_observations("IR3TIB01USM156N")
            assert False, "expected HTTPStatusError to propagate"
        except httpx.HTTPStatusError:
            pass
