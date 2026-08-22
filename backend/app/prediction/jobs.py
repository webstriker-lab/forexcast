# backend/app/prediction/jobs.py
import logging

from app.ingestion.supabase_rest import get_active_currencies
from app.macro.align import align_as_of
from app.macro.supabase_rest import (
    get_latest_macro_rate,
    get_latest_series_value,
    get_macro_rate_series,
    get_series_history,
)
from app.news.supabase_rest import get_latest_news_sentiment
from app.prediction.backtest import run_backtest, summarize
from app.prediction.horizons import trading_day_steps
from app.prediction.model import forecast, naive_forecast
from app.prediction.stats import realized_volatility
from app.prediction.supabase_rest import (
    get_backtest_stats,
    get_rate_series,
    insert_predictions,
    upsert_backtest_stats,
)

logger = logging.getLogger(__name__)

PIVOT = "USD"
HORIZONS = [7, 30, 90, 365]

# Tables backing each non-interest-rate macro factor, keyed by the same
# factor name app.prediction.backtest._select_regression picks between
# and backtest_stats.regression_factor stores. "interest_rate" isn't
# here -- it keeps using the original macro_rates-specific accessors,
# untouched, since they predate this and there's no reason to disturb
# already-stable code for a currently-behavior-identical generalization.
FACTOR_TABLES = {
    "cpi": "macro_cpi",
    "gdp": "macro_gdp",
    "current_account": "macro_current_account",
}


def _predictable_currencies() -> list[str]:
    return [code for code in get_active_currencies() if code != PIVOT]


def _differential(
    dates: list[str],
    foreign_observations: list[tuple[str, float]],
    usd_observations: list[tuple[str, float]],
) -> list[float | None]:
    """Forward-fills both sides onto `dates` (app.macro.align.align_as_of)
    and subtracts: foreign - USD, None wherever either side is unknown as
    of that date. Shared by every macro factor (interest rate, CPI, GDP,
    current account) -- they're all just "some FRED series, foreign minus
    USD" at this layer.
    """
    foreign_aligned = align_as_of(dates, foreign_observations)
    usd_aligned = align_as_of(dates, usd_observations)
    return [
        (f - u) if f is not None and u is not None else None
        for f, u in zip(foreign_aligned, usd_aligned)
    ]


def run_forecast() -> int:
    """Daily job: for every USD-quoted currency, fit today's model and
    forecast each horizon, building a confidence band from that pair's
    most recent backtest_stats and flagging low-confidence when current
    volatility exceeds its own historical 90th percentile. A (currency,
    horizon) with no backtest_stats yet (e.g. before the first weekly
    backtest has run) is skipped for that row only, not treated as an
    error.

    When backtest_stats has a fitted regression for a (currency, horizon)
    AND today's current value for whichever macro factor won that
    regression is available, the baseline point forecast is adjusted by
    it before the confidence band is applied -- otherwise the baseline is
    used exactly as in 2a. Confidence is also flagged low when today's
    news sentiment for that currency is a shock (|score| >= 0.7),
    independent of volatility.

    The baseline itself is whichever model backtest_stats.model_selected
    says actually won the backtest for this (currency, horizon) --
    exponential smoothing (forecast()) or naive persistence
    (naive_forecast()); see app.prediction.backtest._select_model.
    Missing the key (stats from before this field existed) defaults to
    exponential smoothing, the prior behavior.

    The regression's factor -- interest rate, CPI, GDP, or current
    account -- is looked up per (currency, horizon) via
    backtest_stats.regression_factor
    (app.prediction.backtest._select_regression); today's current value
    for that specific factor is fetched, not all four, so a currency only
    pays for the macro lookups it actually needs.
    """
    currencies = _predictable_currencies()
    usd_rate = get_latest_macro_rate(PIVOT)
    usd_factor_values = {
        name: get_latest_series_value(table, PIVOT) for name, table in FACTOR_TABLES.items()
    }
    rows = []
    for quote_code in currencies:
        _dates, rates = get_rate_series(quote_code)
        if len(rates) < 2:
            logger.warning(
                "Skipping %s: insufficient rate history (%d rows)",
                quote_code,
                len(rates),
            )
            continue
        current_vol = realized_volatility(rates, len(rates))

        foreign_rate = get_latest_macro_rate(quote_code)
        current_factor_values = {
            "interest_rate": (
                foreign_rate - usd_rate
                if foreign_rate is not None and usd_rate is not None
                else None
            )
        }
        for name, table in FACTOR_TABLES.items():
            foreign_value = get_latest_series_value(table, quote_code)
            usd_value = usd_factor_values[name]
            current_factor_values[name] = (
                foreign_value - usd_value
                if foreign_value is not None and usd_value is not None
                else None
            )

        sentiment = get_latest_news_sentiment(quote_code)
        if sentiment is None:
            logger.info("No news sentiment available today for %s", quote_code)
        news_shock = sentiment is not None and abs(sentiment["score"]) >= 0.7

        for horizon_days in HORIZONS:
            stats = get_backtest_stats(quote_code, horizon_days)
            if stats is None:
                logger.info(
                    "Skipping %s horizon=%d: no backtest_stats yet",
                    quote_code,
                    horizon_days,
                )
                continue
            steps = trading_day_steps(horizon_days)
            predicted_rate = (
                naive_forecast(rates, steps)
                if stats.get("model_selected") == "naive"
                else forecast(rates, steps)
            )
            current_factor_value = current_factor_values.get(stats.get("regression_factor"))
            if stats["regression_slope"] is not None and current_factor_value is not None:
                multiplier = 1 + (
                    stats["regression_slope"] * current_factor_value
                    + stats["regression_intercept"]
                )
                if multiplier > 0:
                    predicted_rate *= multiplier
                else:
                    logger.warning(
                        "Skipping regression adjustment for %s horizon=%d: "
                        "computed multiplier %.4f is non-positive",
                        quote_code,
                        horizon_days,
                        multiplier,
                    )
            confidence = (
                "low" if (current_vol > stats["volatility_p90"] or news_shock) else "normal"
            )
            rows.append(
                {
                    "base_code": PIVOT,
                    "quote_code": quote_code,
                    "horizon_days": horizon_days,
                    "predicted_rate": predicted_rate,
                    "lower_bound": predicted_rate * (1 + stats["error_lower_pct"]),
                    "upper_bound": predicted_rate * (1 + stats["error_upper_pct"]),
                    "confidence": confidence,
                }
            )
    if not rows and currencies:
        logger.warning(
            "run_forecast produced zero prediction rows despite %d predictable "
            "currencies -- check backtest_stats is populated",
            len(currencies),
        )
    insert_predictions(rows)
    return len(rows)


