import httpx

from app.config import get_settings

BATCH_SIZE = 500


def _headers(prefer: str | None = None) -> dict:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_key,
        "Authorization": f"Bearer {settings.supabase_service_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def get_latest_predictions(quote_code: str) -> list[dict]:
    """Returns the most recent forecast batch for (base_code='USD',
    quote_code=<quote_code>) -- up to 4 rows, one per horizon. Finds the
    exact latest generated_at first, then fetches only rows stamped with
    that exact value, so a currency with fewer than 4 horizons written
    today never gets padded out with a stale row from a previous day.
    """
    settings = get_settings()
    latest_response = httpx.get(
        f"{settings.supabase_url}/rest/v1/predictions",
        params={
            "select": "generated_at",
            "base_code": "eq.USD",
            "quote_code": f"eq.{quote_code}",
            "order": "generated_at.desc",
            "limit": 1,
        },
        headers=_headers(),
        timeout=30.0,
    )
    latest_response.raise_for_status()
    latest_rows = latest_response.json()
    if not latest_rows:
        return []
    latest_generated_at = latest_rows[0]["generated_at"]

    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/predictions",
        params={
            "select": "horizon_days,predicted_rate,lower_bound,upper_bound,confidence",
            "base_code": "eq.USD",
            "quote_code": f"eq.{quote_code}",
            "generated_at": f"eq.{latest_generated_at}",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return [
        {
            "horizon_days": row["horizon_days"],
            "predicted_rate": float(row["predicted_rate"]),
            "lower_bound": float(row["lower_bound"]),
            "upper_bound": float(row["upper_bound"]),
            "confidence": row["confidence"],
        }
        for row in rows
    ]


def get_current_rate(quote_code: str) -> float | None:
    """Returns the most recent USD-pivot rate for `quote_code` from
    rates_cache, or None if no rate exists yet.
    """
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/rates_cache",
        params={
            "select": "rate",
            "base_code": "eq.USD",
            "quote_code": f"eq.{quote_code}",
            "order": "as_of.desc",
            "limit": 1,
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return float(rows[0]["rate"]) if rows else None


def get_directed_rate(base_code: str, quote_code: str) -> float | None:
    """Returns the current rate for an arbitrary directed pair, resolving
    through the USD pivot when neither side is USD. Mirrors the §3
    reciprocal-direction logic used for recommendations, applied to
    whichever pair an alert names.
    """
    if base_code == quote_code:
        return 1.0
    if base_code == "USD":
        return get_current_rate(quote_code)
    if quote_code == "USD":
        base_rate = get_current_rate(base_code)
        return 1 / base_rate if base_rate is not None else None
    base_rate = get_current_rate(base_code)
    quote_rate = get_current_rate(quote_code)
    if base_rate is None or quote_rate is None:
        return None
    return quote_rate / base_rate


def insert_recommendations(rows: list[dict]) -> None:
    """Appends a batch of recommendation rows. Plain insert, not upsert --
    recommendations has no unique constraint, matching predictions'
    append-only pattern (needed so recommendation_change alerts can
    compare today's row against the prior one).
    """
    settings = get_settings()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        response = httpx.post(
            f"{settings.supabase_url}/rest/v1/recommendations",
            headers=_headers(),
            json=batch,
            timeout=60.0,
        )
        response.raise_for_status()


def get_active_alerts() -> list[dict]:
    """Returns all alerts with is_active=true."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/alerts",
        params={
            "select": "id,base_code,quote_code,alert_type,threshold_rate,direction",
            "is_active": "eq.true",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def get_latest_two_recommendations(base_code: str, quote_code: str) -> list[str]:
    """Returns up to the 2 most recent `recommendation` values for a
    directed pair, newest first -- used to detect a recommendation_change.
    """
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/recommendations",
        params={
            "select": "recommendation",
            "base_code": f"eq.{base_code}",
            "quote_code": f"eq.{quote_code}",
            "order": "generated_at.desc",
            "limit": 2,
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return [row["recommendation"] for row in response.json()]


def record_alert_event(alert_id: str, details: dict) -> None:
    settings = get_settings()
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/alert_events",
        headers=_headers(),
        json=[{"alert_id": alert_id, "details": details}],
        timeout=30.0,
    )
    response.raise_for_status()


def deactivate_alert(alert_id: str) -> None:
    settings = get_settings()
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/alerts",
        params={"id": f"eq.{alert_id}"},
        headers=_headers(),
        json={"is_active": False},
        timeout=30.0,
    )
    response.raise_for_status()


def get_latest_recommendation(quote_code: str) -> dict | None:
    """Returns the most recent recommendation row for (base_code='USD',
    quote_code=<quote_code>), or None if none exists yet. Used by the
    LLM agent's get_recommendation tool.
    """
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/recommendations",
        params={
            "select": "recommendation,current_rate,expected_rate,lower_bound,upper_bound,reference_horizon_days,generated_at",
            "base_code": "eq.USD",
            "quote_code": f"eq.{quote_code}",
            "order": "generated_at.desc",
            "limit": 1,
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None
    row = rows[0]
    return {
        "recommendation": row["recommendation"],
        "current_rate": float(row["current_rate"]),
        "expected_rate": float(row["expected_rate"]),
        "lower_bound": float(row["lower_bound"]),
        "upper_bound": float(row["upper_bound"]),
        "reference_horizon_days": row["reference_horizon_days"],
        "generated_at": row["generated_at"],
    }


def create_alert_for_user(
    user_id: str,
    quote_code: str,
    alert_type: str,
    threshold_rate: float | None,
    direction: str | None,
) -> dict:
    """Creates a new alert owned by `user_id`, base_code always 'USD'
    (confirmed live -- every predictions/rates_cache row uses USD as
    base). Used by the LLM agent's create_alert tool.
    """
    settings = get_settings()
    payload = {
        "user_id": user_id,
        "base_code": "USD",
        "quote_code": quote_code,
        "alert_type": alert_type,
        "threshold_rate": threshold_rate,
        "direction": direction,
    }
    response = httpx.post(
        f"{settings.supabase_url}/rest/v1/alerts",
        headers=_headers(prefer="return=representation"),
        json=payload,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()[0]


def list_alerts_for_user(user_id: str) -> list[dict]:
    """Used by the LLM agent's list_alerts tool."""
    settings = get_settings()
    response = httpx.get(
        f"{settings.supabase_url}/rest/v1/alerts",
        params={
            "select": "id,base_code,quote_code,alert_type,threshold_rate,direction,is_active,created_at",
            "user_id": f"eq.{user_id}",
            "order": "created_at.desc",
        },
        headers=_headers(),
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def update_alert_for_user(user_id: str, alert_id: str, fields: dict) -> dict | None:
    """`fields` may contain any of threshold_rate/direction/is_active.
    Filters by both id and user_id in the same request -- ownership is
    enforced atomically by the filter itself, not by a separate
    check-then-act query (which would have a race between the check and
    the update). Returns the updated row, or None if no alert with
    `alert_id` belongs to `user_id` -- PostgREST simply matches zero
    rows rather than erroring, so the LLM agent's update_alert tool
    reports this as "not found" rather than raising. Used by the LLM
    agent's update_alert tool.
    """
    settings = get_settings()
    # Filter fields to only allowed keys to prevent column-injection attacks
    allowed_fields = {k: v for k, v in fields.items() if k in ("threshold_rate", "direction", "is_active")}
    response = httpx.patch(
        f"{settings.supabase_url}/rest/v1/alerts",
        params={"id": f"eq.{alert_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        json=allowed_fields,
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def delete_alert_for_user(user_id: str, alert_id: str) -> bool:
    """Returns True if an alert was deleted, False if none matched
    (either it doesn't exist or belongs to another user) -- same
    atomic-filter reasoning as update_alert_for_user. Used by the LLM
    agent's delete_alert tool.
    """
    settings = get_settings()
    response = httpx.delete(
        f"{settings.supabase_url}/rest/v1/alerts",
        params={"id": f"eq.{alert_id}", "user_id": f"eq.{user_id}"},
        headers=_headers(prefer="return=representation"),
        timeout=30.0,
    )
    response.raise_for_status()
    return len(response.json()) > 0
