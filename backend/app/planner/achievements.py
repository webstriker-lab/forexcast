# backend/app/planner/achievements.py
"""Achievement and streak logic for gamification."""
from datetime import date, timedelta


BADGES = {
    "first_debt_paid_off": {
        "name": "First Debt Paid Off",
        "emoji": "🎯",
        "description": "Paid off your first debt completely",
    },
    "savings_goal_reached": {
        "name": "Savings Goal Reached",
        "emoji": "💰",
        "description": "Reached a savings goal",
    },
    "forex_check_100": {
        "name": "100 Forex Checks",
        "emoji": "📊",
        "description": "Checked forex rates 100 times",
    },
    "streak_30_days": {
        "name": "Fox Friend",
        "emoji": "🦊",
        "description": "30-day check-in streak",
    },
    "multi_currency_master": {
        "name": "Multi-Currency Master",
        "emoji": "🌍",
        "description": "Active debts in 3+ currencies",
    },
    "forecast_follower": {
        "name": "Forecast Follower",
        "emoji": "📈",
        "description": "Acted on 10 recommendations",
    },
    "financial_freedom": {
        "name": "Financial Freedom",
        "emoji": "🏆",
        "description": "All debts paid off",
    },
    "first_goal_set": {
        "name": "Goal Setter",
        "emoji": "🎯",
        "description": "Created your first savings goal",
    },
    "first_alert_created": {
        "name": "Alert Setter",
        "emoji": "🔔",
        "description": "Created your first alert",
    },
}


def check_debt_achievements(
    debts: list[dict],
    earned_badges: set[str],
) -> list[dict]:
    """Check if any debt-related achievements should be earned. Returns
    dicts shaped {"badge_id": str, "metadata": dict} only -- display data
    (name/emoji/description) lives solely in BADGES, looked up by
    badge_id by whoever renders these, never duplicated here.
    """
    new_achievements = []

    paid_off = [d for d in debts if d.get("current_balance", 0) == 0 and not d.get("is_active", True)]
    if paid_off and "first_debt_paid_off" not in earned_badges:
        new_achievements.append({
            "badge_id": "first_debt_paid_off",
            "metadata": {"debt_name": paid_off[0].get("name", "Unknown")},
        })

    active_currencies = {d["currency_code"] for d in debts if d.get("is_active", True)}
    if len(active_currencies) >= 3 and "multi_currency_master" not in earned_badges:
        new_achievements.append({
            "badge_id": "multi_currency_master",
            "metadata": {"currencies": list(active_currencies)},
        })

    active_debts_with_balance = [
        d for d in debts
        if d.get("is_active", True) and d.get("current_balance", 0) > 0
    ]
    if debts and not active_debts_with_balance and "financial_freedom" not in earned_badges:
        new_achievements.append({"badge_id": "financial_freedom", "metadata": None})

    return new_achievements


def check_savings_achievements(
    goals: list[dict],
    earned_badges: set[str],
) -> list[dict]:
    """Check if any savings-related achievements should be earned. See
    check_debt_achievements' docstring for the return shape rationale.
    """
    new_achievements = []

    reached = [g for g in goals if g.get("current_saved", 0) >= g.get("target_amount", 0)]
    if reached and "savings_goal_reached" not in earned_badges:
        new_achievements.append({
            "badge_id": "savings_goal_reached",
            "metadata": {"goal_name": reached[0].get("name", "Unknown")},
        })

    if goals and "first_goal_set" not in earned_badges:
        new_achievements.append({"badge_id": "first_goal_set", "metadata": None})

    return new_achievements


def update_streak(
    streak_data: dict,
    streak_type: str,
) -> dict:
    """Update a streak counter.
    
    Args:
        streak_data: Current streak data dictionary
        streak_type: Type of streak ('daily_checkin', 'savings', 'debt_payment')
    
    Returns:
        Updated streak data
    """
    today = date.today()
    last_key = f"{streak_type}_last"
    current_key = f"{streak_type}_current"
    best_key = f"{streak_type}_best"
    
    last_date = streak_data.get(last_key)
    
    # Parse date if it's a string
    if isinstance(last_date, str):
        last_date = date.fromisoformat(last_date)
    
    if last_date == today:
        return streak_data  # Already checked in today
    
    if last_date == today - timedelta(days=1):
        # Consecutive day
        streak_data[current_key] = streak_data.get(current_key, 0) + 1
    else:
        # Streak broken or first time
        streak_data[current_key] = 1
    
    streak_data[last_key] = today.isoformat()
    streak_data[best_key] = max(
        streak_data.get(best_key, 0),
        streak_data[current_key]
    )
    streak_data["updated_at"] = today.isoformat()
    
    return streak_data


def check_streak_achievements(
    streak_data: dict,
    earned_badges: set[str],
) -> list[dict]:
    """Check if any streak-related achievements should be earned. See
    check_debt_achievements' docstring for the return shape rationale.
    """
    new_achievements = []

    if streak_data.get("daily_checkin_current", 0) >= 30 and "streak_30_days" not in earned_badges:
        new_achievements.append({
            "badge_id": "streak_30_days",
            "metadata": {"streak_days": streak_data["daily_checkin_current"]},
        })

    return new_achievements
