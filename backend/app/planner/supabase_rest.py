# backend/app/planner/supabase_rest.py
"""Supabase REST accessors for the planner module."""
from datetime import datetime, timezone
import httpx
from app.config import get_settings


def _headers(prefer: str | None = None) -> dict:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


# === Debts CRUD ===

def get_user_debts(user_id: str, include_inactive: bool = False) -> list[dict]:
    """Get debts for a user. Active only by default; pass
    include_inactive=True to also see paid-off/deleted debts (needed by
    achievement-checking, which awards badges for paid-off debts).
    """
    settings = get_settings()
    params = {"user_id": f"eq.{user_id}", "order": "created_at.desc"}
    if not include_inactive:
        params["is_active"] = "eq.true"
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/debts",
        params=params,
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def create_debt(user_id: str, data: dict) -> dict:
    """Create a new debt for a user."""
    settings = get_settings()
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/debts",
        headers=_headers(prefer="return=representation"),
        json={**data, "user_id": user_id},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()[0]


def update_debt(debt_id: str, user_id: str, data: dict) -> dict | None:
    """Update a debt (only if owned by user). `currency_code` is
    deliberately not in the allowlist -- a debt's currency is fixed at
    creation, matching how create_alert_for_user treats base_code/
    quote_code.
    """
    allowed_fields = {
        k: v for k, v in data.items()
        if k in ("name", "current_balance", "interest_rate", "minimum_payment", "due_day")
    }
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/debts",
        params={"id": f"eq.{debt_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        json=allowed_fields,
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def delete_debt(debt_id: str, user_id: str) -> bool:
    """Soft-delete a debt (set is_active=false). Returns True if a row
    was updated, False if none matched (doesn't exist or belongs to
    another user).
    """
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/debts",
        params={"id": f"eq.{debt_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        json={"is_active": False},
        timeout=30.0,
    )
    response.raise_for_status()
    return len(response.json()) > 0


# === Income CRUD ===

def get_user_income(user_id: str, include_inactive: bool = False) -> list[dict]:
    """Get income sources for a user. Active only by default."""
    settings = get_settings()
    params = {"user_id": f"eq.{user_id}", "order": "created_at.desc"}
    if not include_inactive:
        params["is_active"] = "eq.true"
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/income",
        params=params,
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def create_income(user_id: str, data: dict) -> dict:
    """Create a new income source for a user."""
    settings = get_settings()
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/income",
        headers=_headers(prefer="return=representation"),
        json={**data, "user_id": user_id},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()[0]


def update_income(income_id: str, user_id: str, data: dict) -> dict | None:
    """Update an income source (only if owned by user)."""
    allowed_fields = {
        k: v for k, v in data.items() if k in ("name", "amount", "frequency")
    }
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/income",
        params={"id": f"eq.{income_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        json=allowed_fields,
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def delete_income(income_id: str, user_id: str) -> bool:
    """Soft-delete an income source. Returns True if a row was updated."""
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/income",
        params={"id": f"eq.{income_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        json={"is_active": False},
        timeout=30.0,
    )
    response.raise_for_status()
    return len(response.json()) > 0


# === Savings Goals CRUD ===

def get_user_savings_goals(user_id: str, include_inactive: bool = False) -> list[dict]:
    """Get savings goals for a user. Active only by default."""
    settings = get_settings()
    params = {"user_id": f"eq.{user_id}", "order": "created_at.desc"}
    if not include_inactive:
        params["is_active"] = "eq.true"
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/savings_goals",
        params=params,
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def create_savings_goal(user_id: str, data: dict) -> dict:
    """Create a new savings goal for a user."""
    settings = get_settings()
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/savings_goals",
        headers=_headers(prefer="return=representation"),
        json={**data, "user_id": user_id},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()[0]


def update_savings_goal(goal_id: str, user_id: str, data: dict) -> dict | None:
    """Update a savings goal (only if owned by user)."""
    allowed_fields = {
        k: v for k, v in data.items()
        if k in ("name", "target_amount", "current_saved", "target_date", "monthly_contribution")
    }
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/savings_goals",
        params={"id": f"eq.{goal_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        json=allowed_fields,
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def delete_savings_goal(goal_id: str, user_id: str) -> bool:
    """Soft-delete a savings goal. Returns True if a row was updated."""
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/savings_goals",
        params={"id": f"eq.{goal_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        json={"is_active": False},
        timeout=30.0,
    )
    response.raise_for_status()
    return len(response.json()) > 0


# === Achievements ===

def get_user_achievements(user_id: str) -> list[dict]:
    """Get all achievements for a user."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/achievements",
        params={
            "user_id": f"eq.{user_id}",
            "order": "earned_at.desc",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def create_achievement(user_id: str, data: dict) -> dict:
    """Create a new achievement for a user. `data` is expected to already
    be shaped {"badge_id": str, "metadata": dict | None} by
    app.planner.achievements' check_*_achievements functions.
    """
    settings = get_settings()
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/achievements",
        headers=_headers(prefer="return=representation"),
        json={**data, "user_id": user_id},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()[0]


# === Streaks ===

def get_user_streaks(user_id: str) -> dict | None:
    """Get streak data for a user."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/streaks",
        params={"user_id": f"eq.{user_id}"},
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def upsert_user_streaks(user_id: str, data: dict) -> dict:
    """Create or update streak data for a user."""
    settings = get_settings()
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/streaks",
        headers=_headers(prefer="return=representation,resolution=merge-duplicates"),
        json={**data, "user_id": user_id},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()[0]
