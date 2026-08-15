from app.ingestion.supabase_rest import get_active_currencies
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
    """
    rows = []
    for quote_code in _predictable_currencies():
        _dates, rates = get_rate_series(quote_code)
        if len(rates) < 2:
            continue
        current_vol = realized_volatility(rates, len(rates))
        for horizon_days in HORIZONS:
            stats = get_backtest_stats(quote_code, horizon_days)
            if stats is None:
                continue
            steps = trading_day_steps(horizon_days)
            predicted_rate = forecast(rates, steps)
            confidence = "low" if current_vol > stats["volatility_p90"] else "normal"
            rows.append(
                {
                    "base_code": PIVOT,
                    "quote_code": quote_code,
                    "horizon_days": horizon_days,
                    "predicted_rate": predicted_rate,
                    "lower_bound": predicted_rate + stats["error_lower_pct"],
                    "upper_bound": predicted_rate + stats["error_upper_pct"],
                    "confidence": confidence,
                }
            )
    insert_predictions(rows)
    return len(rows)


def run_backtest_job() -> int:
    """Weekly job: re-runs the rolling-origin backtest for every USD-quoted
    currency and refreshes backtest_stats. A (currency, horizon) with no
    usable backtest samples is skipped for that row only.
    """
    rows = []
    for quote_code in _predictable_currencies():
        _dates, rates = get_rate_series(quote_code)
        results = run_backtest(rates, HORIZONS)
        for horizon_days, samples in results.items():
            if not samples["errors"]:
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
                }
            )
    upsert_backtest_stats(rows)
    return len(rows)
