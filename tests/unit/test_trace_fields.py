"""Traces keep what really happened: results, errors, timing, cost (1.10)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from toolscore import evaluate
from toolscore.adapters.base import ToolCall
from toolscore.core import load_trace

if TYPE_CHECKING:
    from pathlib import Path


def test_trace_dicts_keep_result_timing_cost_and_metadata() -> None:
    actual = [
        {
            "tool": "search",
            "args": {"q": "x"},
            "result": {"hits": 3},
            "duration": 0.42,
            "cost": 0.001,
            "timestamp": 1700000000.0,
            "id": "call_1",
            "metadata": {"step": 2},
        }
    ]

    result = evaluate(expected=[{"tool": "search"}], actual=actual)

    call = result.trace_calls[0]
    assert call.result == {"hits": 3}
    assert call.duration == 0.42
    assert call.cost == 0.001
    assert call.timestamp == 1700000000.0
    assert call.metadata["id"] == "call_1"
    assert call.metadata["step"] == 2
    assert call.is_error is False


def test_error_can_be_a_message_or_a_flag() -> None:
    result = evaluate(
        expected=[{"tool": "a"}],
        actual=[
            {"tool": "a", "args": {}, "error": "Name has already been taken"},
            {"tool": "a", "args": {}, "error": True},
            {"tool": "a", "args": {}, "is_error": True},
            {"tool": "a", "args": {}, "error": None},
        ],
    )

    calls = result.trace_calls
    assert [c.is_error for c in calls] == [True, True, True, False]
    assert calls[0].metadata["error"] == "Name has already been taken"


def test_error_metrics_count_failures_and_retries_of_the_failed_call() -> None:
    actual = [
        {"tool": "list_issues", "args": {}},
        {"tool": "create_label", "args": {"name": "bug"}, "error": "Name has already been taken"},
        {"tool": "create_label", "args": {"name": "bug"}, "error": "Name has already been taken"},
        {"tool": "create_label", "args": {"name": "urgent"}},
    ]

    metrics = evaluate(expected=[{"tool": "list_issues"}], actual=actual).metrics[
        "efficiency_metrics"
    ]

    assert metrics["error_count"] == 2
    assert metrics["error_rate"] == 0.5
    assert metrics["retry_after_error_count"] == 1


def test_traces_without_error_information_score_exactly_as_before() -> None:
    expected = [{"tool": "a", "args": {"x": 1}}, {"tool": "b"}]
    plain = [{"tool": "a", "args": {"x": 1}}, {"tool": "b", "args": {}}]
    rich = [
        {"tool": "a", "args": {"x": 1}, "result": "ok", "duration": 1.0},
        {"tool": "b", "args": {}, "result": "ok", "cost": 0.01},
    ]

    before = evaluate(expected=expected, actual=plain)
    after = evaluate(expected=expected, actual=rich)

    assert after.score == before.score
    eff = before.metrics["efficiency_metrics"]
    assert (eff["error_count"], eff["error_rate"], eff["retry_after_error_count"]) == (0, 0.0, 0)


def test_tool_call_is_error_reads_adapter_metadata() -> None:
    assert ToolCall(tool="x", metadata={"is_error": True}).is_error is True
    assert ToolCall(tool="x", metadata={"error": "boom"}).is_error is True
    assert ToolCall(tool="x", metadata={"error": None, "is_error": False}).is_error is False
    assert ToolCall(tool="x").is_error is False


def test_recorded_mcp_session_feeds_error_metrics(tmp_path: Path) -> None:
    """A recorded JSON-RPC session: one call per request, errors counted, retry detected."""
    log = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "label_write", "arguments": {"name": "bug"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "Name has already been taken"}],
                "isError": True,
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "label_write", "arguments": {"name": "bug"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "content": [{"type": "text", "text": "Name has already been taken"}],
                "isError": True,
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "issue_write", "arguments": {"labels": ["bug"]}},
        },
        {"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "updated"}]}},
    ]
    path = tmp_path / "session.json"
    path.write_text(json.dumps(log))

    calls = load_trace(path, format="mcp")

    assert [(c.tool, c.is_error) for c in calls] == [
        ("label_write", True),
        ("label_write", True),
        ("issue_write", False),
    ]
