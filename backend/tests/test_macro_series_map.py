import pytest

from app.macro.series_map import CPI_SERIES, CURRENT_ACCOUNT_SERIES, FRED_SERIES, GDP_SERIES

ALL_MAPS = [FRED_SERIES, CPI_SERIES, GDP_SERIES, CURRENT_ACCOUNT_SERIES]


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


@pytest.mark.parametrize("series_map", ALL_MAPS)
def test_all_series_maps_are_nonempty_with_string_keys_and_values(series_map):
    assert len(series_map) > 0
    for currency_code, series_id in series_map.items():
        assert isinstance(currency_code, str) and len(currency_code) == 3
        assert isinstance(series_id, str) and len(series_id) > 0


@pytest.mark.parametrize("series_map", [CPI_SERIES, GDP_SERIES, CURRENT_ACCOUNT_SERIES])
def test_usd_has_a_mapped_series_for_every_fundamental(series_map):
    # Same reasoning as FRED_SERIES: USD anchors every differential.
    assert "USD" in series_map


def test_fundamentals_coverage_counts_match_live_verification():
    # Locks in the counts from the live-FRED-API verification pass done
    # during implementation, so a future edit to these maps has to
    # deliberately update this test rather than silently drift from what
    # was actually confirmed.
    assert len(CPI_SERIES) == 24
    assert len(GDP_SERIES) == 23
    assert len(CURRENT_ACCOUNT_SERIES) == 24


def test_currencies_with_no_confirmed_series_of_any_kind_stay_excluded():
    # MYR, PHP, RON, THB, SGD, HKD had no usable series for CPI, GDP, or
    # current account when verified live -- if a future edit adds one of
    # these back in without re-verifying, this test forces a second look.
    always_excluded = {"MYR", "PHP", "RON", "THB", "SGD", "HKD"}
    for series_map in [CPI_SERIES, GDP_SERIES, CURRENT_ACCOUNT_SERIES]:
        assert not (always_excluded & series_map.keys())


def test_cny_has_no_gdp_series_despite_having_the_others():
    # A specifically-verified gap worth locking in: CNY has confirmed
    # CPI and current-account coverage but no confirmed GDP-growth series.
    assert "CNY" in CPI_SERIES
    assert "CNY" in CURRENT_ACCOUNT_SERIES
    assert "CNY" not in GDP_SERIES
