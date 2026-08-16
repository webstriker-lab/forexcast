from unittest.mock import MagicMock, patch

from app.macro.supabase_rest import (
    get_latest_macro_rate,
    get_macro_rate_series,
    upsert_macro_rates,
)


def test_upsert_macro_rates_posts_with_merge_duplicates():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    rows = [
        {"currency_code": "EUR", "as_of": "2020-01-01", "series_id": "IR3TIB01EZM156N", "rate": 0.5}
    ]
    with patch(
        "app.macro.supabase_rest.httpx.post", return_value=mock_response
    ) as mock_post:
        upsert_macro_rates(rows)

    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.supabase.co/rest/v1/macro_rates"
    assert kwargs["params"] == {"on_conflict": "currency_code,as_of"}
    assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates"
    assert kwargs["json"] == rows


def test_get_macro_rate_series_returns_date_rate_tuples():
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"as_of": "2020-01-01", "rate": 0.5},
        {"as_of": "2020-02-01", "rate": 0.6},
    ]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.macro.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_macro_rate_series("EUR")

    assert result == [("2020-01-01", 0.5), ("2020-02-01", 0.6)]
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["currency_code"] == "eq.EUR"
    assert kwargs["params"]["order"] == "as_of.asc"


def test_get_macro_rate_series_paginates():
    page_size = 1000
    first_page = [
        {"as_of": f"2020-{(i % 12) + 1:02d}-01", "rate": float(i)} for i in range(page_size)
    ]
    second_page = [{"as_of": "2099-01-01", "rate": 9.9}]
    first_response = MagicMock()
    first_response.json.return_value = first_page
    first_response.raise_for_status.return_value = None
    second_response = MagicMock()
    second_response.json.return_value = second_page
    second_response.raise_for_status.return_value = None
    with patch(
        "app.macro.supabase_rest.httpx.get",
        side_effect=[first_response, second_response],
    ) as mock_get:
        result = get_macro_rate_series("EUR")

    assert len(result) == page_size + 1
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[1].kwargs["params"]["offset"] == page_size


def test_get_latest_macro_rate_returns_most_recent_value():
    mock_response = MagicMock()
    mock_response.json.return_value = [{"rate": 0.75}]
    mock_response.raise_for_status.return_value = None
    with patch(
        "app.macro.supabase_rest.httpx.get", return_value=mock_response
    ) as mock_get:
        result = get_latest_macro_rate("EUR")

    assert result == 0.75
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["order"] == "as_of.desc"
    assert kwargs["params"]["limit"] == 1


def test_get_latest_macro_rate_returns_none_when_no_data():
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None
    with patch("app.macro.supabase_rest.httpx.get", return_value=mock_response):
        result = get_latest_macro_rate("EUR")

    assert result is None
