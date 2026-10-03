"""Adapter for Model Context Protocol (MCP) traces.

MCP uses JSON-RPC 2.0 as its messaging format for tool calls.
Specification: https://modelcontextprotocol.io/specification/draft/server/tools
"""

import json
from typing import Any

from toolscore.adapters.base import BaseAdapter, ToolCall
from toolscore.mcp.content import content_to_text


class MCPAdapter(BaseAdapter):
    """Adapter for Anthropic Model Context Protocol (MCP) traces.

    MCP is an open standard for connecting AI assistants to data systems
    using JSON-RPC 2.0 messaging format.

    Supports:

    - Tool call requests (JSON-RPC 2.0 method calls)
    - Tool call results (JSON-RPC 2.0 responses)
    - Error handling (JSON-RPC 2.0 errors)
    - Both single requests and batch requests

    A recorded session (for example from ``toolscore mcp record``) holds each
    request followed by its response. A response whose ``id`` matches an earlier
    request in the same trace is merged into that request's call (result, error,
    ``is_error``), so one tool call stays one :class:`ToolCall`. A response with
    no matching request is reported on its own, as before.

    Example MCP tool call request::

        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "get_weather",
                "arguments": {"location": "San Francisco"}
            },
            "id": 1
        }

    Example MCP tool call result::

        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "Temperature: 72°F"}]
            }
        }
    """

    def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
        """Parse MCP trace into normalized tool calls.

        Args:
            trace_data: MCP trace data (single request or list of requests).

        Returns:
            List of normalized ToolCall objects.

        Raises:
            ValueError: If trace data is invalid.
        """
        self._validate_trace_data(trace_data)

        tool_calls: list[ToolCall] = []
        # Requests still waiting for their response, keyed by JSON-RPC id.
        pending: dict[Any, ToolCall] = {}

        for message in self._messages(trace_data):
            request_id = message.get("id")
            is_response = "method" not in message and ("result" in message or "error" in message)
            key = _hashable_id(request_id)
            if is_response and key is not None and key in pending:
                self._apply_response(pending.pop(key), message)
                continue

            tool_call = self._parse_mcp_message(message)
            if tool_call is None:
                continue
            tool_calls.append(tool_call)
            if "method" in message and key is not None:
                pending[key] = tool_call

        return tool_calls

    @staticmethod
    def _messages(trace_data: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        """Return the JSON-RPC messages held by any supported trace shape, in order."""
        if isinstance(trace_data, list):
            items: Any = trace_data
        elif "jsonrpc" in trace_data:
            items = [trace_data]
        elif "messages" in trace_data:
            items = trace_data["messages"]
        elif "calls" in trace_data or "tools" in trace_data:
            items = trace_data.get("calls", trace_data.get("tools", []))
        else:
            items = []
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def _parse_mcp_message(self, message: dict[str, Any]) -> ToolCall | None:
        """Parse a single MCP JSON-RPC message.

        Args:
            message: MCP JSON-RPC message (request or response).

        Returns:
            ToolCall object or None if not a tool call.
        """
        # Check if this is a JSON-RPC 2.0 message
        if (
            "jsonrpc" not in message
            and "method" not in message
            and "params" not in message
            and "error" not in message
        ):
            return None

        # Extract tool call from request
        if "method" in message and "params" in message:
            return self._parse_tool_request(message)

        # Extract tool call from result (for tracking results)
        if "result" in message and "id" in message:
            return self._parse_tool_result(message)

        # Extract error response
        if "error" in message and "id" in message:
            return self._parse_tool_result(message)

        return None

    def _parse_tool_request(self, request: dict[str, Any]) -> ToolCall | None:
        """Parse MCP tool call request.

        Args:
            request: JSON-RPC request message.

        Returns:
            ToolCall object or None.
        """
        method = request.get("method", "")
        params = request.get("params", {})

        # MCP tool calls use "tools/call" method
        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            if not tool_name:
                return None

            # Handle arguments as JSON string
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            return ToolCall(
                tool=tool_name,
                args=arguments,
                metadata={
                    "format": "mcp",
                    "jsonrpc_id": request.get("id"),
                    "method": method,
                },
            )

        # Some MCP implementations use the tool name directly as method
        # e.g., {"method": "get_weather", "params": {...}}
        if method and not method.startswith("tools/"):
            return ToolCall(
                tool=method,
                args=params,
                metadata={
                    "format": "mcp",
                    "jsonrpc_id": request.get("id"),
                    "method": method,
                },
            )

        return None

    @staticmethod
    def _response_fields(response: dict[str, Any]) -> dict[str, Any]:
        """Extract result, error and ``is_error`` from a JSON-RPC response.

        The result is ``structuredContent`` when present, otherwise the
        ``content`` rendered the way an MCP client shows it (text, embedded
        resources, resource links; see :func:`toolscore.mcp.content.content_to_text`),
        otherwise the raw ``result`` object. Error results carry no result value;
        their message goes to ``error`` (the JSON-RPC error message, or the tool's
        own text for ``isError`` results).
        """
        raw_result = response.get("result")
        result = raw_result if isinstance(raw_result, dict) else {}
        rpc_error = response.get("error")
        rpc_error = rpc_error if isinstance(rpc_error, dict) else None

        content = result.get("content", [])
        structured_content = result.get("structuredContent")
        if structured_content:
            result_value: Any = structured_content
        elif isinstance(content, list) and content:
            result_value = content_to_text(content)
        else:
            result_value = result

        is_error = bool(result.get("isError", False)) or rpc_error is not None
        if rpc_error is not None:
            error: str | None = rpc_error.get("message")
        elif is_error:
            error = content_to_text(content) or None
        else:
            error = None

        return {
            "result": None if is_error else result_value,
            "error": error,
            "error_code": rpc_error.get("code") if rpc_error else None,
            "is_error": is_error,
        }

    def _apply_response(self, call: ToolCall, response: dict[str, Any]) -> None:
        """Merge a response into the call created from its request."""
        fields = self._response_fields(response)
        call.result = fields["result"]
        call.duration = _duration(response)
        call.metadata.update(
            {
                "error": fields["error"],
                "error_code": fields["error_code"],
                "is_error": fields["is_error"],
            }
        )

    def _parse_tool_result(self, response: dict[str, Any]) -> ToolCall | None:
        """Parse a tool call result that has no matching request in the trace.

        Args:
            response: JSON-RPC response message.

        Returns:
            ToolCall object with result populated, or None.
        """
        result = response.get("result")
        # MCP responses do not carry the tool name; some logs add it as ``_tool_name``.
        tool_name = result.get("_tool_name", "unknown") if isinstance(result, dict) else "unknown"
        fields = self._response_fields(response)
        return ToolCall(
            tool=tool_name,
            args={},
            result=fields["result"],
            duration=_duration(response),
            metadata={
                "format": "mcp",
                "jsonrpc_id": response.get("id"),
                "error": fields["error"],
                "error_code": fields["error_code"],
                "is_error": fields["is_error"],
            },
        )


def _duration(response: dict[str, Any]) -> float | None:
    """Round-trip seconds recorded next to a response (``toolscore mcp record`` adds them)."""
    value = response.get("duration")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _hashable_id(request_id: Any) -> Any:
    """Return a JSON-RPC id usable as a dict key, or ``None`` when absent or unusable."""
    if request_id is None or isinstance(request_id, bool):
        return None
    if isinstance(request_id, (int, str)):
        return (type(request_id).__name__, request_id)
    return None
