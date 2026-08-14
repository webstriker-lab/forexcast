from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.ingestion.supabase_rest import get_active_currencies, get_usd_rate, upsert_rates


def test_get_active_currencies_returns_sorted_codes():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"code": "USD"}, {"code": "EUR"}, {"code": "AUD"}]
    mock_response.raise_for_status.return_value = None
    with patch("app.ingestion.supabase_rest.httpx.get", return_value=mock_response) as mock_get:
        result = get_active_currencies()

    assert result == ["AUD", "EUR", "USD"]
    args, kwargs = mock_get.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/currencies"
    assert kwargs["params"] == {"select": "code", "is_active": "eq.true"}
    assert kwargs["headers"]["apikey"] == "test-service-key"


def test_upsert_rates_sends_one_batch_when_under_batch_size():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [{"base_code": "USD", "quote_code": "EUR", "rate": 0.867, "as_of": "2026-08-13"}]
    with patch("app.ingestion.supabase_rest.httpx.post", return_value=mock_response) as mock_post:
        upsert_rates(rows)

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/rates_cache"
    assert kwargs["params"] == {"on_conflict": "base_code,quote_code,as_of"}
    assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates"
    assert kwargs["json"] == rows


def test_upsert_rates_batches_large_row_sets():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {"base_code": "USD", "quote_code": "EUR", "rate": 0.867, "as_of": f"2026-01-{i:02d}"}
        for i in range(1, 11)
    ]
    with patch("app.ingestion.supabase_rest.httpx.post", return_value=mock_response) as mock_post:
        with patch("app.ingestion.supabase_rest.BATCH_SIZE", 4):
            upsert_rates(rows)

    assert mock_post.call_count == 3
    sent_row_counts = [len(call.kwargs["json"]) for call in mock_post.call_args_list]
    assert sent_row_counts == [4, 4, 2]


def test_get_usd_rate_for_usd_returns_one_without_a_request():
    with patch("app.ingestion.supabase_rest.httpx.get") as mock_get:
        result = get_usd_rate("2026-08-13", "USD")

    assert result == 1.0
    mock_get.assert_not_called()


def test_get_usd_rate_returns_value_when_found():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"rate": 0.867}]
    mock_response.raise_for_status.return_value = None
    with patch("app.ingestion.supabase_rest.httpx.get", return_value=mock_response) as mock_get:
        result = get_usd_rate("2026-08-13", "EUR")

    assert result == 0.867
    args, kwargs = mock_get.call_args
    assert kwargs["params"] == {
        "select": "rate",
        "base_code": "eq.USD",
        "quote_code": "eq.EUR",
        "as_of": "eq.2026-08-13",
    }


def test_get_usd_rate_returns_none_when_not_found():
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None
    with patch("app.ingestion.supabase_rest.httpx.get", return_value=mock_response):
        result = get_usd_rate("2026-08-13", "EUR")

    assert result is None


def test_upsert_rates_raises_when_response_errors():
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "error", request=MagicMock(), response=MagicMock()
    )
    rows = [{"base_code": "USD", "quote_code": "EUR", "rate": 0.867, "as_of": "2026-08-13"}]
    with patch("app.ingestion.supabase_rest.httpx.post", return_value=mock_response):
        with pytest.raises(httpx.HTTPStatusError):
            upsert_rates(rows)
