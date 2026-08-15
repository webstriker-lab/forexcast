import pytest

from app.prediction.stats import percentile, realized_volatility


def test_percentile_linear_interpolation():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(values, 0) == 1.0
    assert percentile(values, 100) == 5.0
    assert percentile(values, 50) == 3.0


def test_percentile_raises_on_empty_list():
    with pytest.raises(ValueError):
        percentile([], 50)


def test_realized_volatility_zero_for_constant_series():
    rates = [100.0] * 40
    assert realized_volatility(rates, 40) == 0.0


def test_realized_volatility_positive_for_varying_series():
    rates = [100.0, 101.0, 99.0, 102.0, 98.0] * 10
    assert realized_volatility(rates, len(rates)) > 0.0


def test_realized_volatility_uses_only_trailing_window():
    # Wild values before the trailing window, flat values inside it --
    # volatility must reflect only the flat trailing window.
    rates = [1000.0, 1.0, 1000.0, 1.0] + [100.0] * 30
    result = realized_volatility(rates, len(rates), window=30)
    assert result == 0.0
