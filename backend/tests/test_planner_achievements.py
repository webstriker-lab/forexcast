# backend/tests/test_planner_achievements.py
"""Tests for the achievement and streak logic."""
from datetime import date, timedelta
import pytest
from app.planner.achievements import (
    check_debt_achievements,
    check_savings_achievements,
    check_streak_achievements,
    update_streak,
    BADGES,
)


def test_check_debt_achievements_first_paid_off():
    """Test first debt paid off achievement."""
    debts = [
        {"name": "Student Loan", "current_balance": 0, "is_active": False, "currency_code": "USD"},
    ]
    earned = set()
    
    new = check_debt_achievements(debts, earned)
    
    badge_ids = {a["badge_id"] for a in new}
    assert "first_debt_paid_off" in badge_ids
    assert "financial_freedom" in badge_ids  # Also triggers when all debts paid off


def test_check_debt_achievements_already_earned():
    """Test that already-earned achievements are not duplicated."""
    debts = [
        {"name": "Student Loan", "current_balance": 0, "is_active": False, "currency_code": "USD"},
    ]
    earned = {"first_debt_paid_off", "financial_freedom"}
    
    new = check_debt_achievements(debts, earned)
    
    assert len(new) == 0


def test_check_debt_achievements_multi_currency():
    """Test multi-currency achievement."""
    debts = [
        {"name": "USD Debt", "current_balance": 1000, "is_active": True, "currency_code": "USD"},
        {"name": "EUR Debt", "current_balance": 500, "is_active": True, "currency_code": "EUR"},
        {"name": "GBP Debt", "current_balance": 300, "is_active": True, "currency_code": "GBP"},
    ]
    earned = set()
    
    new = check_debt_achievements(debts, earned)
    
    badge_ids = {a["badge_id"] for a in new}
    assert "multi_currency_master" in badge_ids


def test_check_debt_achievements_financial_freedom():
    """Test financial freedom achievement."""
    debts = [
        {"name": "Loan 1", "current_balance": 0, "is_active": False, "currency_code": "USD"},
        {"name": "Loan 2", "current_balance": 0, "is_active": False, "currency_code": "USD"},
    ]
    earned = {"first_debt_paid_off"}
    
    new = check_debt_achievements(debts, earned)
    
    badge_ids = {a["badge_id"] for a in new}
    assert "financial_freedom" in badge_ids


def test_check_debt_achievements_no_duplicates():
    """Test that multi-currency is not awarded with only 2 currencies."""
    debts = [
        {"name": "USD Debt", "current_balance": 1000, "is_active": True, "currency_code": "USD"},
        {"name": "EUR Debt", "current_balance": 500, "is_active": True, "currency_code": "EUR"},
    ]
    earned = set()
    
    new = check_debt_achievements(debts, earned)
    
    badge_ids = {a["badge_id"] for a in new}
    assert "multi_currency_master" not in badge_ids


def test_check_savings_achievements_goal_reached():
    """Test savings goal reached achievement."""
    goals = [
        {"name": "Europe Trip", "target_amount": 5000, "current_saved": 6000},
    ]
    earned = set()
    
    new = check_savings_achievements(goals, earned)
    
    badge_ids = {a["badge_id"] for a in new}
    assert "savings_goal_reached" in badge_ids


def test_check_savings_achievements_first_goal():
    """Test first goal set achievement."""
    goals = [
        {"name": "Emergency Fund", "target_amount": 10000, "current_saved": 1000},
    ]
    earned = set()
    
    new = check_savings_achievements(goals, earned)
    
    badge_ids = {a["badge_id"] for a in new}
    assert "first_goal_set" in badge_ids


def test_check_savings_achievements_no_goals():
    """Test with no goals."""
    earned = set()
    
    new = check_savings_achievements([], earned)
    
    assert len(new) == 0


def test_update_streak_consecutive_day():
    """Test streak update on consecutive day."""
    yesterday = date.today() - timedelta(days=1)
    streak_data = {
        "daily_checkin_current": 5,
        "daily_checkin_best": 10,
        "daily_checkin_last": yesterday.isoformat(),
    }
    
    updated = update_streak(streak_data, "daily_checkin")
    
    assert updated["daily_checkin_current"] == 6
    assert updated["daily_checkin_best"] == 10
    assert updated["daily_checkin_last"] == date.today().isoformat()


def test_update_streak_broken():
    """Test streak update when streak is broken."""
    two_days_ago = date.today() - timedelta(days=2)
    streak_data = {
        "daily_checkin_current": 5,
        "daily_checkin_best": 10,
        "daily_checkin_last": two_days_ago.isoformat(),
    }
    
    updated = update_streak(streak_data, "daily_checkin")
    
    assert updated["daily_checkin_current"] == 1
    assert updated["daily_checkin_best"] == 10


def test_update_streak_same_day():
    """Test streak update on same day (no change)."""
    today = date.today()
    streak_data = {
        "daily_checkin_current": 5,
        "daily_checkin_best": 10,
        "daily_checkin_last": today.isoformat(),
    }
    
    updated = update_streak(streak_data, "daily_checkin")
    
    assert updated["daily_checkin_current"] == 5
    assert updated["daily_checkin_best"] == 10


def test_update_streak_new_best():
    """Test streak update when new best is achieved."""
    yesterday = date.today() - timedelta(days=1)
    streak_data = {
        "daily_checkin_current": 10,
        "daily_checkin_best": 10,
        "daily_checkin_last": yesterday.isoformat(),
    }
    
    updated = update_streak(streak_data, "daily_checkin")
    
    assert updated["daily_checkin_current"] == 11
    assert updated["daily_checkin_best"] == 11


def test_check_streak_achievements_30_days():
    """Test 30-day streak achievement. Only badge_id and metadata are
    returned -- display fields (name/emoji/description) come from the
    BADGES catalog by badge_id, not duplicated onto the achievement row.
    """
    streak_data = {
        "daily_checkin_current": 30,
        "daily_checkin_best": 30,
    }
    earned = set()
    
    new = check_streak_achievements(streak_data, earned)
    
    assert len(new) == 1
    assert new[0]["badge_id"] == "streak_30_days"
    assert new[0]["metadata"] == {"streak_days": 30}
    assert "emoji" not in new[0]
    assert "name" not in new[0]


def test_check_streak_achievements_not_yet():
    """Test streak achievement not yet earned."""
    streak_data = {
        "daily_checkin_current": 15,
        "daily_checkin_best": 15,
    }
    earned = set()
    
    new = check_streak_achievements(streak_data, earned)
    
    assert len(new) == 0


def test_check_streak_achievements_already_earned():
    """Test streak achievement already earned."""
    streak_data = {
        "daily_checkin_current": 30,
        "daily_checkin_best": 30,
    }
    earned = {"streak_30_days"}
    
    new = check_streak_achievements(streak_data, earned)
    
    assert len(new) == 0


def test_badges_constant():
    """Test that BADGES constant is properly defined."""
    assert "first_debt_paid_off" in BADGES
    assert "savings_goal_reached" in BADGES
    assert "streak_30_days" in BADGES
    assert "financial_freedom" in BADGES
    
    for badge_id, badge in BADGES.items():
        assert "name" in badge
        assert "emoji" in badge
        assert "description" in badge
