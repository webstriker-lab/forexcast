def trading_day_steps(horizon_days: int) -> int:
    """Converts a calendar-day horizon into the trading-day step count to
    actually forecast, since rates_cache only contains trading days
    (weekends and ECB holidays are absent). Must be used identically
    wherever a horizon becomes a forecast step count -- app.prediction
    .backtest and app.prediction.jobs both import this rather than
    redefining the conversion, or the backtest's confidence bands would
    stop describing what's actually being predicted.
    """
    return round(horizon_days * 5 / 7)
