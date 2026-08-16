from app.macro.align import align_as_of


def test_align_as_of_forward_fills_sparse_observations():
    dates = ["2020-01-01", "2020-01-15", "2020-02-01", "2020-02-15"]
    observations = [("2020-01-10", 0.5), ("2020-02-01", 0.6)]
    result = align_as_of(dates, observations)
    assert result == [None, 0.5, 0.6, 0.6]


def test_align_as_of_exact_date_match():
    dates = ["2020-01-01"]
    observations = [("2020-01-01", 1.25)]
    assert align_as_of(dates, observations) == [1.25]


def test_align_as_of_empty_observations_returns_all_none():
    dates = ["2020-01-01", "2020-01-02"]
    assert align_as_of(dates, []) == [None, None]


def test_align_as_of_empty_dates_returns_empty_list():
    assert align_as_of([], [("2020-01-01", 1.0)]) == []


def test_align_as_of_returns_none_for_stale_observation():
    dates = ["2025-01-01"]
    observations = [("2020-01-01", 5.0)]  # ~5 years stale
    assert align_as_of(dates, observations) == [None]


def test_align_as_of_keeps_observation_within_staleness_window():
    dates = ["2020-06-01"]
    observations = [("2020-01-01", 5.0)]  # ~5 months, within 548-day default
    assert align_as_of(dates, observations) == [5.0]


def test_align_as_of_respects_custom_max_staleness_days():
    dates = ["2020-02-01"]
    observations = [("2020-01-01", 5.0)]  # 31 days
    assert align_as_of(dates, observations, max_staleness_days=10) == [None]
