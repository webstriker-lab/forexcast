import pytest
from app.prediction.backtest import summarize


def _samples(errors, naive_errors=None, trailing_vols=None):
    return {
        "errors": errors,
        "naive_errors": naive_errors if naive_errors is not None else [],
        "trailing_vols": trailing_vols or [0.01] * len(errors),
    }


def test_summarize_es_mae_is_mean_abs_error():
    # errors = [0.1, -0.1] → MAE = 0.1
    s = summarize(_samples([0.1, -0.1], naive_errors=[0.2, -0.2]))
    assert s["es_mae"] == pytest.approx(0.1)


def test_summarize_naive_mae_is_mean_abs_naive_error():
    # naive errors = [0.2, -0.2] → naive MAE = 0.2
    s = summarize(_samples([0.1, -0.1], naive_errors=[0.2, -0.2]))
    assert s["naive_mae"] == pytest.approx(0.2)


def test_summarize_mae_improvement_positive_when_es_wins():
    # es_mae=0.1, naive_mae=0.2 → (0.2-0.1)/0.2*100 = 50%
    s = summarize(_samples([0.1, -0.1], naive_errors=[0.2, -0.2]))
    assert s["mae_improvement_pct"] == pytest.approx(50.0, abs=0.01)


def test_summarize_mae_improvement_negative_when_naive_wins():
    # es_mae=0.2, naive_mae=0.1 → (0.1-0.2)/0.1*100 = -100%
    s = summarize(_samples([0.2, -0.2], naive_errors=[0.1, -0.1]))
    assert s["mae_improvement_pct"] == pytest.approx(-100.0, abs=0.01)


def test_summarize_mae_improvement_none_when_no_naive_errors():
    s = summarize(_samples([0.1, -0.1]))
    assert s["mae_improvement_pct"] is None
    assert s["naive_mae"] is None


def test_summarize_calibration_coverage_between_zero_and_one():
    errors = [float(i) * 0.01 for i in range(-5, 6)]  # -0.05..0.05
    s = summarize(_samples(errors, naive_errors=errors[:]))
    assert 0.0 <= s["calibration_coverage"] <= 1.0


def test_summarize_calibration_coverage_near_eighty_percent_for_uniform_errors():
    # 10 evenly spaced errors: p10=min+0.9*range, p90=max-0.9*range
    # 8 of 10 should fall within [p10, p90]
    errors = [float(i) for i in range(1, 11)]
    s = summarize(_samples(errors, naive_errors=errors[:]))
    assert s["calibration_coverage"] >= 0.70
