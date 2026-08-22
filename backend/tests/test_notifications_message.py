from app.notifications.message import build_message


def test_build_message_formats_threshold_alert():
    alert = {"base_code": "USD", "quote_code": "EUR"}
    details = {
        "alert_type": "threshold",
        "current_rate": 1.0487,
        "threshold_rate": 1.05,
        "direction": "below",
    }
    result = build_message(alert, details)

    assert "USD/EUR" in result
    assert "below" in result
    assert "1.05" in result
    assert "1.0487" in result


def test_build_message_formats_recommendation_change_alert():
    alert = {"base_code": "USD", "quote_code": "INR"}
    details = {"alert_type": "recommendation_change", "latest": "act_now", "previous": "wait"}
    result = build_message(alert, details)

    assert "USD/INR" in result
    assert "wait" in result
    assert "act_now" in result


def test_build_message_raises_for_unknown_alert_type():
    alert = {"base_code": "USD", "quote_code": "INR"}
    details = {"alert_type": "something_else"}
    try:
        build_message(alert, details)
        assert False, "expected ValueError"
    except ValueError:
        pass
