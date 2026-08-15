def threshold_crossed(current_rate: float, threshold_rate: float, direction: str) -> bool:
    """direction is 'above' or 'below', matching alerts.direction's check
    constraint."""
    if direction == "above":
        return current_rate > threshold_rate
    if direction == "below":
        return current_rate < threshold_rate
    raise ValueError(f"unknown direction: {direction}")


def recommendation_changed(latest: str, previous: str | None) -> bool:
    """True if the two most recent recommendations for a pair differ. If
    there's no previous recommendation yet (fewer than 2 rows exist),
    there's nothing to compare against -- not a change.
    """
    if previous is None:
        return False
    return latest != previous
