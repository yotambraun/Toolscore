"""OpenAI Responses API: extraction, auto-detection and trace files.

Uses the real ``openai`` SDK types when the SDK is installed.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from toolscore import evaluate, from_openai_responses
from toolscore.core import evaluate_trace
from toolscore.integrations import auto_extract

if TYPE_CHECKING:
    from pathlib import Path


def _response_dict(output: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 1_760_000_000,
        "model": "gpt-6-luna",
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }


FUNCTION_CALL = {
    "type": "function_call",
    "id": "fc_1",
    "call_id": "call_1",
    "name": "get_weather",
    "arguments": '{"city": "Paris", "unit": "c"}',
    "status": "completed",
}
MESSAGE = {
    "type": "message",
    "id": "msg_1",
    "role": "assistant",
    "status": "completed",
    "content": [{"type": "output_text", "text": "Checking.", "annotations": []}],
}


def test_real_sdk_response_object_works_with_evaluate() -> None:
    responses = pytest.importorskip("openai.types.responses")
    response = responses.Response.model_validate(_response_dict([MESSAGE, FUNCTION_CALL]))
    result = evaluate(
        expected=[{"tool": "get_weather", "args": {"city": "Paris", "unit": "c"}}],
        actual=response,
    )
    assert result.score == 1.0
    assert from_openai_responses(response) == [
        {"tool": "get_weather", "args": {"city": "Paris", "unit": "c"}, "id": "call_1"}
    ]


def test_real_sdk_mcp_call_keeps_output_and_error() -> None:
    responses = pytest.importorskip("openai.types.responses")
    mcp_ok = {
        "type": "mcp_call",
        "id": "mcp_1",
        "name": "search_docs",
        "server_label": "docs",
        "arguments": '{"q": "mcp"}',
        "output": "3 results",
    }
    mcp_failed = {
        "type": "mcp_call",
        "id": "mcp_2",
        "name": "delete_doc",
        "server_label": "docs",
        "arguments": "{}",
        # The SDK types ``McpCall.error`` as a string (openai 2.41); the typed error
        # object some payloads carry is covered with plain dicts below.
        "error": "doc not found",
    }
    response = responses.Response.model_validate(_response_dict([mcp_ok, mcp_failed]))
    calls = from_openai_responses(response)
    assert calls[0] == {
        "tool": "search_docs",
        "args": {"q": "mcp"},
        "id": "mcp_1",
        "result": "3 results",
    }
    assert calls[1]["error"] == "doc not found"


def test_input_item_list_pairs_outputs_and_errors_by_call_id() -> None:
    items = [
        {"role": "user", "content": "weather in Paris and Rome?"},
        FUNCTION_CALL,
        {**FUNCTION_CALL, "id": "fc_2", "call_id": "call_2", "arguments": '{"city": "Rome"}'},
        {"type": "function_call_output", "call_id": "call_1", "output": '{"temp": 18}'},
        {
            "type": "function_call_output",
            "call_id": "call_2",
            "output": "An error occurred while running the tool. Please try again. Error: timeout",
        },
    ]
    calls = auto_extract(items)
    assert [c["tool"] for c in calls] == ["get_weather", "get_weather"]
    assert calls[0]["result"] == '{"temp": 18}'
    assert "error" not in calls[0]
    assert calls[1]["error"].endswith("timeout")


@pytest.mark.parametrize(
    ("output", "error"),
    [
        ('{"error": "city not found"}', "city not found"),
        ('{"is_error": true, "message": "bad"}', "bad"),
        ('{"temp": 1}', None),
        ("plain text", None),
    ],
)
def test_output_errors_are_only_reported_when_explicit(output: str, error: str | None) -> None:
    items = [FUNCTION_CALL, {"type": "function_call_output", "call_id": "call_1", "output": output}]
    assert from_openai_responses(items)[0].get("error") == error


def test_custom_tool_calls_and_unparseable_arguments() -> None:
    items = [
        {"type": "custom_tool_call", "call_id": "c1", "name": "run_sql", "input": "SELECT 1"},
        {**FUNCTION_CALL, "arguments": "{not json"},
        {"type": "web_search_call", "id": "ws_1", "status": "completed"},
    ]
    calls = from_openai_responses(items)
    assert calls[0]["args"] == {"input": "SELECT 1"}
    assert calls[1]["args"] == {"raw": "{not json"}
    assert len(calls) == 2


def test_errors_reach_the_evaluation_result() -> None:
    items = [
        FUNCTION_CALL,
        {"type": "function_call_output", "call_id": "call_1", "output": '{"error": "down"}'},
    ]
    result = evaluate(expected=[{"tool": "get_weather"}], actual=items)
    assert result.trace_calls[0].metadata["error"] == "down"


def test_trace_file_is_auto_detected(tmp_path: Path) -> None:
    gold = tmp_path / "gold.json"
    trace = tmp_path / "trace.json"
    gold.write_text(json.dumps([{"tool": "get_weather", "args": {"city": "Paris", "unit": "c"}}]))
    trace.write_text(json.dumps(_response_dict([MESSAGE, FUNCTION_CALL])))
    result = evaluate_trace(gold, trace)
    assert result.score == 1.0
    assert result.trace_calls[0].metadata["format"] == "responses"


def test_a_perfect_run_scores_exactly_one() -> None:
    calls = [{"tool": "a", "args": {"x": 1}}, {"tool": "b", "args": {}}]
    result = evaluate(expected=calls, actual=calls)
    assert result.score == 1.0
    assert result.grade == "A"
    custom = evaluate(expected=calls, actual=calls, weights={"required_call_recall": 0.3})
    assert custom.score == 1.0


def test_mcp_call_error_object_is_read_as_its_message() -> None:
    items = [
        {
            "type": "mcp_call",
            "id": "mcp_2",
            "name": "delete_doc",
            "server_label": "docs",
            "arguments": "{}",
            "error": {"type": "mcp_protocol_error", "code": -32602, "message": "doc not found"},
        }
    ]
    assert from_openai_responses(items)[0]["error"] == "doc not found"
