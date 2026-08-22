from unittest.mock import patch

from app.prediction.backtest import fit_regression, run_backtest, summarize
from app.prediction.horizons import trading_day_steps


def test_run_backtest_produces_fewer_samples_for_longer_horizons():
    # 500 trading days of mildly-trending synthetic data. Verified by hand
    # and by running this exact scenario: with MIN_HISTORY=60 and
    # ORIGIN_SPACING=30, there are 15 origins usable for the 7-day horizon
    # (steps=5) and 6 for the 365-day horizon (steps=261), since a 365-day
    # origin needs a lot more trailing future data to score against.
    rates = [100.0 + 0.01 * i for i in range(500)]
    results = run_backtest(rates, horizons=[7, 365])
    assert len(results[7]["errors"]) == 15
    assert len(results[365]["errors"]) == 6


def test_run_backtest_fits_only_on_data_up_to_each_origin():
    # No-look-ahead check: capture exactly what `history` each origin
    # passes to forecast(), and confirm it's precisely rates[:origin+1] --
    # never anything from beyond that origin.
    rates = [100.0 + i for i in range(150)]
    captured_histories = []

    def fake_forecast(history, steps):
        captured_histories.append(list(history))
        return history[-1]

    with patch("app.prediction.backtest.forecast", side_effect=fake_forecast):
        run_backtest(rates, horizons=[7])

    expected_origins = [60, 90, 120]  # MIN_HISTORY=60, ORIGIN_SPACING=30, n=150
    assert len(captured_histories) == len(expected_origins)
    for origin, history in zip(expected_origins, captured_histories):
        assert history == rates[: origin + 1]


def test_summarize_computes_percentiles_and_sample_count():
    samples = {
        "errors": [-2.0, -1.0, 0.0, 1.0, 2.0],
        "trailing_vols": [0.01, 0.02, 0.03, 0.04, 0.05],
    }
    result = summarize(samples)
    assert result["sample_count"] == 5
    assert result["error_lower_pct"] < 0
    assert result["error_upper_pct"] > 0
    assert result["volatility_p90"] > 0.04


def test_run_backtest_collects_named_factors_parallel_to_errors():
    rates = [100.0 + i for i in range(150)]
    # MIN_HISTORY=60, ORIGIN_SPACING=30 -> origins at 60, 90, 120
    rate_diffs = [0.01 * i for i in range(150)]
    cpi_diffs = [0.02 * i for i in range(150)]
    results = run_backtest(
        rates, horizons=[7], factors={"interest_rate": rate_diffs, "cpi": cpi_diffs}
    )
    assert results[7]["factors"]["interest_rate"] == [
        rate_diffs[60], rate_diffs[90], rate_diffs[120]
    ]
    assert results[7]["factors"]["cpi"] == [
        cpi_diffs[60], cpi_diffs[90], cpi_diffs[120]
    ]
    assert len(results[7]["factors"]["interest_rate"]) == len(results[7]["errors"])


def test_run_backtest_factor_none_entries_pass_through():
    rates = [100.0 + i for i in range(150)]
    rate_diffs = [None] * 70 + [0.5] * 80  # unknown until day 70
    results = run_backtest(rates, horizons=[7], factors={"interest_rate": rate_diffs})
    # origin 60 falls in the None region, origins 90/120 don't
    assert results[7]["factors"]["interest_rate"] == [None, 0.5, 0.5]


def test_fit_regression_recovers_known_slope_with_enough_significant_samples():
    # Deterministic synthetic data with a real linear relationship plus
    # small noise -- verified by hand: scipy.stats.linregress on this
    # exact data recovers slope=0.00408 (true 0.004) with p-value~2e-23,
    # comfortably clearing both the min_samples=24 and p_threshold=0.10
    # gates.
    import random
    random.seed(42)
    differentials = [i * 0.2 - 2.0 for i in range(30)]
    errors = [0.004 * d + -0.01 + random.uniform(-0.002, 0.002) for d in differentials]
    result = fit_regression(errors, differentials)
    assert result is not None
    assert abs(result["slope"] - 0.004) < 0.001
    assert abs(result["intercept"] - (-0.01)) < 0.001


