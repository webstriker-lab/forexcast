def align_as_of(
    dates: list[str], observations: list[tuple[str, float]]
) -> list[float | None]:
    """Forward-fills `observations` (sparse, e.g. monthly FRED data,
    sorted oldest to newest) onto every entry of `dates` (dense, e.g.
    daily trading dates, also sorted oldest to newest): each date gets
    the most recent observation known as of that date. A date before the
    first observation gets None -- no macro data was known yet at that
    point in history. Both inputs must already be sorted ascending by
    date (a two-pointer merge, not a search).
    """
    result: list[float | None] = []
    obs_index = 0
    current_value: float | None = None
    for date in dates:
        while obs_index < len(observations) and observations[obs_index][0] <= date:
            current_value = observations[obs_index][1]
            obs_index += 1
        result.append(current_value)
    return result
