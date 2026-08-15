def percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile of an already-sorted list (the
    common "linear" method, matching e.g. numpy's default). `pct` is 0-100.
    """
    if not sorted_values:
        raise ValueError("cannot compute a percentile of an empty sample")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (pct / 100)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    fraction = rank - lower_index
    return (
        sorted_values[lower_index]
        + (sorted_values[upper_index] - sorted_values[lower_index]) * fraction
    )


def realized_volatility(rates: list[float], end_index: int, window: int = 30) -> float:
    """Standard deviation of daily returns over the `window` trading days
    ending just before `end_index` (rates[end_index] itself is excluded,
    matching Python slicing). Used both historically in the backtest
    (passing the origin's index, so only data known as of that origin is
    used -- no look-ahead) and for today's live volatility check (passing
    len(rates), so the most recent `window` days are used).
    """
    start = max(0, end_index - window)
    segment = rates[start:end_index]
    if len(segment) < 2:
        return 0.0
    returns = [
        (segment[i] - segment[i - 1]) / segment[i - 1] for i in range(1, len(segment))
    ]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return variance**0.5
