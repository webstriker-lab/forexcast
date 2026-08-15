from unittest.mock import patch

from app.prediction.backtest import run_backtest, summarize


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
