from scipy.stats import linregress

from app.prediction.horizons import trading_day_steps
from app.prediction.model import forecast
from app.prediction.stats import percentile, realized_volatility

ORIGIN_SPACING = 30  # trading days between backtest origins
MIN_HISTORY = 60  # minimum trading days of lead-in before the first origin


def run_backtest(
    rates: list[float],
    horizons: list[int],
    differentials: list[float | None] | None = None,
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

    `differentials`, when given, is parallel to `rates` (same length,
    oldest to newest) -- the interest-rate differential known as of each
    date, or None where macro coverage doesn't exist yet for that date.
    When provided, each horizon's results additionally collect a
    `"differentials"` list in lock-step with `"errors"` (same length,
    same order), which summarize() uses to fit a regression. Omitting
    `differentials` (the default) leaves every horizon's results
    identical in shape to the pre-2b implementation -- this is a purely
    additive extension, not a behavior change, for any caller that
    doesn't pass it.
    """
    n = len(rates)
    results: dict[int, dict] = {h: {"errors": [], "trailing_vols": []} for h in horizons}
    if differentials is not None:
        for h in horizons:
            results[h]["differentials"] = []

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
            results[horizon_days]["errors"].append((actual - predicted) / predicted)
            results[horizon_days]["trailing_vols"].append(trailing_vol)
            if differentials is not None:
                results[horizon_days]["differentials"].append(differentials[origin])

    return results


def fit_regression(
    errors: list[float],
    differentials: list[float],
    min_samples: int = 24,
    p_threshold: float = 0.10,
) -> dict | None:
    """Fits `relative_error ~ a + b * differential` via ordinary least
    squares. Returns None -- meaning "not enough evidence this
    currency's rate differential predicts anything, don't adjust it" --
    when there are fewer than `min_samples` paired observations, or when
    the fitted slope's p-value doesn't clear `p_threshold`. `errors` and
    `differentials` must already be paired 1:1 (equal length, no None
    entries) -- callers filter out unpaired samples before calling this.
    """
    if len(errors) < min_samples:
        return None
    result = linregress(differentials, errors)
    if result.pvalue >= p_threshold:
        return None
    return {"slope": result.slope, "intercept": result.intercept}


def summarize(samples: dict) -> dict:
    """Turns one horizon's raw backtest samples into the stats stored in
    backtest_stats: empirical 10th/90th percentile forecast error (added
    to a fresh point forecast to build lower_bound/upper_bound), the 90th
    percentile of historically observed trailing volatility (the
    threshold today's live volatility is compared against for the
    confidence flag), and -- new in 2b -- a fitted interest-rate
    differential regression, when `samples` includes a `"differentials"`
    list and enough of its entries are non-None to clear fit_regression's
    quality gate.

    When a regression IS fit, error_lower_pct/error_upper_pct are
    recomputed from the POST-adjustment residuals, not the raw baseline
    errors -- otherwise the confidence band would misrepresent the
    adjusted model's real historical accuracy. An origin with no known
    differential can't be adjusted (there's nothing to apply the
    regression to), so its RAW baseline error is used as-is for that
    entry -- this matches what the daily forecast job actually does when
    today's current differential is unavailable (see
    app.prediction.jobs.run_forecast): no adjustment, baseline as-is.
    """
    errors = samples["errors"]
    diffs = samples.get("differentials")

    regression = None
    if diffs:
        paired = [(e, d) for e, d in zip(errors, diffs) if d is not None]
        if paired:
            regression = fit_regression(
                [e for e, _ in paired], [d for _, d in paired]
            )

    if regression:
        residuals = [
            e - (regression["slope"] * d + regression["intercept"]) if d is not None else e
            for e, d in zip(errors, diffs)
        ]
    else:
        residuals = errors

    return {
        "error_lower_pct": percentile(sorted(residuals), 10),
        "error_upper_pct": percentile(sorted(residuals), 90),
        "volatility_p90": percentile(sorted(samples["trailing_vols"]), 90),
        "sample_count": len(errors),
        "regression_slope": regression["slope"] if regression else None,
        "regression_intercept": regression["intercept"] if regression else None,
    }
