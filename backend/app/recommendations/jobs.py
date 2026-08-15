import logging

from app.ingestion.supabase_rest import get_active_currencies
from app.recommendations.alerts import recommendation_changed, threshold_crossed
from app.recommendations.engine import choose_recommendation, invert_prediction
from app.recommendations.supabase_rest import (
    deactivate_alert,
    get_active_alerts,
    get_current_rate,
    get_directed_rate,
    get_latest_predictions,
    get_latest_two_recommendations,
    insert_recommendations,
    record_alert_event,
)

logger = logging.getLogger(__name__)

PIVOT = "USD"


def _predictable_currencies() -> list[str]:
    return [code for code in get_active_currencies() if code != PIVOT]


def run_recommendations() -> int:
    """Daily job: for every USD-quoted currency, compute a recommendation
    for both directions (USD->X and X->USD) from that currency's latest
    forecast batch, and write them to `recommendations`. A currency with
    no forecast batch or no current rate yet is skipped for both
    directions.
    """
    currencies = _predictable_currencies()
    rows = []
    for quote_code in currencies:
        horizons = get_latest_predictions(quote_code)
        if not horizons:
            logger.info("Skipping %s: no prediction batch today", quote_code)
            continue
        current_rate = get_current_rate(quote_code)
        if current_rate is None:
            logger.info("Skipping %s: no current rate", quote_code)
            continue

        forward = choose_recommendation(current_rate, horizons, favorable_high=True)
        rows.append(
            {
                "base_code": PIVOT,
                "quote_code": quote_code,
                "recommendation": forward["recommendation"],
                "reference_horizon_days": forward["reference_horizon_days"],
                "current_rate": forward["current_rate"],
                "expected_rate": forward["expected_rate"],
                "lower_bound": forward["lower_bound"],
                "upper_bound": forward["upper_bound"],
            }
        )

        inverted_horizons = [
            {**h, **invert_prediction(h["predicted_rate"], h["lower_bound"], h["upper_bound"])}
            for h in horizons
        ]
        reverse = choose_recommendation(1 / current_rate, inverted_horizons, favorable_high=True)
        rows.append(
            {
                "base_code": quote_code,
                "quote_code": PIVOT,
                "recommendation": reverse["recommendation"],
                "reference_horizon_days": reverse["reference_horizon_days"],
                "current_rate": reverse["current_rate"],
                "expected_rate": reverse["expected_rate"],
                "lower_bound": reverse["lower_bound"],
                "upper_bound": reverse["upper_bound"],
            }
        )

    if not rows and currencies:
        logger.warning(
            "run_recommendations produced zero rows despite %d predictable currencies "
            "-- check predictions/rates_cache is populated",
            len(currencies),
        )

    insert_recommendations(rows)
    return len(rows)


def run_alert_evaluation() -> int:
    """Evaluates every active alert and records a firing event for each
    one that triggers. threshold alerts deactivate on fire (one-shot);
    recommendation_change alerts stay active (repeating). Each alert is
    evaluated independently -- a malformed alert's failure is collected
    and does not prevent evaluation of the remaining alerts, but the run
    still raises at the end if any alert failed (fail-loud overall).
    """
    fired = 0
    errors = []
    for alert in get_active_alerts():
        try:
            if alert["alert_type"] == "threshold":
                current_rate = get_directed_rate(alert["base_code"], alert["quote_code"])
                if current_rate is None:
                    # Unlike a fresh currency awaiting its first backtest, this
                    # app's 29-currency universe is fixed and known -- a missing
                    # rate for an alert's currency is unexpected, not a normal
                    # gap, so it fails loudly rather than being silently skipped.
                    raise ValueError(
                        f"No current rate for {alert['base_code']}/{alert['quote_code']} (alert {alert['id']})"
                    )
                if threshold_crossed(current_rate, float(alert["threshold_rate"]), alert["direction"]):
                    record_alert_event(
                        alert["id"],
                        {
                            "alert_type": "threshold",
                            "current_rate": current_rate,
                            "threshold_rate": float(alert["threshold_rate"]),
                            "direction": alert["direction"],
                        },
                    )
                    deactivate_alert(alert["id"])
                    fired += 1
            elif alert["alert_type"] == "recommendation_change":
                recent = get_latest_two_recommendations(alert["base_code"], alert["quote_code"])
                latest = recent[0] if recent else None
                previous = recent[1] if len(recent) > 1 else None
                if latest is not None and recommendation_changed(latest, previous):
                    record_alert_event(
                        alert["id"],
                        {
                            "alert_type": "recommendation_change",
                            "latest": latest,
                            "previous": previous,
                        },
                    )
                    fired += 1
        except Exception as exc:
            errors.append(f"alert {alert['id']}: {exc}")

    if errors:
        raise ValueError(f"{len(errors)} alert(s) failed evaluation: " + "; ".join(errors))
    return fired
