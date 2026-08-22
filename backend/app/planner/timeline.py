# backend/app/planner/timeline.py
"""Timeline calculation engine for debt payoff and savings progress."""
from datetime import date, timedelta
from dataclasses import dataclass


@dataclass
class DebtPayment:
    month: int
    payment: float
    interest: float
    principal: float
    remaining_balance: float


@dataclass
class SavingsEntry:
    month: int
    date: date
    balance: float
    progress: float


def calculate_debt_payoff(
    principal: float,
    annual_rate: float,
    monthly_payment: float,
    start_date: date | None = None,
) -> list[DebtPayment]:
    """Calculate month-by-month debt payoff with compound interest.
    
    Args:
        principal: Current debt balance
        annual_rate: Annual interest rate (e.g. 0.05 for 5%)
        monthly_payment: Monthly payment amount
        start_date: Optional start date for timeline
    
    Returns:
        List of monthly payment details until debt is paid off
    """
    if principal <= 0:
        return []
    
    if monthly_payment <= 0:
        raise ValueError("Monthly payment must be positive")
    
    payments = []
    balance = principal
    monthly_rate = annual_rate / 12
    month = 0
    
    while balance > 0.01 and month < 600:  # 50 year cap, $0.01 threshold
        month += 1
        interest = balance * monthly_rate
        
        # Ensure payment covers at least the interest
        if monthly_payment <= interest:
            raise ValueError(
                f"Monthly payment ({monthly_payment}) must exceed monthly interest ({interest:.2f})"
            )
        
        principal_paid = min(monthly_payment - interest, balance)
        balance -= principal_paid
        
        payments.append(DebtPayment(
            month=month,
            payment=monthly_payment,
            interest=round(interest, 2),
            principal=round(principal_paid, 2),
            remaining_balance=round(max(0, balance), 2),
        ))
    
    return payments


def calculate_savings_timeline(
    target_amount: float,
    monthly_contribution: float,
    current_saved: float = 0,
    start_date: date | None = None,
) -> list[SavingsEntry]:
    """Calculate month-by-month savings progress.
    
    Args:
        target_amount: Savings goal amount
        monthly_contribution: Monthly savings contribution
        current_saved: Current savings balance
        start_date: Optional start date for timeline
    
    Returns:
        List of monthly savings entries until goal is reached
    """
    if target_amount <= 0:
        raise ValueError("Target amount must be positive")
    
    if monthly_contribution <= 0:
        raise ValueError("Monthly contribution must be positive")
    
    if current_saved >= target_amount:
        return [SavingsEntry(
            month=0,
            date=start_date or date.today(),
            balance=current_saved,
            progress=1.0,
        )]
    
    timeline = []
    balance = current_saved
    month = 0
    base_date = start_date or date.today()
    
    while balance < target_amount and month < 600:
        month += 1
        balance += monthly_contribution
        
        timeline.append(SavingsEntry(
            month=month,
            date=base_date + timedelta(days=30 * month),
            balance=round(min(balance, target_amount), 2),
            progress=round(min(balance / target_amount, 1.0), 4),
        ))
    
    return timeline


def calculate_forex_impact(
    debt_amount: float,
    debt_currency: str,
    income_currency: str,
    current_rate: float,
    predicted_rate: float,
) -> dict:
    """Calculate how forex timing affects debt cost.
    
    Args:
        debt_amount: Amount of debt in debt_currency
        debt_currency: Currency of the debt
        income_currency: Currency of income
        current_rate: Current exchange rate (income_currency per debt_currency)
        predicted_rate: Predicted exchange rate
    
    Returns:
        Dictionary with cost analysis and recommendation
    """
    if current_rate <= 0 or predicted_rate <= 0:
        raise ValueError("Exchange rates must be positive")
    
    current_cost = debt_amount / current_rate
    predicted_cost = debt_amount / predicted_rate
    savings = current_cost - predicted_cost
    
    return {
        "debt_amount": debt_amount,
        "debt_currency": debt_currency,
        "income_currency": income_currency,
        "current_rate": current_rate,
        "predicted_rate": predicted_rate,
        "current_cost": round(current_cost, 2),
        "predicted_cost": round(predicted_cost, 2),
        "potential_savings": round(savings, 2),
        "recommendation": "wait" if savings > 0 else "act_now",
        "savings_percentage": round(abs(savings) / current_cost * 100, 2),
    }


def calculate_total_debt_summary(debts: list[dict]) -> dict:
    """Calculate summary statistics for all debts.
    
    Args:
        debts: List of debt dictionaries with current_balance, interest_rate, etc.
    
    Returns:
        Summary dictionary with totals and averages
    """
    if not debts:
        return {
            "total_balance": 0,
            "total_minimum_payment": 0,
            "weighted_average_rate": 0,
            "debt_count": 0,
        }
    
    total_balance = sum(d["current_balance"] for d in debts)
    total_payment = sum(d["minimum_payment"] for d in debts)
    
    # Weighted average interest rate
    if total_balance > 0:
        weighted_rate = sum(
            d["interest_rate"] * d["current_balance"] / total_balance
            for d in debts
        )
    else:
        weighted_rate = 0
    
    return {
        "total_balance": round(total_balance, 2),
        "total_minimum_payment": round(total_payment, 2),
        "weighted_average_rate": round(weighted_rate, 4),
        "debt_count": len(debts),
    }
