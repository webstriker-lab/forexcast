# backend/app/planner/routes.py
"""FastAPI routes for the debt savings planner."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

from app.auth import get_current_user
from app.recommendations.supabase_rest import get_current_rate
from app.planner.supabase_rest import (
    get_user_debts, create_debt, update_debt, delete_debt,
    get_user_income, create_income, update_income, delete_income,
    get_user_savings_goals, create_savings_goal, update_savings_goal, delete_savings_goal,
    get_user_achievements, create_achievement,
    get_user_streaks, upsert_user_streaks,
)
from app.planner.timeline import (
    calculate_debt_payoff, calculate_savings_timeline, derive_monthly_contribution,
    calculate_forex_impact, calculate_total_debt_summary,
)
from app.planner.achievements import (
    check_debt_achievements, check_savings_achievements,
    check_streak_achievements, update_streak, BADGES,
)

router = APIRouter(prefix="/planner", tags=["planner"])


# === Request/Response Models ===

class DebtCreate(BaseModel):
    name: str
    currency_code: str
    original_amount: float = Field(gt=0)
    current_balance: float = Field(ge=0)
    interest_rate: float = Field(ge=0)
    minimum_payment: float = Field(gt=0)
    due_day: Optional[int] = Field(None, ge=1, le=31)

class DebtUpdate(BaseModel):
    name: Optional[str] = None
    current_balance: Optional[float] = Field(None, ge=0)
    interest_rate: Optional[float] = Field(None, ge=0)
    minimum_payment: Optional[float] = Field(None, gt=0)
    due_day: Optional[int] = Field(None, ge=1, le=31)

class IncomeCreate(BaseModel):
    name: str
    currency_code: str
    amount: float = Field(gt=0)
    frequency: str = Field(pattern="^(monthly|biweekly|weekly)$")

class IncomeUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = Field(None, gt=0)
    frequency: Optional[str] = Field(None, pattern="^(monthly|biweekly|weekly)$")

class SavingsGoalCreate(BaseModel):
    name: str
    target_currency: str
    target_amount: float = Field(gt=0)
    current_saved: float = Field(0, ge=0)
    target_date: Optional[date] = None
    monthly_contribution: Optional[float] = Field(None, gt=0)

class SavingsGoalUpdate(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[float] = Field(None, gt=0)
    current_saved: Optional[float] = Field(None, ge=0)
    target_date: Optional[date] = None
    monthly_contribution: Optional[float] = Field(None, gt=0)


# === Debt Routes ===

@router.get("/debts")
async def list_debts(user_id: str = Depends(get_current_user)):
    """List all active debts for the current user."""
    return get_user_debts(user_id)

@router.post("/debts")
async def add_debt(data: DebtCreate, user_id: str = Depends(get_current_user)):
    """Create a new debt."""
    return create_debt(user_id, data.model_dump())

@router.put("/debts/{debt_id}")
async def modify_debt(debt_id: str, data: DebtUpdate, user_id: str = Depends(get_current_user)):
    """Update a debt."""
    result = update_debt(debt_id, user_id, data.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Debt not found")
    return result

@router.delete("/debts/{debt_id}")
async def remove_debt(debt_id: str, user_id: str = Depends(get_current_user)):
    """Delete a debt (soft delete)."""
    deleted = delete_debt(debt_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Debt not found")
    return {"status": "deleted"}


# === Income Routes ===

@router.get("/income")
async def list_income(user_id: str = Depends(get_current_user)):
    """List all active income sources for the current user."""
    return get_user_income(user_id)

@router.post("/income")
async def add_income(data: IncomeCreate, user_id: str = Depends(get_current_user)):
    """Create a new income source."""
    return create_income(user_id, data.model_dump())

@router.put("/income/{income_id}")
async def modify_income(income_id: str, data: IncomeUpdate, user_id: str = Depends(get_current_user)):
    """Update an income source."""
    result = update_income(income_id, user_id, data.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Income not found")
    return result

@router.delete("/income/{income_id}")
async def remove_income(income_id: str, user_id: str = Depends(get_current_user)):
    """Delete an income source (soft delete)."""
    deleted = delete_income(income_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Income not found")
    return {"status": "deleted"}


# === Savings Goals Routes ===

@router.get("/goals")
async def list_goals(user_id: str = Depends(get_current_user)):
    """List all active savings goals for the current user."""
    return get_user_savings_goals(user_id)

@router.post("/goals")
async def add_goal(data: SavingsGoalCreate, user_id: str = Depends(get_current_user)):
    """Create a new savings goal."""
    payload = data.model_dump()
    payload["target_date"] = payload["target_date"].isoformat() if payload["target_date"] else None
    return create_savings_goal(user_id, payload)

@router.put("/goals/{goal_id}")
async def modify_goal(goal_id: str, data: SavingsGoalUpdate, user_id: str = Depends(get_current_user)):
    """Update a savings goal."""
    payload = data.model_dump(exclude_unset=True)
    if "target_date" in payload and payload["target_date"] is not None:
        payload["target_date"] = payload["target_date"].isoformat()
    result = update_savings_goal(goal_id, user_id, payload)
    if not result:
        raise HTTPException(status_code=404, detail="Goal not found")
    return result

@router.delete("/goals/{goal_id}")
async def remove_goal(goal_id: str, user_id: str = Depends(get_current_user)):
    """Delete a savings goal (soft delete)."""
    deleted = delete_savings_goal(goal_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"status": "deleted"}


# === Timeline Routes ===

@router.get("/timeline/debts")
async def get_debt_timeline(user_id: str = Depends(get_current_user)):
    """Calculate debt payoff timeline for all active debts, and a
    USD-converted summary across all of them regardless of currency.
    """
    active_debts = [d for d in get_user_debts(user_id) if d.get("current_balance", 0) > 0]

    timelines = {}
    for debt in active_debts:
        try:
            timeline = calculate_debt_payoff(
                principal=debt["current_balance"],
                annual_rate=debt["interest_rate"],
                monthly_payment=debt["minimum_payment"],
            )
            timelines[debt["id"]] = {
                "debt": debt,
                "timeline": [
                    {
                        "month": p.month,
                        "payment": p.payment,
                        "interest": p.interest,
                        "principal": p.principal,
                        "remaining_balance": p.remaining_balance,
                    }
                    for p in timeline
                ],
                "months_to_payoff": len(timeline),
                "total_interest": sum(p.interest for p in timeline),
            }
        except ValueError as e:
            timelines[debt["id"]] = {"debt": debt, "error": str(e)}

    distinct_currencies = {d["currency_code"] for d in active_debts if d["currency_code"] != "USD"}
    rates = {c: get_current_rate(c) for c in distinct_currencies}
    rates = {c: r for c, r in rates.items() if r is not None}
    summary = calculate_total_debt_summary(active_debts, rates)

    return {
        "debts": timelines,
        "summary": summary,
    }

@router.get("/timeline/goals")
async def get_goals_timeline(user_id: str = Depends(get_current_user)):
    """Calculate savings timeline for all active goals. Uses each goal's
    own monthly_contribution if set; otherwise derives one from its
    target_date. A goal with neither reports an error rather than
    inventing a number.
    """
    goals = get_user_savings_goals(user_id)

    timelines = {}
    for goal in goals:
        remaining = goal["target_amount"] - goal.get("current_saved", 0)
        if remaining <= 0:
            timelines[goal["id"]] = {
                "goal": goal,
                "status": "completed",
                "months_to_goal": 0,
            }
            continue

        monthly_contribution = goal.get("monthly_contribution")
        if not monthly_contribution:
            target_date_str = goal.get("target_date")
            if not target_date_str:
                timelines[goal["id"]] = {
                    "goal": goal,
                    "error": "set a monthly contribution or a target date",
                }
                continue
            monthly_contribution = derive_monthly_contribution(
                target_amount=goal["target_amount"],
                current_saved=goal.get("current_saved", 0),
                target_date=date.fromisoformat(target_date_str),
            )

        try:
            timeline = calculate_savings_timeline(
                target_amount=goal["target_amount"],
                monthly_contribution=monthly_contribution,
                current_saved=goal.get("current_saved", 0),
            )
            timelines[goal["id"]] = {
                "goal": goal,
                "timeline": [
                    {
                        "month": e.month,
                        "date": e.date.isoformat(),
                        "balance": e.balance,
                        "progress": e.progress,
                    }
                    for e in timeline
                ],
                "months_to_goal": len(timeline),
                "monthly_contribution": monthly_contribution,
            }
        except ValueError as e:
            timelines[goal["id"]] = {"goal": goal, "error": str(e)}

    return {"goals": timelines}


# === Achievement Routes ===

@router.get("/achievements")
async def list_achievements(user_id: str = Depends(get_current_user)):
    """List all achievements for the current user."""
    return get_user_achievements(user_id)

@router.post("/achievements/check")
async def check_achievements(user_id: str = Depends(get_current_user)):
    """Check and award any new achievements. Sees inactive (paid-off)
    debts too -- first_debt_paid_off/financial_freedom depend on it.
    """
    debts = get_user_debts(user_id, include_inactive=True)
    goals = get_user_savings_goals(user_id)
    achievements = get_user_achievements(user_id)
    earned_badges = {a["badge_id"] for a in achievements}

    new_achievements = []
    new_achievements.extend(check_debt_achievements(debts, earned_badges))
    new_achievements.extend(check_savings_achievements(goals, earned_badges))

    streaks = get_user_streaks(user_id)
    if streaks:
        new_achievements.extend(check_streak_achievements(streaks, earned_badges))

    awarded = []
    for achievement in new_achievements:
        try:
            result = create_achievement(user_id, achievement)
            awarded.append(result)
        except Exception:
            pass  # Already earned (unique constraint)

    return {
        "new_achievements": awarded,
        "total_achievements": len(achievements) + len(awarded),
    }


# === Streak Routes ===

@router.get("/streaks")
async def list_streaks(user_id: str = Depends(get_current_user)):
    """Get streak data for the current user."""
    streaks = get_user_streaks(user_id)
    if not streaks:
        streaks = {
            "daily_checkin_current": 0,
            "daily_checkin_best": 0,
            "daily_checkin_last": None,
            "savings_current": 0,
            "savings_best": 0,
            "savings_last": None,
            "debt_payment_current": 0,
            "debt_payment_best": 0,
            "debt_payment_last": None,
        }
    return streaks

@router.post("/streaks/checkin")
async def record_checkin(user_id: str = Depends(get_current_user)):
    """Record a daily check-in and update streak."""
    streaks = get_user_streaks(user_id) or {}
    updated = update_streak(streaks, "daily_checkin")
    result = upsert_user_streaks(user_id, updated)

    achievements = get_user_achievements(user_id)
    earned_badges = {a["badge_id"] for a in achievements}
    new_achievements = check_streak_achievements(result, earned_badges)

    for achievement in new_achievements:
        try:
            create_achievement(user_id, achievement)
        except Exception:
            pass

    return {
        "streaks": result,
        "new_achievements": new_achievements,
    }


# === Badge Catalog ===

@router.get("/badges")
async def list_badges(user_id: str = Depends(get_current_user)):
    """List all available badges. Requires auth like every other route
    in this app, even though the catalog itself carries no user data --
    consistency, not a security requirement specific to this route.
    """
    return BADGES
