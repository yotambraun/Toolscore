"""Import tool calls from OpenTelemetry GenAI spans.

Agent frameworks and observability platforms that follow the OpenTelemetry
semantic conventions for generative AI record each tool execution as a span:

* GenAI ``execute_tool`` spans: ``gen_ai.operation.name == "execute_tool"``,
  ``gen_ai.tool.name``, and opt-in ``gen_ai.tool.call.arguments`` /
  ``gen_ai.tool.call.result``
  (https://github.com/open-telemetry/semantic-conventions-genai, gen-ai-spans.md).
* MCP client spans: ``mcp.method.name == "tools/call"`` with ``gen_ai.tool.name``
  (same repository, mcp.md).

A failed call carries ``error.type`` and/or an ERROR span status. The call id is
``gen_ai.tool.call.id`` (or ``jsonrpc.request.id`` for MCP).

Accepted inputs:

* an OTLP JSON export (``{"resourceSpans": [...]}``), as written by OTLP/JSON
  exporters and collector file exporters;
* a list of span dicts (OTLP span objects, or dicts whose ``attributes`` is a
  plain mapping);
* a list of OpenTelemetry SDK span objects (``ReadableSpan``: ``attributes``,
  ``start_time``/``end_time`` in nanoseconds, ``status``).

Spans that are not tool executions (agent, chat, embeddings ...) are skipped,
and calls are returned in start-time order.
"""

from __future__ import annotations

import json
from typing import Any

from toolscore.adapters.base import BaseAdapter, ToolCall

_TOOL_OPERATION = "execute_tool"
_MCP_TOOL_METHOD = "tools/call"


def _otlp_value(value: Any) -> Any:
    """Decode an OTLP ``AnyValue`` (``{"stringValue": ...}`` and friends)."""
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "boolValue", "doubleValue", "bytesValue"):
        if key in value:
            return value[key]
    if "intValue" in value:
        return int(value["intValue"])
    if "arrayValue" in value:
        return [_otlp_value(item) for item in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return {
            kv["key"]: _otlp_value(kv.get("value")) for kv in value["kvlistValue"].get("values", [])
        }
    return None


def _attributes(span: Any) -> dict[str, Any]:
    """A span's attributes as a plain dict (OTLP key/value list or a mapping)."""
    raw = span.get("attributes") if isinstance(span, dict) else getattr(span, "attributes", None)
    if isinstance(raw, list):
        return {
            item["key"]: _otlp_value(item.get("value"))
            for item in raw
            if isinstance(item, dict) and "key" in item
        }
    if raw is None:
        return {}
    try:
        return dict(raw)
    except (TypeError, ValueError):
        return {}


def _nanos(span: Any, json_key: str, sdk_attr: str) -> int | None:
    """A span timestamp in nanoseconds (OTLP strings or SDK integers)."""
    value = span.get(json_key) if isinstance(span, dict) else getattr(span, sdk_attr, None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _status(span: Any) -> tuple[bool, str | None]:
    """Whether the span status is ERROR, and its message."""
    if isinstance(span, dict):
        status = span.get("status") or {}
        code = status.get("code")
        failed = code in (2, "2", "STATUS_CODE_ERROR", "ERROR")
        return failed, status.get("message") or None
    status = getattr(span, "status", None)
    code = getattr(getattr(status, "status_code", None), "name", None)
    return code == "ERROR", getattr(status, "description", None) or None


def _decode(value: Any) -> Any:
    """Decode a JSON-string attribute into an object when possible."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _spans(data: Any) -> list[Any]:
    """Every span in an OTLP export, a span list, or a single span."""
    if isinstance(data, dict) and "resourceSpans" in data:
        return [
            span
            for resource in data.get("resourceSpans") or []
            for scope in resource.get("scopeSpans")
            or resource.get("instrumentationLibrarySpans")
            or []
            for span in scope.get("spans") or []
        ]
    if isinstance(data, list):
        return list(data)
    return [data]


def is_tool_span(span: Any) -> bool:
    """Whether a span records a tool execution (GenAI ``execute_tool`` or MCP ``tools/call``)."""
    attributes = _attributes(span)
    if not attributes.get("gen_ai.tool.name"):
        return False
    return (
        attributes.get("gen_ai.operation.name") == _TOOL_OPERATION
        or attributes.get("mcp.method.name") == _MCP_TOOL_METHOD
    )


def looks_like_otel(data: Any) -> bool:
    """Whether ``data`` is an OTLP export or a list holding at least one tool span."""
    if isinstance(data, dict):
        return "resourceSpans" in data
    if isinstance(data, list) and data:
        return any(is_tool_span(span) for span in data[:50])
    return False


def tool_calls_from_otel(data: Any) -> list[dict[str, Any]]:
    """Extract tool calls from OpenTelemetry GenAI tool spans.

    Args:
        data: An OTLP JSON export, a list of span dicts, or a list of
            OpenTelemetry SDK span objects.

    Returns:
        One dict per tool span, in start-time order, with ``tool``, ``args``,
        ``result``, ``is_error``, ``error``, ``duration`` (seconds) and ``id``.
        Arguments and results recorded as JSON strings are decoded; arguments
        that are not a JSON object are kept as ``{"value": ...}``.
    """
    rows: list[tuple[int, int, dict[str, Any]]] = []
    for position, span in enumerate(_spans(data)):
        if not is_tool_span(span):
            continue
        attributes = _attributes(span)
        start = _nanos(span, "startTimeUnixNano", "start_time")
        end = _nanos(span, "endTimeUnixNano", "end_time")
        failed, message = _status(span)
        error_type = attributes.get("error.type")
        args = _decode(attributes.get("gen_ai.tool.call.arguments"))
        if args is None:
            args = {}
        elif not isinstance(args, dict):
            args = {"value": args}
        call_id = attributes.get("gen_ai.tool.call.id") or attributes.get("jsonrpc.request.id")
        is_error = failed or bool(error_type)
        rows.append(
            (
                start if start is not None else 0,
                position,
                {
                    "tool": str(attributes["gen_ai.tool.name"]),
                    "args": args,
                    "result": _decode(attributes.get("gen_ai.tool.call.result")),
                    "is_error": is_error,
                    "error": (message or (str(error_type) if error_type else None))
                    if is_error
                    else None,
                    "duration": (end - start) / 1e9
                    if start is not None and end is not None
                    else None,
                    "id": str(call_id) if call_id is not None else None,
                },
            )
        )
    return [row for _, _, row in sorted(rows, key=lambda r: (r[0], r[1]))]


class OTelAdapter(BaseAdapter):
    """Adapter for OpenTelemetry GenAI tool spans (OTLP JSON exports).

    See :func:`tool_calls_from_otel` for the accepted inputs and the mapping.
    """

    def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
        """Parse an OTLP export or span list into tool calls.

        Args:
            trace_data: An OTLP JSON export or a list of spans.

        Returns:
            One :class:`ToolCall` per tool span, in start-time order.
        """
        self._validate_trace_data(trace_data)
        calls: list[ToolCall] = []
        for row in tool_calls_from_otel(trace_data):
            metadata: dict[str, Any] = {"format": "otel", "is_error": row["is_error"]}
            if row["error"] is not None:
                metadata["error"] = row["error"]
            if row["id"] is not None:
                metadata["id"] = row["id"]
            calls.append(
                ToolCall(
                    tool=row["tool"],
                    args=row["args"],
                    result=row["result"],
                    duration=row["duration"],
                    metadata=metadata,
                )
            )
        return calls
