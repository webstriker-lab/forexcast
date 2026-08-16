# backend/app/prediction/jobs.py
import logging

from app.ingestion.supabase_rest import get_active_currencies
from app.macro.align import align_as_of
from app.macro.supabase_rest import get_latest_macro_rate, get_macro_rate_series
from app.prediction.backtest import run_backtest, summarize
from app.prediction.horizons import trading_day_steps
from app.prediction.model import forecast
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


def _predictable_currencies() -> list[str]:
    return [code for code in get_active_currencies() if code != PIVOT]


def run_forecast() -> int:
    """Daily job: for every USD-quoted currency, fit today's model and
    forecast each horizon, building a confidence band from that pair's
    most recent backtest_stats and flagging low-confidence when current
    volatility exceeds its own historical 90th percentile. A (currency,
    horizon) with no backtest_stats yet (e.g. before the first weekly
    backtest has run) is skipped for that row only, not treated as an
    error.

    When backtest_stats has a fitted regression for a (currency, horizon)
    AND today's current interest-rate differential is available, the
    baseline point forecast is adjusted by that regression before the
    confidence band is applied -- otherwise the baseline is used exactly
    as in 2a.
    """
    currencies = _predictable_currencies()
    usd_rate = get_latest_macro_rate(PIVOT)
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
        current_differential = (
            foreign_rate - usd_rate
            if foreign_rate is not None and usd_rate is not None
            else None
        )

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
            predicted_rate = forecast(rates, steps)
            if stats["regression_slope"] is not None and current_differential is not None:
                multiplier = 1 + (
                    stats["regression_slope"] * current_differential
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
            confidence = "low" if current_vol > stats["volatility_p90"] else "normal"
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

    Also fits an interest-rate-differential regression per (currency,
    horizon) when macro_rates has coverage: the currency's and USD's
    interest-rate histories are each forward-filled onto the rate
    series' own dates (app.macro.align.align_as_of), then subtracted to
    build the differential series run_backtest uses. A currency with no
    macro coverage at all gets an all-None differential array, which
    flows through to summarize() as "no regression fit" -- identical to
    2a's behavior for that currency.
    """
    rows = []
    usd_observations = get_macro_rate_series(PIVOT)
    for quote_code in _predictable_currencies():
        dates, rates = get_rate_series(quote_code)

        foreign_observations = get_macro_rate_series(quote_code)
        usd_aligned = align_as_of(dates, usd_observations)
        foreign_aligned = align_as_of(dates, foreign_observations)
        differentials = [
            (f - u) if f is not None and u is not None else None
            for f, u in zip(foreign_aligned, usd_aligned)
        ]

        results = run_backtest(rates, HORIZONS, differentials=differentials)
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
                    "error_lower_pct": summary["error_lower_pct"],
                    "error_upper_pct": summary["error_upper_pct"],
                    "volatility_p90": summary["volatility_p90"],
                    "sample_count": summary["sample_count"],
                    "regression_slope": summary["regression_slope"],
                    "regression_intercept": summary["regression_intercept"],
                }
            )
    upsert_backtest_stats(rows)
    return len(rows)
