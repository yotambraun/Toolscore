"""Import tool calls from OpenTelemetry GenAI spans (1.10).

The fixture is a real OTLP JSON export produced by the official OpenTelemetry Python
SDK (see tests/fixtures/make_otel_fixture.py): an agent span, a chat span and three
tool spans (one GenAI execute_tool span, one failed MCP tools/call span, one more
execute_tool span), listed in the order they finished.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from toolscore import evaluate, from_otel
from toolscore.core import load_trace

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "otel_genai_tool_spans.json"


def _export() -> dict:
    return json.loads(FIXTURE.read_text())


def test_tool_spans_become_calls_in_start_order() -> None:
    calls = from_otel(_export())

    assert [c["tool"] for c in calls] == ["search_orders", "issue_refund", "send_email"]
    search, _, email = calls
    assert search["args"] == {"customer": "ada@example.com", "status": "open"}
    assert search["result"] == {"orders": [{"id": "A-17", "total": 42.5}]}
    assert search["id"] == "call_1"
    assert search["is_error"] is False
    assert search["duration"] >= 0.02
    assert email["result"] is None


def test_failed_tool_span_keeps_the_error() -> None:
    refund = from_otel(_export())[1]

    assert refund["is_error"] is True
    assert refund["error"] == "Refund window has closed"
    assert refund["id"] == "7"
    assert refund["args"] == {"order_id": "A-17", "amount": 42.5}


def test_evaluate_and_load_trace_auto_detect_otlp(tmp_path: Path) -> None:
    result = evaluate(
        expected=[{"tool": "search_orders"}, {"tool": "issue_refund"}, {"tool": "send_email"}],
        actual=_export(),
    )
    assert result.selection_accuracy == 1.0
    assert result.metrics["efficiency_metrics"]["error_count"] == 1

    for fmt in ("auto", "otel"):
        calls = load_trace(FIXTURE, format=fmt)
        assert [(c.tool, c.is_error) for c in calls] == [
            ("search_orders", False),
            ("issue_refund", True),
            ("send_email", False),
        ]


def test_sdk_span_objects_are_supported() -> None:
    """ReadableSpan-like objects: attributes mapping, ns timestamps, a status with a code name."""
    ok = SimpleNamespace(
        name="execute_tool lookup",
        attributes={
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "lookup",
            "gen_ai.tool.call.arguments": {"q": "x"},
        },
        start_time=1_000_000_000,
        end_time=1_500_000_000,
        status=SimpleNamespace(status_code=SimpleNamespace(name="UNSET"), description=None),
    )
    failed = SimpleNamespace(
        name="execute_tool lookup",
        attributes={"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "lookup"},
        start_time=2_000_000_000,
        end_time=2_100_000_000,
        status=SimpleNamespace(status_code=SimpleNamespace(name="ERROR"), description="boom"),
    )

    calls = from_otel([failed, ok])

    assert [(c["args"], c["is_error"]) for c in calls] == [({"q": "x"}, False), ({}, True)]
    assert calls[0]["duration"] == 0.5
    assert calls[1]["error"] == "boom"


def test_numeric_error_status_and_non_json_arguments() -> None:
    export = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "execute_tool run",
                                "startTimeUnixNano": "1",
                                "endTimeUnixNano": "2",
                                "attributes": [
                                    {
                                        "key": "gen_ai.operation.name",
                                        "value": {"stringValue": "execute_tool"},
                                    },
                                    {"key": "gen_ai.tool.name", "value": {"stringValue": "run"}},
                                    {
                                        "key": "gen_ai.tool.call.arguments",
                                        "value": {"stringValue": "not json"},
                                    },
                                ],
                                "status": {"code": 2},
                            }
                        ]
                    }
                ]
            }
        ]
    }

    (call,) = from_otel(export)

    assert call["args"] == {"value": "not json"}
    assert call["is_error"] is True
