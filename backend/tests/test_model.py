from app.prediction.model import naive_forecast


def test_naive_forecast_returns_last_value_regardless_of_steps():
    assert naive_forecast([1.0, 2.0, 3.0], steps=7) == 3.0
    assert naive_forecast([1.0, 2.0, 3.0], steps=365) == 3.0
