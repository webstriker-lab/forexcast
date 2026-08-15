from app.ingestion.supabase_rest import get_active_currencies
from app.recommendations.alerts import recommendation_changed, threshold_crossed
from app.recommendations.engine import choose_recommendation, invert_prediction
from app.recommendations.supabase_rest import (
    deactivate_alert,
    get_active_alerts,
    get_current_rate,
    get_latest_predictions,
    get_latest_two_recommendations,
    insert_recommendations,
    record_alert_event,
)

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
    rows = []
    for quote_code in _predictable_currencies():
        horizons = get_latest_predictions(quote_code)
        if not horizons:
            continue
        current_rate = get_current_rate(quote_code)
        if current_rate is None:
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
        reverse = choose_recommendation(1 / current_rate, inverted_horizons, favorable_high=False)
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

    insert_recommendations(rows)
    return len(rows)


def run_alert_evaluation() -> int:
    """Evaluates every active alert and records a firing event for each
    one that triggers. threshold alerts deactivate on fire (one-shot);
    recommendation_change alerts stay active (repeating).
    """
    fired = 0
    for alert in get_active_alerts():
        if alert["alert_type"] == "threshold":
            current_rate = get_current_rate(alert["quote_code"])
            if current_rate is None:
                # Unlike a fresh currency awaiting its first backtest, this
                # app's 29-currency universe is fixed and known -- a missing
                # rate for an alert's currency is unexpected, not a normal
                # gap, so it fails loudly rather than being silently skipped.
                raise ValueError(
                    f"No current rate for {alert['quote_code']} (alert {alert['id']})"
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
    return fired
