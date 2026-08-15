def invert_prediction(predicted_rate: float, lower_bound: float, upper_bound: float) -> dict:
    """Inverts a USD->X prediction into the X->USD direction. Reciprocal
    is a decreasing function for positive numbers, so bound order flips:
    the new lower bound comes from the old upper bound, and vice versa.
    """
    return {
        "predicted_rate": 1 / predicted_rate,
        "lower_bound": 1 / upper_bound,
        "upper_bound": 1 / lower_bound,
    }


def choose_recommendation(current_rate: float, horizons: list[dict], favorable_high: bool) -> dict:
    """Given one direction's current rate and its horizon predictions
    (already in that direction's own value-space -- inverted beforehand
    via invert_prediction if this is the X->USD direction), picks the
    reference horizon (whichever predicts the most favorable rate) and
    decides act_now/wait/volatile.

    `horizons` is a list of dicts, each with horizon_days, predicted_rate,
    lower_bound, upper_bound, confidence.
    """
    if not horizons:
        raise ValueError("no horizons to choose from")

    if favorable_high:
        reference = max(horizons, key=lambda h: h["predicted_rate"])
    else:
        reference = min(horizons, key=lambda h: h["predicted_rate"])

    if reference["confidence"] == "low":
        recommendation = "volatile"
    elif favorable_high:
        recommendation = "act_now" if current_rate >= reference["predicted_rate"] else "wait"
    else:
        recommendation = "act_now" if current_rate <= reference["predicted_rate"] else "wait"

    return {
        "recommendation": recommendation,
        "reference_horizon_days": reference["horizon_days"],
        "current_rate": current_rate,
        "expected_rate": reference["predicted_rate"],
        "lower_bound": reference["lower_bound"],
        "upper_bound": reference["upper_bound"],
    }
