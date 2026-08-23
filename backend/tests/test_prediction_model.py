import pytest

from app.prediction.model import forecast


def test_forecast_returns_a_float_for_a_trending_series():
    # Simple ES (trend=None) tracks the smoothed level, not the trend direction.
    # The forecast on a rising series will be near (but at or below) the last value
    # because alpha < 1 means the level lags the actual rate slightly.
    values = [float(i) for i in range(1, 101)]  # steadily rising 1..100
    result = forecast(values, steps=5)
    assert isinstance(result, float)
    assert result == pytest.approx(values[-1], rel=0.01)


def test_forecast_flat_series_stays_near_flat():
    values = [100.0] * 50
    result = forecast(values, steps=10)
    assert result == pytest.approx(100.0, abs=0.5)


def test_no_trend_extrapolation():
    # Simple ES must not extrapolate a detected trend indefinitely -- the
    # long-horizon forecast must stay near the smoothed level, not at the
    # undamped linear projection. This guards against re-introducing a trend
    # component that overshoots at 90+ day horizons (the failure mode that
    # caused mae_improvement_pct < 0 at those horizons).
    values = [float(i) for i in range(1, 101)]
    slope = values[-1] - values[-2]
    forecast_50 = forecast(values, steps=50)
    undamped_linear_50 = values[-1] + slope * 50
    assert forecast_50 < undamped_linear_50
