from unittest.mock import patch

import pytest

from app.agent.orchestrator import (
    MAX_TOOL_ITERATIONS,
    LLMNotConfiguredError,
    ToolLoopExceededError,
    run_chat,
)


def _settings_row():
    return {"provider": "openrouter", "api_key_encrypted": "ciphertext", "model": None}


def _final_answer_response(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _tool_call_response(tool_name: str, arguments_json: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "call_1", "type": "function", "function": {"name": tool_name, "arguments": arguments_json}}
                    ],
                }
            }
        ]
    }


def test_run_chat_raises_when_user_has_no_llm_settings():
    with patch("app.agent.orchestrator.get_llm_settings", return_value=None):
        with pytest.raises(LLMNotConfiguredError):
            run_chat("u1", [{"role": "user", "content": "hi"}])


def test_run_chat_returns_immediate_answer_when_no_tool_calls():
    with patch("app.agent.orchestrator.get_llm_settings", return_value=_settings_row()), patch(
        "app.agent.orchestrator.decrypt_api_key", return_value="plain-key"
    ), patch(
        "app.agent.orchestrator.call_chat_completion",
        return_value=_final_answer_response("Hi there!"),
    ) as mock_call:
        result = run_chat("u1", [{"role": "user", "content": "hi"}])

    assert result["message"] == {"role": "assistant", "content": "Hi there!"}
    assert result["tool_calls"] == []
    assert mock_call.call_count == 1


def test_run_chat_executes_a_tool_call_then_returns_the_final_answer():
    responses = [
        _tool_call_response("get_forecast", '{"quote_code": "EUR", "horizon_days": 30}'),
        _final_answer_response("EUR is forecast at 1.10"),
    ]
    with patch("app.agent.orchestrator.get_llm_settings", return_value=_settings_row()), patch(
        "app.agent.orchestrator.decrypt_api_key", return_value="plain-key"
    ), patch(
        "app.agent.orchestrator.call_chat_completion", side_effect=responses
    ), patch(
        "app.agent.orchestrator.call_tool", return_value={"predicted_rate": 1.10}
    ) as mock_tool:
        result = run_chat("u1", [{"role": "user", "content": "what's the EUR forecast?"}])

    assert result["message"]["content"] == "EUR is forecast at 1.10"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["tool"] == "get_forecast"
    assert result["tool_calls"][0]["result"] == {"predicted_rate": 1.10}
    mock_tool.assert_called_once_with("get_forecast", {"quote_code": "EUR", "horizon_days": 30}, "u1")


def test_run_chat_feeds_back_a_tool_error_on_malformed_json_arguments():
    responses = [
        _tool_call_response("get_forecast", "not valid json"),
        _final_answer_response("Let me try again"),
    ]
    with patch("app.agent.orchestrator.get_llm_settings", return_value=_settings_row()), patch(
        "app.agent.orchestrator.decrypt_api_key", return_value="plain-key"
    ), patch(
        "app.agent.orchestrator.call_chat_completion", side_effect=responses
    ) as mock_call, patch("app.agent.orchestrator.call_tool") as mock_tool:
        result = run_chat("u1", [{"role": "user", "content": "hi"}])

    mock_tool.assert_not_called()
    assert result["tool_calls"][0]["result"] == {"error": "arguments were not valid JSON"}
    second_call_messages = mock_call.call_args_list[1].args[3]
    assert second_call_messages[-1]["role"] == "tool"


def test_run_chat_feeds_back_a_tool_error_from_tool_argument_error():
    from app.agent.tools import ToolArgumentError

    responses = [
        _tool_call_response("get_forecast", "{}"),
        _final_answer_response("Let me try again"),
    ]
    with patch("app.agent.orchestrator.get_llm_settings", return_value=_settings_row()), patch(
        "app.agent.orchestrator.decrypt_api_key", return_value="plain-key"
    ), patch(
        "app.agent.orchestrator.call_chat_completion", side_effect=responses
    ), patch(
        "app.agent.orchestrator.call_tool", side_effect=ToolArgumentError("missing required argument(s): quote_code")
    ):
        result = run_chat("u1", [{"role": "user", "content": "hi"}])

    assert "missing required argument" in result["tool_calls"][0]["result"]["error"]


def test_run_chat_raises_after_exceeding_max_tool_iterations():
    responses = [
        _tool_call_response("get_forecast", '{"quote_code": "EUR", "horizon_days": 30}')
        for _ in range(MAX_TOOL_ITERATIONS)
    ]
    with patch("app.agent.orchestrator.get_llm_settings", return_value=_settings_row()), patch(
        "app.agent.orchestrator.decrypt_api_key", return_value="plain-key"
    ), patch(
        "app.agent.orchestrator.call_chat_completion", side_effect=responses
    ), patch("app.agent.orchestrator.call_tool", return_value={"predicted_rate": 1.10}):
        with pytest.raises(ToolLoopExceededError):
            run_chat("u1", [{"role": "user", "content": "hi"}])
