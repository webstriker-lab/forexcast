from unittest.mock import patch

from app.prediction.backtest import fit_regression, run_backtest, summarize


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


def test_run_backtest_collects_differentials_parallel_to_errors():
    rates = [100.0 + i for i in range(150)]
    # MIN_HISTORY=60, ORIGIN_SPACING=30 -> origins at 60, 90, 120
    differentials = [0.01 * i for i in range(150)]
    results = run_backtest(rates, horizons=[7], differentials=differentials)
    assert results[7]["differentials"] == [
        differentials[60], differentials[90], differentials[120]
    ]
    assert len(results[7]["differentials"]) == len(results[7]["errors"])


def test_run_backtest_differentials_none_entries_pass_through():
    rates = [100.0 + i for i in range(150)]
    differentials = [None] * 70 + [0.5] * 80  # unknown until day 70
    results = run_backtest(rates, horizons=[7], differentials=differentials)
    # origin 60 falls in the None region, origins 90/120 don't
    assert results[7]["differentials"] == [None, 0.5, 0.5]


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


def test_summarize_stores_none_regression_when_no_differentials_key():
    samples = {
        "errors": [-2.0, -1.0, 0.0, 1.0, 2.0],
        "trailing_vols": [0.01, 0.02, 0.03, 0.04, 0.05],
    }
    result = summarize(samples)
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
        "differentials": differentials,
    }
    result = summarize(samples)
    assert result["regression_slope"] is not None
    assert abs(result["regression_slope"] - 0.004) < 0.001
    # Post-adjustment residuals must be tighter than the raw error spread,
    # since the regression explains away the systematic component.
    raw_spread = max(errors) - min(errors)
    fitted_spread = result["error_upper_pct"] - result["error_lower_pct"]
    assert fitted_spread < raw_spread


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
        "differentials": differentials,
    }
    result = summarize(samples)
    assert result["regression_slope"] is not None
    assert result["error_upper_pct"] > 0.1
