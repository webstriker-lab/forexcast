from datetime import date as _date


def align_as_of(
    dates: list[str],
    observations: list[tuple[str, float]],
    max_staleness_days: int = 548,
) -> list[float | None]:
    """Forward-fills `observations` (sparse, e.g. monthly FRED data,
    sorted oldest to newest) onto every entry of `dates` (dense, e.g.
    daily trading dates, also sorted oldest to newest): each date gets
    the most recent observation known as of that date. A date before the
    first observation gets None -- no macro data was known yet at that
    point in history. Both inputs must already be sorted ascending by
    date (a two-pointer merge, not a search).

    A forward-filled value more than `max_staleness_days` older than the
    date it would apply to is treated as None instead of being carried
    forward indefinitely -- this catches a FRED series that has been
    discontinued (no new observations published) rather than silently
    treating a years-old value as if it were still current. The default
    (548 days, ~18 months) comfortably covers ordinary monthly-data
    publication lag while still catching genuinely dead series.
    """
    result: list[float | None] = []
    obs_index = 0
    current_value: float | None = None
    current_obs_date: str | None = None
    for date in dates:
        while obs_index < len(observations) and observations[obs_index][0] <= date:
            current_value = observations[obs_index][1]
            current_obs_date = observations[obs_index][0]
            obs_index += 1
        if current_value is not None:
            gap_days = (
                _date.fromisoformat(date) - _date.fromisoformat(current_obs_date)
            ).days
            if gap_days > max_staleness_days:
                result.append(None)
                continue
        result.append(current_value)
    return result
