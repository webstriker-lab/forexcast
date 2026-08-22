from scipy.stats import linregress

from app.prediction.horizons import trading_day_steps
from app.prediction.model import forecast, naive_forecast
from app.prediction.stats import percentile, realized_volatility

ORIGIN_SPACING = 30  # trading days between backtest origins
MIN_HISTORY = 60  # minimum trading days of lead-in before the first origin


def run_backtest(
    rates: list[float],
    horizons: list[int],
    factors: dict[str, list[float | None]] | None = None,
) -> dict[int, dict]:
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

    Each horizon's results also collects "naive_errors" -- the same
    origins scored against naive_forecast (persistence/random-walk)
    instead of forecast() -- so summarize() can pick whichever candidate
    actually had the lower backtested error for that (currency, horizon),
    rather than assuming the more complex model is better. Both
    candidates are scored against the exact same origins and actuals, so
    the comparison is paired and fair.

    `factors`, when given, maps a factor name (e.g. "interest_rate",
    "cpi", "gdp", "current_account") to a list parallel to `rates` (same
    length, oldest to newest) -- that factor's differential known as of
    each date, or None where macro coverage doesn't exist yet for that
    date. When provided, each horizon's results additionally collects a
    `"factors"` dict of {name: [...]}, each list in lock-step with
    `"errors"` (same length, same order), which summarize() uses to
    independently try fitting a regression against each factor and pick
    whichever one wins for that (currency, horizon) -- never a joint fit
    across all of them at once (see summarize()'s docstring for why).
    Omitting `factors` (the default) leaves every horizon's results
    identical in shape to the pre-existing single-factor implementation.
    """
    n = len(rates)
    results: dict[int, dict] = {
        h: {"errors": [], "naive_errors": [], "trailing_vols": []} for h in horizons
    }
    if factors is not None:
        for h in horizons:
            results[h]["factors"] = {name: [] for name in factors}

    for origin in range(MIN_HISTORY, n, ORIGIN_SPACING):
        history = rates[: origin + 1]
        trailing_vol = realized_volatility(rates, origin + 1)
        for horizon_days in horizons:
            steps = trading_day_steps(horizon_days)
            target_index = origin + steps
            if target_index >= n:
                continue
            predicted = forecast(history, steps)
            predicted_naive = naive_forecast(history, steps)
            actual = rates[target_index]
            results[horizon_days]["errors"].append((actual - predicted) / predicted)
            results[horizon_days]["naive_errors"].append((actual - predicted_naive) / predicted_naive)
            results[horizon_days]["trailing_vols"].append(trailing_vol)
            if factors is not None:
                for name, series in factors.items():
                    results[horizon_days]["factors"][name].append(series[origin])

    return results


def fit_regression(
    errors: list[float],
    differentials: list[float],
    min_samples: int = 24,
    p_threshold: float = 0.01,
) -> dict | None:
    """Fits `relative_error ~ a + b * differential` via ordinary least
    squares. Returns None -- meaning "not enough evidence this
    currency's rate differential predicts anything, don't adjust it" --
    when there are fewer than `min_samples` paired observations, or when
    the fitted slope's p-value doesn't clear `p_threshold`. `errors` and
    `differentials` must already be paired 1:1 (equal length, no None
    entries) -- callers filter out unpaired samples before calling this.

    Known limitation: this p-value assumes independent samples, but
    backtest origins are spaced ORIGIN_SPACING (30) trading days apart
    while a horizon can span many more steps than that (e.g. 261 for the
    365-day horizon) -- consecutive samples' outcome windows overlap, so
    the true effective sample size is smaller than len(errors) and this
    p-value understates the real uncertainty, especially at longer
    horizons. p_threshold is set conservatively (0.01, not the
    textbook-standard 0.05 or a looser 0.10) partly to compensate.
    """
    if len(errors) < min_samples:
        return None
    result = linregress(differentials, errors)
    if result.pvalue >= p_threshold:
        return None
    return {"slope": result.slope, "intercept": result.intercept}


def _select_model(errors: list[float], naive_errors: list[float] | None) -> str:
    """Picks whichever candidate has actually had the lower mean absolute
    error out of sample: exponential smoothing (forecast()) or naive
    persistence (naive_forecast()). FX rates are famously close to a
    random walk (Meese & Rogoff, 1983) -- there's no a priori reason to
    assume the more complex model wins for any given (currency, horizon),
    so this is decided empirically, per pair, from the same backtest
    samples used to build the confidence band.

    Ties, and the case where naive_errors wasn't collected at all (older
    callers / unit tests exercising summarize() in isolation), favor
    "exponential_smoothing" -- the historical default -- so this is a
    strictly additive capability, not a behavior change, for any caller
    that doesn't opt in by providing naive_errors.
    """
    if not naive_errors:
        return "exponential_smoothing"
    es_mae = sum(abs(e) for e in errors) / len(errors)
    naive_mae = sum(abs(e) for e in naive_errors) / len(naive_errors)
    return "naive" if naive_mae < es_mae else "exponential_smoothing"


def _select_regression(
    selected_errors: list[float], factors: dict[str, list[float | None]] | None
) -> tuple[str, dict] | None:
    """Independently tries fit_regression against each available factor
    (interest-rate differential, CPI differential, GDP-growth
    differential, current-account differential) and returns whichever
    cleared fit_regression's significance gate with the lowest resulting
    residual MAE, or None if none did.

    Deliberately never a joint multivariate fit across all factors at
    once: with only ~200-something backtest samples per horizon (and
    macro fundamentals that often move together), a joint fit risks
    overfitting far more than picking whichever single factor actually
    has demonstrated, independently-significant explanatory power for
    this specific currency and horizon.
    """
    if not factors:
        return None
    best: tuple[str, dict, float] | None = None
    for name, series in factors.items():
        paired = [(e, d) for e, d in zip(selected_errors, series) if d is not None]
        if not paired:
            continue
        regression = fit_regression([e for e, _ in paired], [d for _, d in paired])
        if regression is None:
            continue
        residuals = [e - (regression["slope"] * d + regression["intercept"]) for e, d in paired]
        mae = sum(abs(r) for r in residuals) / len(residuals)
        if best is None or mae < best[2]:
            best = (name, regression, mae)
    return (best[0], best[1]) if best else None


def summarize(samples: dict) -> dict:
    """Turns one horizon's raw backtest samples into the stats stored in
    backtest_stats: which candidate model actually wins for this
    (currency, horizon) (see _select_model), empirical 10th/90th
    percentile forecast error for the WINNING model (added to a fresh
    point forecast to build lower_bound/upper_bound), the 90th percentile
    of historically observed trailing volatility (the threshold today's
    live volatility is compared against for the confidence flag), and
    which macro factor's regression wins for this (currency, horizon)
    (see _select_regression), when `samples` includes a `"factors"` dict
    and at least one factor clears fit_regression's quality gate.

    The regression only ever adjusts exponential smoothing's residuals --
    naive_forecast has no baseline drift for a differential to correct,
    so when naive wins, no regression is fit and its raw errors are used
    as-is.

    When a regression IS fit, error_lower_pct/error_upper_pct are
    recomputed from the POST-adjustment residuals, not the raw baseline
    errors -- otherwise the confidence band would misrepresent the
    adjusted model's real historical accuracy. An origin with no known
    value for the winning factor can't be adjusted (there's nothing to
    apply the regression to), so its RAW baseline error is used as-is for
    that entry -- this matches what the daily forecast job actually does
    when today's current value for that factor is unavailable (see
    app.prediction.jobs.run_forecast): no adjustment, baseline as-is.
    """
    errors = samples["errors"]
    naive_errors = samples.get("naive_errors")
    factors = samples.get("factors")

    model_selected = _select_model(errors, naive_errors)
    selected_errors = errors if model_selected == "exponential_smoothing" else naive_errors

    regression_factor = None
    regression = None
    if factors and model_selected == "exponential_smoothing":
        picked = _select_regression(selected_errors, factors)
        if picked:
            regression_factor, regression = picked

    if regression:
        diffs = factors[regression_factor]
        residuals = [
            e - (regression["slope"] * d + regression["intercept"]) if d is not None else e
            for e, d in zip(selected_errors, diffs)
        ]
    else:
        residuals = selected_errors

    return {
        "model_selected": model_selected,
        "error_lower_pct": percentile(sorted(residuals), 10),
        "error_upper_pct": percentile(sorted(residuals), 90),
        "volatility_p90": percentile(sorted(samples["trailing_vols"]), 90),
        "sample_count": len(selected_errors),
        "regression_factor": regression_factor,
        "regression_slope": regression["slope"] if regression else None,
        "regression_intercept": regression["intercept"] if regression else None,
    }