def test_fit_regression_returns_none_below_min_samples():
    # Only 5 samples -- rejected by the min_samples=24 gate regardless of
    # fit quality (this data is a perfect fit, verified by hand: p-value
    # ~1.2e-30, which would otherwise easily clear p_threshold).
    differentials = [0.1, 0.2, 0.3, 0.4, 0.5]
    errors = [0.001, 0.002, 0.003, 0.004, 0.005]
    assert fit_regression(errors, differentials) is None


def test_fit_regression_returns_none_when_relationship_is_not_significant():
    # 30 samples (clears min_samples) but no real relationship -- verified
    # by hand: p-value~0.76, well above p_threshold=0.10.
    differentials = list(range(30))
    errors = [0.01 if i % 2 == 0 else -0.01 for i in range(30)]
    assert fit_regression(errors, differentials) is None


def test_summarize_stores_none_regression_when_no_factors_key():
    samples = {
        "errors": [-2.0, -1.0, 0.0, 1.0, 2.0],
        "trailing_vols": [0.01, 0.02, 0.03, 0.04, 0.05],
    }
    result = summarize(samples)
    assert result["regression_factor"] is None
    assert result["regression_slope"] is None
    assert result["regression_intercept"] is None


def test_summarize_fits_and_applies_regression_to_bounds():
    import random
    random.seed(7)
    differentials = [i * 0.2 - 2.0 for i in range(30)]
    errors = [0.004 * d - 0.01 + random.uniform(-0.001, 0.001) for d in differentials]
    samples = {
        "errors": errors,
        "trailing_vols": [0.01] * 30,
        "factors": {"interest_rate": differentials},
    }
    result = summarize(samples)
    assert result["regression_factor"] == "interest_rate"
    assert result["regression_slope"] is not None
    assert abs(result["regression_slope"] - 0.004) < 0.001
    # Post-adjustment residuals must be tighter than the raw error spread,
    # since the regression explains away the systematic component.
    raw_spread = max(errors) - min(errors)
    fitted_spread = result["error_upper_pct"] - result["error_lower_pct"]
    assert fitted_spread < raw_spread


def test_summarize_picks_whichever_factor_has_the_lowest_residual_mae():
    import random
    random.seed(11)
    n = 30
    base = [i * 0.2 - 2.0 for i in range(n)]
    errors = [0.004 * d - 0.01 + random.uniform(-0.0005, 0.0005) for d in base]
    # interest_rate IS the exact series errors were built from (tight fit).
    # cpi tracks the same underlying trend but with heavy added noise --
    # still a real, significant relationship, just a much worse fit --
    # so interest_rate must win on lower residual MAE.
    interest_rate = base
    cpi = [d + random.uniform(-1.0, 1.0) for d in base]
    samples = {
        "errors": errors,
        "trailing_vols": [0.01] * n,
        "factors": {"cpi": cpi, "interest_rate": interest_rate},
    }
    result = summarize(samples)
    assert result["regression_factor"] == "interest_rate"


def test_run_backtest_collects_naive_errors_parallel_to_errors():
    rates = [100.0 + i for i in range(150)]
    results = run_backtest(rates, horizons=[7])
    assert len(results[7]["naive_errors"]) == len(results[7]["errors"])
    # naive_forecast just returns the last known rate -- verify directly
    # against the origins the sibling no-look-ahead test established for
    # this exact scenario: MIN_HISTORY=60, ORIGIN_SPACING=30 -> 60, 90, 120.
    steps = trading_day_steps(7)
    for origin, naive_error in zip([60, 90, 120], results[7]["naive_errors"]):
        actual = rates[origin + steps]
        last_known = rates[origin]
        assert naive_error == (actual - last_known) / last_known


