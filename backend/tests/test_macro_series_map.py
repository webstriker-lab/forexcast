from app.macro.series_map import FRED_SERIES


def test_fred_series_is_nonempty():
    assert len(FRED_SERIES) > 0


def test_fred_series_keys_and_values_are_strings():
    for currency_code, series_id in FRED_SERIES.items():
        assert isinstance(currency_code, str) and len(currency_code) == 3
        assert isinstance(series_id, str) and len(series_id) > 0


def test_usd_has_a_mapped_series():
    # USD's own rate is required for every differential (foreign - USD);
    # if USD itself has no confirmed series, the whole regression layer
    # can never activate for any currency.
    assert "USD" in FRED_SERIES
