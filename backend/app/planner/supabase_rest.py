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

def get_user_debts(user_id: str) -> list[dict]:
    """Get all active debts for a user."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/debts",
        params={
            "user_id": f"eq.{user_id}",
            "order": "created_at.desc",
        },
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
    """Update a debt (only if owned by user)."""
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/debts",
        params={"id": f"eq.{debt_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        json=data,
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def delete_debt(debt_id: str, user_id: str) -> bool:
    """Soft-delete a debt (set is_active=false)."""
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/debts",
        params={"id": f"eq.{debt_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(),
        json={"is_active": False},
        timeout=30.0,
    )
    response.raise_for_status()
    return True


# === Income CRUD ===

def get_user_income(user_id: str) -> list[dict]:
    """Get all active income sources for a user."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/income",
        params={
            "user_id": f"eq.{user_id}",
            "order": "created_at.desc",
        },
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
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/income",
        params={"id": f"eq.{income_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        json=data,
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def delete_income(income_id: str, user_id: str) -> bool:
    """Soft-delete an income source (set is_active=false)."""
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/income",
        params={"id": f"eq.{income_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(),
        json={"is_active": False},
        timeout=30.0,
    )
    response.raise_for_status()
    return True


# === Savings Goals CRUD ===

def get_user_savings_goals(user_id: str) -> list[dict]:
    """Get all savings goals for a user."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/savings_goals",
        params={
            "user_id": f"eq.{user_id}",
            "order": "created_at.desc",
        },
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
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/savings_goals",
        params={"id": f"eq.{goal_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        json=data,
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def delete_savings_goal(goal_id: str, user_id: str) -> bool:
    """Soft-delete a savings goal (set is_active=false)."""
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/savings_goals",
        params={"id": f"eq.{goal_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(),
        json={"is_active": False},
        timeout=30.0,
    )
    response.raise_for_status()
    return True


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
    """Create a new achievement for a user."""
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
