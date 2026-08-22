# backend/tests/test_planner_timeline.py
"""Tests for the timeline calculation engine."""
from datetime import date
import pytest
from app.planner.timeline import (
    calculate_debt_payoff,
    calculate_savings_timeline,
    calculate_forex_impact,
    calculate_total_debt_summary,
)


def test_calculate_debt_payoff_basic():
    """Test basic debt payoff calculation."""
    payments = calculate_debt_payoff(
        principal=10000,
        annual_rate=0.12,  # 12% annual = 1% monthly
        monthly_payment=500,
    )
    
    assert len(payments) > 0
    assert payments[-1].remaining_balance == 0
    assert all(p.payment == 500 for p in payments[:-1])
    assert all(p.interest > 0 for p in payments)
    assert all(p.principal > 0 for p in payments)


def test_calculate_debt_payoff_zero_balance():
    """Test with zero balance returns empty."""
    payments = calculate_debt_payoff(
        principal=0,
        annual_rate=0.12,
        monthly_payment=500,
    )
    assert payments == []


def test_calculate_debt_payoff_invalid_payment():
    """Test with payment too low raises error."""
    with pytest.raises(ValueError, match="Monthly payment must be positive"):
        calculate_debt_payoff(
            principal=10000,
            annual_rate=0.12,
            monthly_payment=0,
        )


def test_calculate_debt_payoff_payment_too_low():
    """Test with payment below interest raises error."""
    with pytest.raises(ValueError, match="must exceed monthly interest"):
        calculate_debt_payoff(
            principal=10000,
            annual_rate=0.12,  # 1% monthly = $100 interest
            monthly_payment=50,  # Less than interest
        )


def test_calculate_debt_payoff_total_interest():
    """Test total interest calculation."""
    payments = calculate_debt_payoff(
        principal=10000,
        annual_rate=0.12,
        monthly_payment=500,
    )
    
    total_interest = sum(p.interest for p in payments)
    total_principal = sum(p.principal for p in payments)
    
    assert abs(total_principal - 10000) < 0.01  # Should pay off exactly $10,000
    assert total_interest > 0  # Should pay some interest


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
    assert result["recommendation"] == "wait"  # Rate going up means wait
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
    
    assert result["recommendation"] == "act_now"  # Rate going down means act now
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


def test_calculate_total_debt_summary():
    """Test debt summary calculation."""
    debts = [
        {"current_balance": 5000, "interest_rate": 0.12, "minimum_payment": 200},
        {"current_balance": 3000, "interest_rate": 0.06, "minimum_payment": 100},
    ]
    
    summary = calculate_total_debt_summary(debts)
    
    assert summary["total_balance"] == 8000
    assert summary["total_minimum_payment"] == 300
    assert summary["debt_count"] == 2
    assert 0.06 < summary["weighted_average_rate"] < 0.12


def test_calculate_total_debt_summary_empty():
    """Test debt summary with no debts."""
    summary = calculate_total_debt_summary([])
    
    assert summary["total_balance"] == 0
    assert summary["total_minimum_payment"] == 0
    assert summary["debt_count"] == 0
