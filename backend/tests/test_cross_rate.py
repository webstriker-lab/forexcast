from unittest.mock import patch

import pytest

from app.ingestion.cross_rate import cross_rate


def test_same_currency_returns_one_without_lookup():
    with patch("app.ingestion.cross_rate.get_usd_rate") as mock_get:
        result = cross_rate("2026-08-13", "EUR", "EUR")

    assert result == 1.0
    mock_get.assert_not_called()


def test_computes_cross_rate_via_usd_pivot():
    def fake_get_usd_rate(as_of, code):
        return {"EUR": 2.0, "INR": 10.0}[code]

    with patch("app.ingestion.cross_rate.get_usd_rate", side_effect=fake_get_usd_rate):
        result = cross_rate("2026-08-13", "EUR", "INR")

    assert result == 5.0


def test_calls_get_usd_rate_with_correct_args():
    def fake_get_usd_rate(as_of, code):
        return {"EUR": 2.0, "INR": 10.0}[code]

    with patch(
        "app.ingestion.cross_rate.get_usd_rate", side_effect=fake_get_usd_rate
    ) as mock_get:
        cross_rate("2026-08-13", "EUR", "INR")

    mock_get.assert_any_call("2026-08-13", "EUR")
    mock_get.assert_any_call("2026-08-13", "INR")


def test_raises_when_from_rate_missing():
    def fake_get_usd_rate(as_of, code):
        return None if code == "EUR" else 10.0

    with patch("app.ingestion.cross_rate.get_usd_rate", side_effect=fake_get_usd_rate):
        with pytest.raises(ValueError, match="EUR"):
            cross_rate("2026-08-13", "EUR", "INR")


def test_raises_when_to_rate_missing():
    def fake_get_usd_rate(as_of, code):
        return 2.0 if code == "EUR" else None

    with patch("app.ingestion.cross_rate.get_usd_rate", side_effect=fake_get_usd_rate):
        with pytest.raises(ValueError, match="INR"):
            cross_rate("2026-08-13", "EUR", "INR")
