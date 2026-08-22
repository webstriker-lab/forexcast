from statsmodels.tsa.holtwinters import ExponentialSmoothing


def naive_forecast(values: list[float], steps: int) -> float:
    """Persistence / random-walk baseline: "assume the rate doesn't
    change." `steps` is unused -- accepted only so callers can treat this
    and forecast() interchangeably.

    This is the standard benchmark in FX forecasting, and a famously hard
    one to beat: Meese & Rogoff (1983) showed structural exchange-rate
    models fail to outperform it out of sample, a result that has held up
    remarkably well since. app.prediction.backtest picks between this and
    forecast() per (currency, horizon) based on which has actually had
    the lower backtested error -- there's no guarantee the more complex
    model earns its keep for any given pair.
    """
    return values[-1]


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
