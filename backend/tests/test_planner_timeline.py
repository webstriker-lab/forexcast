# backend/tests/test_planner_timeline.py
"""Tests for the timeline calculation engine."""
from datetime import date
import pytest
from app.planner.timeline import (
    calculate_debt_payoff,
    calculate_savings_timeline,
    derive_monthly_contribution,
    calculate_forex_impact,
    calculate_total_debt_summary,
)


def test_calculate_debt_payoff_basic():
    """Interest rate is a plain percentage (12 means 12% APR), not a
    fraction -- pins the exact known values for this input, verified by
    hand: 12% APR / 12 = 1% monthly, $10,000 @ $500/mo pays off in 23
    months with $1,213.48 total interest.
    """
    payments = calculate_debt_payoff(
        principal=10000,
        annual_rate=12,
        monthly_payment=500,
    )

    assert len(payments) == 23
    assert payments[-1].remaining_balance == 0
    assert all(p.payment == 500 for p in payments[:-1])
    total_interest = round(sum(p.interest for p in payments), 2)
    assert total_interest == 1213.48


def test_calculate_debt_payoff_zero_balance():
    """Test with zero balance returns empty."""
    payments = calculate_debt_payoff(
        principal=0,
        annual_rate=12,
        monthly_payment=500,
    )
    assert payments == []


def test_calculate_debt_payoff_zero_interest():
    """0% interest is a valid, common case (e.g. a promotional-rate
    card) and must not divide by zero or otherwise misbehave.
    """
    payments = calculate_debt_payoff(
        principal=1200,
        annual_rate=0,
        monthly_payment=100,
    )
    assert len(payments) == 12
    assert all(p.interest == 0 for p in payments)
    assert payments[-1].remaining_balance == 0


def test_calculate_debt_payoff_invalid_payment():
    """Test with payment too low raises error."""
    with pytest.raises(ValueError, match="Monthly payment must be positive"):
        calculate_debt_payoff(
            principal=10000,
            annual_rate=12,
            monthly_payment=0,
        )


def test_calculate_debt_payoff_payment_too_low():
    """Test with payment below interest raises error. 12% APR = 1%
    monthly = $100 interest on a $10,000 balance; $50 doesn't cover it.
    """
    with pytest.raises(ValueError, match="must exceed monthly interest"):
        calculate_debt_payoff(
            principal=10000,
            annual_rate=12,
            monthly_payment=50,
        )


def test_calculate_savings_timeline_basic():
    """Test basic savings timeline calculation."""
    timeline = calculate_savings_timeline(
        target_amount=10000,
        monthly_contribution=1000,
        current_saved=0,
    )

    assert len(timeline) == 10  # 10 months to save $10,000
    assert timeline[-1].balance == 10000
    assert timeline[-1].progress == 1.0
    assert all(e.progress <= 1.0 for e in timeline)


def test_calculate_savings_timeline_with_existing():
    """Test savings timeline with existing savings."""
    timeline = calculate_savings_timeline(
        target_amount=10000,
        monthly_contribution=1000,
        current_saved=5000,
    )

    assert len(timeline) == 5  # 5 more months needed
    assert timeline[0].balance == 6000
    assert timeline[-1].balance == 10000


def test_calculate_savings_timeline_already_reached():
    """Test when goal is already reached."""
    timeline = calculate_savings_timeline(
        target_amount=10000,
        monthly_contribution=1000,
        current_saved=15000,
    )

    assert len(timeline) == 1
    assert timeline[0].progress == 1.0


def test_calculate_savings_timeline_invalid():
    """Test with invalid inputs."""
    with pytest.raises(ValueError, match="Target amount must be positive"):
        calculate_savings_timeline(
            target_amount=0,
            monthly_contribution=1000,
        )

    with pytest.raises(ValueError, match="Monthly contribution must be positive"):
        calculate_savings_timeline(
            target_amount=10000,
            monthly_contribution=0,
        )


