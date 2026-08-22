def build_message(alert: dict, details: dict) -> str:
    """Formats a human-readable notification line from an alert_events
    row's `details` jsonb (written by app.recommendations.jobs,
    unchanged by this module) plus its parent alert's currency pair.

    `recommendation_change` details are trusted to always carry a
    non-null `previous` -- app.recommendations.alerts.recommendation_changed()
    returns False (so no event is ever recorded) whenever `previous` is
    None, so this formatter never needs to guard against that case.
    """
    pair = f"{alert['base_code']}/{alert['quote_code']}"
    alert_type = details.get("alert_type")
    if alert_type == "threshold":
        return (
            f"\U0001F514 {pair} crossed {details['direction']} "
            f"{details['threshold_rate']}: currently {details['current_rate']}"
        )
    if alert_type == "recommendation_change":
        return (
            f"\U0001F4CA {pair} recommendation changed: "
            f"{details['previous']} → {details['latest']}"
        )
    raise ValueError(f"unknown alert_type in details: {alert_type!r}")
