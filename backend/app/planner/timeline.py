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
        annual_rate: Annual interest rate as a plain percentage (e.g. 5.5
            for 5.5% APR) -- matches how the frontend takes and displays
            this value; the conversion to a monthly fraction happens here.
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
    monthly_rate = (annual_rate / 100) / 12
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


def derive_monthly_contribution(
    target_amount: float,
    current_saved: float,
    target_date: date,
    today: date | None = None,
) -> float:
    """Derives the monthly contribution needed to reach `target_amount`
    by `target_date`, given `current_saved` already saved -- used when a
    savings goal has a target date but no explicit monthly_contribution,
    instead of fabricating an arbitrary percentage.

    Uses a calendar-month difference (not the 30-day-month stepping
    calculate_savings_timeline uses internally for its own date column --
    that's a display convenience, this is the actual requirement), floored
    at 1 month so a same-month or past target date doesn't divide by zero.
    """
    today = today or date.today()
    months = max(1, (target_date.year - today.year) * 12 + (target_date.month - today.month))
    remaining = max(0.0, target_amount - current_saved)
    return remaining / months


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


def calculate_total_debt_summary(debts: list[dict], rates: dict[str, float]) -> dict:
    """Calculate summary statistics for all debts, converting each debt's
    balance and minimum payment to USD (this app's pivot currency) before
    summing -- debts can be in different currencies, so a raw sum is
    meaningless. `rates` maps currency_code -> units of that currency per
    1 USD (matching app.recommendations.supabase_rest.get_current_rate's
    convention); a USD debt needs no lookup. A debt whose currency has no
    entry in `rates` (no rates_cache data yet) is excluded from the totals
    and listed in currencies_missing_rate instead of silently
    under-reporting with no explanation.

    Args:
        debts: List of debt dictionaries with current_balance,
            interest_rate, minimum_payment, currency_code
        rates: currency_code -> USD exchange rate (units of that currency
            per 1 USD)

    Returns:
        Summary dictionary with totals and averages, all in USD
    """
    if not debts:
        return {
            "total_balance": 0,
            "total_minimum_payment": 0,
            "weighted_average_rate": 0,
            "debt_count": 0,
            "currencies_missing_rate": [],
        }

    total_balance = 0.0
    total_payment = 0.0
    missing_currencies: set[str] = set()
    weighted_rate_numerator = 0.0
    converted_balance_sum = 0.0

    for d in debts:
        currency = d["currency_code"]
        rate = 1.0 if currency == "USD" else rates.get(currency)
        if rate is None:
            missing_currencies.add(currency)
            continue
        balance_usd = d["current_balance"] / rate
        payment_usd = d["minimum_payment"] / rate
        total_balance += balance_usd
        total_payment += payment_usd
        weighted_rate_numerator += d["interest_rate"] * balance_usd
        converted_balance_sum += balance_usd

    weighted_rate = (
        weighted_rate_numerator / converted_balance_sum if converted_balance_sum > 0 else 0
    )

    return {
        "total_balance": round(total_balance, 2),
        "total_minimum_payment": round(total_payment, 2),
        "weighted_average_rate": round(weighted_rate, 4),
        "debt_count": len(debts),
        "currencies_missing_rate": sorted(missing_currencies),
    }
