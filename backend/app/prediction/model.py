from statsmodels.tsa.holtwinters import ExponentialSmoothing


def forecast(values: list[float], steps: int) -> float:
    """Fits a damped additive-trend exponential smoothing model on `values`
    (ordered oldest to newest, no seasonality assumed) and returns the
    point forecast `steps` steps ahead.

    This is the sole model candidate for now. The backtest harness
    (app.prediction.backtest) and the daily job (app.prediction.jobs) both
    call this function by name rather than embedding model logic
    themselves, so adding a second candidate (e.g. ARIMA) later, and
    letting the backtest decide which wins per currency, means adding a
    function here -- not redesigning either caller.
    """
    model = ExponentialSmoothing(
        values,
        trend="add",
        damped_trend=True,
        seasonal=None,
        initialization_method="estimated",
    )
    fitted = model.fit()
    forecasts = fitted.forecast(steps)
    return float(forecasts[-1])
