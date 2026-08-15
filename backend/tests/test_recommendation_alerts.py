import pytest

from app.recommendations.alerts import recommendation_changed, threshold_crossed


def test_threshold_crossed_above():
    assert threshold_crossed(86.0, 85.0, "above") is True
    assert threshold_crossed(84.0, 85.0, "above") is False


def test_threshold_crossed_below():
    assert threshold_crossed(84.0, 85.0, "below") is True
    assert threshold_crossed(86.0, 85.0, "below") is False


def test_threshold_crossed_raises_on_unknown_direction():
    with pytest.raises(ValueError):
        threshold_crossed(1.0, 2.0, "sideways")


def test_recommendation_changed_true_when_different():
    assert recommendation_changed("act_now", "wait") is True


def test_recommendation_changed_false_when_same():
    assert recommendation_changed("wait", "wait") is False


def test_recommendation_changed_false_when_no_previous():
    assert recommendation_changed("act_now", None) is False