def run_backtest_job() -> int:
    """Weekly job: re-runs the rolling-origin backtest for every USD-quoted
    currency and refreshes backtest_stats. A (currency, horizon) with no
    usable backtest samples is skipped for that row only.

    Also independently fits a regression against each of four macro
    factors (interest-rate, CPI, GDP-growth, and current-account
    differentials) when coverage exists: each currency's and USD's
    history for that factor is forward-filled onto the rate series' own
    dates (app.macro.align.align_as_of via _differential), then
    subtracted. run_backtest/summarize pick whichever single factor
    actually wins per (currency, horizon) -- see
    app.prediction.backtest._select_regression for why never jointly. A
    currency with no coverage for a given factor gets an all-None
    differential array for it, which just makes that factor unavailable
    to win -- identical in spirit to 2b's original single-factor "no
    regression fit" behavior, now per-factor instead of currency-wide.
    """
    rows = []
    usd_observations = {"interest_rate": get_macro_rate_series(PIVOT)}
    for name, table in FACTOR_TABLES.items():
        usd_observations[name] = get_series_history(table, PIVOT)

    for quote_code in _predictable_currencies():
        dates, rates = get_rate_series(quote_code)

        factors = {
            "interest_rate": _differential(
                dates, get_macro_rate_series(quote_code), usd_observations["interest_rate"]
            )
        }
        for name, table in FACTOR_TABLES.items():
            factors[name] = _differential(
                dates, get_series_history(table, quote_code), usd_observations[name]
            )

        results = run_backtest(rates, HORIZONS, factors=factors)
        for horizon_days, samples in results.items():
            if not samples["errors"]:
                logger.info(
                    "Skipping %s horizon=%d: no backtest samples",
                    quote_code,
                    horizon_days,
                )
                continue
            summary = summarize(samples)
            rows.append(
                {
                    "quote_code": quote_code,
                    "horizon_days": horizon_days,
                    "model_selected": summary["model_selected"],
                    "error_lower_pct": summary["error_lower_pct"],
                    "error_upper_pct": summary["error_upper_pct"],
                    "volatility_p90": summary["volatility_p90"],
                    "sample_count": summary["sample_count"],
                    "regression_factor": summary["regression_factor"],
                    "regression_slope": summary["regression_slope"],
                    "regression_intercept": summary["regression_intercept"],
                }
            )
    upsert_backtest_stats(rows)
    return len(rows)
