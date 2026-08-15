import pytest

from app.prediction.model import forecast


def test_forecast_returns_a_float_for_a_trending_series():
    values = [float(i) for i in range(1, 101)]  # steadily rising 1..100
    result = forecast(values, steps=5)
    assert isinstance(result, float)
    assert result > values[-1]


def test_forecast_flat_series_stays_near_flat():
    values = [100.0] * 50
    result = forecast(values, steps=10)
    assert result == pytest.approx(100.0, abs=0.5)


def test_damped_trend_does_not_extrapolate_linearly_forever():
    # A rising series' 50-step-ahead forecast should grow by less than a
    # *linear* (undamped) extrapolation of the same per-step slope would --
    # damping caps how far a detected trend is allowed to compound. This is
    # exactly the "falsely precise" failure mode the product spec warns
    # against at long horizons.
    values = [float(i) for i in range(1, 101)]
    slope = values[-1] - values[-2]
    forecast_50 = forecast(values, steps=50)
    undamped_linear_50 = values[-1] + slope * 50
    assert forecast_50 < undamped_linear_50