def test_summarize_selects_naive_when_it_has_lower_error():
    samples = {
        "errors": [0.10, -0.10, 0.12, -0.12, 0.11],  # exponential smoothing: large errors
        "naive_errors": [0.01, -0.01, 0.02, -0.02, 0.01],  # naive: much smaller
        "trailing_vols": [0.01] * 5,
    }
    result = summarize(samples)
    assert result["model_selected"] == "naive"
    # bounds must reflect the tighter naive error spread, not the wider ES one
    assert result["error_upper_pct"] < 0.10


def test_summarize_selects_exponential_smoothing_when_it_has_lower_error():
    samples = {
        "errors": [0.01, -0.01, 0.02, -0.02, 0.01],
        "naive_errors": [0.10, -0.10, 0.12, -0.12, 0.11],
        "trailing_vols": [0.01] * 5,
    }
    result = summarize(samples)
    assert result["model_selected"] == "exponential_smoothing"


def test_summarize_defaults_to_exponential_smoothing_without_naive_errors():
    # Backward compatibility: a caller that doesn't provide naive_errors
    # (summarize() exercised in isolation, as every pre-existing test in
    # this file does) gets the historical default, not an error.
    samples = {
        "errors": [-2.0, -1.0, 0.0, 1.0, 2.0],
        "trailing_vols": [0.01, 0.02, 0.03, 0.04, 0.05],
    }
    result = summarize(samples)
    assert result["model_selected"] == "exponential_smoothing"


def test_summarize_skips_regression_when_naive_selected():
    # The regression only ever adjusts exponential smoothing's residuals
    # -- naive has no baseline drift for a differential to correct. Here
    # errors/differentials would otherwise clearly clear fit_regression's
    # gates, but naive_errors are tiny by comparison, so naive must win
    # and the regression must NOT be fit.
    import random
    random.seed(7)
    differentials = [i * 0.2 - 2.0 for i in range(30)]
    errors = [0.004 * d - 0.01 + random.uniform(-0.001, 0.001) for d in differentials]
    samples = {
        "errors": errors,
        "naive_errors": [0.0001] * 30,
        "trailing_vols": [0.01] * 30,
        "factors": {"interest_rate": differentials},
    }
    result = summarize(samples)
    assert result["model_selected"] == "naive"
    assert result["regression_factor"] is None
    assert result["regression_slope"] is None
    assert result["regression_intercept"] is None


def test_summarize_falls_back_to_raw_error_for_unpaired_origins():
    # A regression IS fit (24 paired samples, the minimum to clear
    # min_samples), plus 3 additional origins with no known differential
    # and a wild raw error (0.5) -- those 3 must contribute their RAW
    # error as-is (not silently dropped, not incorrectly "adjusted" via
    # the fitted line), since that's what production would actually do
    # for a day with no current differential. Verified by hand: with 3
    # such outliers among 27 total samples, the 90th-percentile rank
    # (26 * 0.9 = 23.4) falls just past the paired block into the
    # outlier block, giving error_upper_pct~0.20 -- if the unpaired
    # entries were wrongly dropped (24 samples total) or wrongly
    # regression-adjusted (extrapolating the fitted line with no real
    # differential), this would come out far smaller.
    import random
    random.seed(3)
    paired_differentials = [i * 0.2 - 2.0 for i in range(24)]
    paired_errors = [
        0.004 * d - 0.01 + random.uniform(-0.001, 0.001) for d in paired_differentials
    ]
    differentials = paired_differentials + [None, None, None]
    errors = paired_errors + [0.5, 0.5, 0.5]
    samples = {
        "errors": errors,
        "trailing_vols": [0.01] * 27,
        "factors": {"interest_rate": differentials},
    }
    result = summarize(samples)
    assert result["regression_factor"] == "interest_rate"
    assert result["regression_slope"] is not None
    assert result["error_upper_pct"] > 0.1
