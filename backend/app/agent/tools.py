from app.news.supabase_rest import get_latest_news_sentiment
from app.recommendations.supabase_rest import (
    create_alert_for_user,
    delete_alert_for_user,
    get_latest_predictions,
    get_latest_recommendation,
    list_alerts_for_user,
    update_alert_for_user,
)

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_forecast",
            "description": "Get the forecast (predicted rate, confidence interval, confidence level) for 1 USD to a given currency at a given horizon.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quote_code": {"type": "string", "description": "3-letter currency code, e.g. 'EUR'"},
                    "horizon_days": {"type": "integer", "description": "Forecast horizon in days: 7, 30, 90, or 365"},
                },
                "required": ["quote_code", "horizon_days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news_summary",
            "description": "Get today's news-sentiment score and summary for a currency, if one has been scored today.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quote_code": {"type": "string", "description": "3-letter currency code, e.g. 'EUR'"},
                },
                "required": ["quote_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recommendation",
            "description": "Get the latest act_now/wait/volatile recommendation for 1 USD to a given currency.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quote_code": {"type": "string", "description": "3-letter currency code, e.g. 'EUR'"},
                },
                "required": ["quote_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_alert",
            "description": "Create a new alert for the current user on USD to a given currency. For alert_type 'threshold', threshold_rate and direction are required. For alert_type 'recommendation_change', omit both.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quote_code": {"type": "string", "description": "3-letter currency code, e.g. 'EUR'"},
                    "alert_type": {"type": "string", "enum": ["threshold", "recommendation_change"]},
                    "threshold_rate": {"type": "number", "description": "Required only for alert_type='threshold'"},
                    "direction": {"type": "string", "enum": ["above", "below"], "description": "Required only for alert_type='threshold'"},
                },
                "required": ["quote_code", "alert_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_alerts",
            "description": "List all alerts belonging to the current user.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_alert",
            "description": "Update an existing alert belonging to the current user. Only include the fields being changed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "alert_id": {"type": "string", "description": "The alert's id, from list_alerts"},
                    "threshold_rate": {"type": "number"},
                    "direction": {"type": "string", "enum": ["above", "below"]},
                    "is_active": {"type": "boolean"},
                },
                "required": ["alert_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_alert",
            "description": "Delete an alert belonging to the current user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "alert_id": {"type": "string", "description": "The alert's id, from list_alerts"},
                },
                "required": ["alert_id"],
            },
        },
    },
]


class ToolArgumentError(Exception):
    """Raised when a tool call's arguments are missing a required field.
    Caught by the orchestrator and fed back to the model as a tool-error
    message rather than crashing the whole chat turn -- a model mistake,
    not an infrastructure failure.
    """


def _require(arguments: dict, *keys: str) -> None:
    missing = [k for k in keys if k not in arguments]
    if missing:
        raise ToolArgumentError(f"missing required argument(s): {', '.join(missing)}")


def call_tool(name: str, arguments: dict, user_id: str) -> dict:
    """Dispatches a model-requested tool call to its implementation.
    `user_id` comes from the authenticated request, never from the
    model's own arguments (even if the model is asked to pass one, or
    tries to) -- the alert tools use this parameter, not anything in
    `arguments`, to scope every read and write, so the agent can never
    see or touch another user's alerts.
    """
    if name == "get_forecast":
        _require(arguments, "quote_code", "horizon_days")
        predictions = get_latest_predictions(arguments["quote_code"])
        match = next(
            (p for p in predictions if p["horizon_days"] == arguments["horizon_days"]), None
        )
        if match is None:
            return {
                "error": f"no forecast available for {arguments['quote_code']} "
                f"at horizon {arguments['horizon_days']}"
            }
        return match

    if name == "get_news_summary":
        _require(arguments, "quote_code")
        sentiment = get_latest_news_sentiment(arguments["quote_code"])
        if sentiment is None:
            return {"error": f"no news sentiment scored today for {arguments['quote_code']}"}
        return sentiment

    if name == "get_recommendation":
        _require(arguments, "quote_code")
        recommendation = get_latest_recommendation(arguments["quote_code"])
        if recommendation is None:
            return {"error": f"no recommendation available yet for {arguments['quote_code']}"}
        return recommendation

    if name == "create_alert":
        _require(arguments, "quote_code", "alert_type")
        return create_alert_for_user(
            user_id,
            arguments["quote_code"],
            arguments["alert_type"],
            arguments.get("threshold_rate"),
            arguments.get("direction"),
        )

    if name == "list_alerts":
        return {"alerts": list_alerts_for_user(user_id)}

    if name == "update_alert":
        _require(arguments, "alert_id")
        fields = {
            k: v for k, v in arguments.items() if k in ("threshold_rate", "direction", "is_active")
        }
        updated = update_alert_for_user(user_id, arguments["alert_id"], fields)
        if updated is None:
            return {"error": "no alert with that id belongs to you"}
        return updated

    if name == "delete_alert":
        _require(arguments, "alert_id")
        deleted = delete_alert_for_user(user_id, arguments["alert_id"])
        if not deleted:
            return {"error": "no alert with that id belongs to you"}
        return {"deleted": True}

    raise ValueError(f"unknown tool: {name}")
