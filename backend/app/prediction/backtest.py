from app.prediction.horizons import trading_day_steps
from app.prediction.model import forecast
from app.prediction.stats import percentile, realized_volatility

ORIGIN_SPACING = 30  # trading days between backtest origins
MIN_HISTORY = 60  # minimum trading days of lead-in before the first origin


def run_backtest(rates: list[float], horizons: list[int]) -> dict[int, dict]:
    """Rolling-origin backtest for one currency's USD-pivot rate series
    (`rates`, ordered oldest to newest). For each horizon, returns the raw
    forecast-error and trailing-volatility samples collected across every
    usable origin -- summarize() turns these into the stats actually
    stored in backtest_stats.

    Origins are spaced ORIGIN_SPACING trading days apart, starting after
    MIN_HISTORY days of lead-in so every fit has a reasonable amount of
    data. An origin only contributes a sample for a given horizon if
    enough future data exists to know the real outcome -- this is why
    longer horizons end up with fewer usable samples than shorter ones
    (see design spec Sec 5).
    """
    n = len(rates)
    results: dict[int, dict] = {h: {"errors": [], "trailing_vols": []} for h in horizons}

    for origin in range(MIN_HISTORY, n, ORIGIN_SPACING):
        history = rates[: origin + 1]
        trailing_vol = realized_volatility(rates, origin + 1)
        for horizon_days in horizons:
            steps = trading_day_steps(horizon_days)
            target_index = origin + steps
            if target_index >= n:
                continue
            predicted = forecast(history, steps)
            actual = rates[target_index]
            results[horizon_days]["errors"].append(actual - predicted)
            results[horizon_days]["trailing_vols"].append(trailing_vol)

    return results


def summarize(samples: dict) -> dict:
    """Turns one horizon's raw backtest samples into the stats stored in
    backtest_stats: empirical 10th/90th percentile forecast error (added
    to a fresh point forecast to build lower_bound/upper_bound), and the
    90th percentile of historically observed trailing volatility (the
    threshold today's live volatility is compared against for the
    confidence flag).
    """
    errors = sorted(samples["errors"])
    vols = sorted(samples["trailing_vols"])
    return {
        "error_lower_pct": percentile(errors, 10),
        "error_upper_pct": percentile(errors, 90),
        "volatility_p90": percentile(vols, 90),
        "sample_count": len(errors),
    }
