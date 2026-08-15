from app.prediction.horizons import trading_day_steps


def test_trading_day_steps_for_each_product_horizon():
    # Verified by hand and by running the exact formula: round(days * 5/7).
    assert trading_day_steps(7) == 5
    assert trading_day_steps(30) == 21
    assert trading_day_steps(90) == 64
    assert trading_day_steps(365) == 261
