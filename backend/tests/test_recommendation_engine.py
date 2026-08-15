import pytest

from app.recommendations.engine import choose_recommendation, invert_prediction


def test_invert_prediction_flips_bound_order():
    result = invert_prediction(0.9, 0.85, 0.95)
    assert result["predicted_rate"] == pytest.approx(1 / 0.9)
    assert result["lower_bound"] == pytest.approx(1 / 0.95)
    assert result["upper_bound"] == pytest.approx(1 / 0.85)
    assert result["lower_bound"] < result["predicted_rate"] < result["upper_bound"]


def test_invert_prediction_round_trips():
    inverted = invert_prediction(0.9, 0.85, 0.95)
    back = invert_prediction(inverted["predicted_rate"], inverted["lower_bound"], inverted["upper_bound"])
    assert back["predicted_rate"] == pytest.approx(0.9)
    assert back["lower_bound"] == pytest.approx(0.85)
    assert back["upper_bound"] == pytest.approx(0.95)


HORIZONS = [
    {"horizon_days": 7, "predicted_rate": 90, "lower_bound": 88, "upper_bound": 92, "confidence": "normal"},
    {"horizon_days": 30, "predicted_rate": 95, "lower_bound": 91, "upper_bound": 99, "confidence": "normal"},
    {"horizon_days": 90, "predicted_rate": 93, "lower_bound": 85, "upper_bound": 101, "confidence": "normal"},
    {"horizon_days": 365, "predicted_rate": 100, "lower_bound": 80, "upper_bound": 120, "confidence": "normal"},
]


def test_choose_recommendation_waits_for_better_future_rate():
    result = choose_recommendation(85, HORIZONS, favorable_high=True)
    assert result["recommendation"] == "wait"
    assert result["reference_horizon_days"] == 365
    assert result["expected_rate"] == 100


def test_choose_recommendation_act_now_when_current_already_best():
    result = choose_recommendation(101, HORIZONS, favorable_high=True)
    assert result["recommendation"] == "act_now"


def test_choose_recommendation_volatile_when_reference_horizon_low_confidence():
    horizons = [dict(h) for h in HORIZONS]
    horizons[3] = {**horizons[3], "confidence": "low"}
    result = choose_recommendation(85, horizons, favorable_high=True)
    assert result["recommendation"] == "volatile"


HORIZONS_INVERTED = [
    {"horizon_days": 7, "predicted_rate": 0.011, "lower_bound": 0.0108, "upper_bound": 0.0113, "confidence": "normal"},
    {"horizon_days": 30, "predicted_rate": 0.0105, "lower_bound": 0.0101, "upper_bound": 0.011, "confidence": "normal"},
]


def test_choose_recommendation_favorable_low_direction_waits():
    result = choose_recommendation(0.012, HORIZONS_INVERTED, favorable_high=False)
    assert result["recommendation"] == "wait"
    assert result["reference_horizon_days"] == 30


def test_choose_recommendation_favorable_low_direction_act_now():
    result = choose_recommendation(0.0104, HORIZONS_INVERTED, favorable_high=False)
    assert result["recommendation"] == "act_now"


def test_choose_recommendation_raises_on_empty_horizons():
    with pytest.raises(ValueError):
        choose_recommendation(1.0, [], favorable_high=True)