def test_derive_monthly_contribution_basic():
    """6 months out, need $6000 more -> $1000/month."""
    result = derive_monthly_contribution(
        target_amount=10000,
        current_saved=4000,
        target_date=date(2026, 8, 1),
        today=date(2026, 2, 1),
    )
    assert result == 1000.0


def test_derive_monthly_contribution_floors_at_one_month():
    """A target date in the same month (or the past) must not divide by
    zero -- floors at 1 month.
    """
    result = derive_monthly_contribution(
        target_amount=1000,
        current_saved=0,
        target_date=date(2026, 2, 15),
        today=date(2026, 2, 1),
    )
    assert result == 1000.0


def test_derive_monthly_contribution_already_reached():
    """Already at or past the target -- no negative contribution."""
    result = derive_monthly_contribution(
        target_amount=1000,
        current_saved=1500,
        target_date=date(2026, 8, 1),
        today=date(2026, 2, 1),
    )
    assert result == 0.0


def test_calculate_forex_impact_basic():
    """Test basic forex impact calculation."""
    result = calculate_forex_impact(
        debt_amount=1000,
        debt_currency="USD",
        income_currency="INR",
        current_rate=83.0,
        predicted_rate=85.0,
    )

    assert result["debt_amount"] == 1000
    assert result["current_rate"] == 83.0
    assert result["predicted_rate"] == 85.0
    assert result["recommendation"] == "wait"
    assert result["potential_savings"] > 0


def test_calculate_forex_impact_act_now():
    """Test forex impact when rate is favorable now."""
    result = calculate_forex_impact(
        debt_amount=1000,
        debt_currency="USD",
        income_currency="INR",
        current_rate=85.0,
        predicted_rate=83.0,
    )

    assert result["recommendation"] == "act_now"
    assert result["potential_savings"] < 0


def test_calculate_forex_impact_invalid():
    """Test with invalid rates."""
    with pytest.raises(ValueError, match="Exchange rates must be positive"):
        calculate_forex_impact(
            debt_amount=1000,
            debt_currency="USD",
            income_currency="INR",
            current_rate=0,
            predicted_rate=85.0,
        )


def test_calculate_total_debt_summary_converts_to_usd():
    """Two debts in different currencies must be converted to USD (via
    the passed-in rates dict, currency_code -> units of that currency
    per 1 USD, matching get_current_rate's convention) before summing --
    not added together raw.
    """
    debts = [
        {"current_balance": 1000, "interest_rate": 12, "minimum_payment": 100, "currency_code": "USD"},
        {"current_balance": 9200, "interest_rate": 6, "minimum_payment": 500, "currency_code": "EUR"},
    ]
    rates = {"EUR": 0.92}  # 0.92 EUR per 1 USD -> 9200 EUR = 10000 USD

    summary = calculate_total_debt_summary(debts, rates)

    assert summary["total_balance"] == 11000.0  # 1000 USD + 10000 USD
    assert summary["debt_count"] == 2
    assert summary["currencies_missing_rate"] == []


def test_calculate_total_debt_summary_reports_missing_rates():
    """A debt whose currency has no entry in `rates` is excluded from
    total_balance and reported, not silently mis-summed.
    """
    debts = [
        {"current_balance": 1000, "interest_rate": 12, "minimum_payment": 100, "currency_code": "USD"},
        {"current_balance": 500, "interest_rate": 6, "minimum_payment": 50, "currency_code": "GBP"},
    ]
    rates = {}  # no GBP rate available

    summary = calculate_total_debt_summary(debts, rates)

    assert summary["total_balance"] == 1000.0  # GBP debt excluded
    assert summary["currencies_missing_rate"] == ["GBP"]


def test_calculate_total_debt_summary_empty():
    """Test debt summary with no debts."""
    summary = calculate_total_debt_summary([], {})

    assert summary["total_balance"] == 0
    assert summary["total_minimum_payment"] == 0
    assert summary["debt_count"] == 0
    assert summary["currencies_missing_rate"] == []
