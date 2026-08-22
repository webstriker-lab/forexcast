import json

from app.agent.crypto import decrypt_api_key
from app.agent.providers import call_chat_completion
from app.agent.supabase_rest import get_llm_settings
from app.agent.tools import TOOL_SCHEMAS, ToolArgumentError, call_tool

MAX_TOOL_ITERATIONS = 5

SYSTEM_PROMPT = (
    "You are ForexCast's assistant. You have tools to check live "
    "forecasts, news sentiment, recommendations, and to manage the "
    "user's alerts. Always call a tool to get real numbers rather than "
    "guessing or inventing them. If a tool reports no data is "
    "available, say so plainly instead of making something up."
)


class LLMNotConfiguredError(Exception):
    """Raised when the user has no llm_settings row yet -- a normal
    first-time-user state, not a server error."""


class ToolLoopExceededError(Exception):
    """Raised when MAX_TOOL_ITERATIONS is exhausted without a final
    (non-tool-call) answer -- either a confused model or a tool-schema
    bug worth surfacing, not something to paper over by truncating."""


def run_chat(user_id: str, messages: list[dict]) -> dict:
    """Runs one chat turn: loads the user's LLM provider config,
    decrypts their API key, and drives the tool-calling loop until the
    model returns a final answer (no more tool_calls) or
    MAX_TOOL_ITERATIONS is exhausted.

    Returns {"message": {"role": "assistant", "content": str},
    "tool_calls": [{"tool": str, "arguments": dict, "result": ...}]} --
    tool_calls is always present (empty list if none were made) so the
    caller can show what the agent actually checked.
    """
    settings_row = get_llm_settings(user_id)
    if settings_row is None:
        raise LLMNotConfiguredError(
            "No LLM provider configured -- set one up in Settings first"
        )
    api_key = decrypt_api_key(settings_row["api_key_encrypted"])
    provider = settings_row["provider"]
    model = settings_row.get("model")

    conversation = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
    tool_call_log = []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = call_chat_completion(provider, api_key, model, conversation, TOOL_SCHEMAS)
        try:
            choice = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(
                f"provider returned an unexpected response shape: {response}"
            ) from exc
        tool_calls = choice.get("tool_calls")
        if not tool_calls:
            return {
                "message": {"role": "assistant", "content": choice.get("content") or ""},
                "tool_calls": tool_call_log,
            }
        conversation.append(choice)
        for call in tool_calls:
            fn = call["function"]
            try:
                arguments = json.loads(fn["arguments"])
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be a JSON object")
            except (json.JSONDecodeError, ValueError):
                arguments = {}
                result = {"error": "arguments were not valid JSON"}
            else:
                try:
                    result = call_tool(fn["name"], arguments, user_id)
                except (ToolArgumentError, ValueError) as exc:
                    result = {"error": str(exc)}
            tool_call_log.append({"tool": fn["name"], "arguments": arguments, "result": result})
            conversation.append(
                {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)}
            )

    raise ToolLoopExceededError(
        f"exceeded {MAX_TOOL_ITERATIONS} tool-calling iterations without a final answer"
    )
