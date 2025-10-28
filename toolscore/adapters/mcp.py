"""Adapter for Model Context Protocol (MCP) traces.

MCP uses JSON-RPC 2.0 as its messaging format for tool calls.
Specification: https://modelcontextprotocol.io/specification/draft/server/tools
"""

import json
from typing import Any

from toolscore.adapters.base import BaseAdapter, ToolCall


class MCPAdapter(BaseAdapter):
    """Adapter for Anthropic Model Context Protocol (MCP) traces.

    MCP is an open standard for connecting AI assistants to data systems
    using JSON-RPC 2.0 messaging format.

    Supports:
    - Tool call requests (JSON-RPC 2.0 method calls)
    - Tool call results (JSON-RPC 2.0 responses)
    - Error handling (JSON-RPC 2.0 errors)
    - Both single requests and batch requests

    Example MCP tool call request:
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "get_weather",
                "arguments": {"location": "San Francisco"}
            },
            "id": 1
        }

    Example MCP tool call result:
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

        # Handle both single and batch requests
        if isinstance(trace_data, dict):
            # Single request/response
            if "jsonrpc" in trace_data:
                tool_call = self._parse_mcp_message(trace_data)
                if tool_call:
                    tool_calls.append(tool_call)
            # Object containing messages array
            elif "messages" in trace_data:
                for message in trace_data["messages"]:
                    tool_call = self._parse_mcp_message(message)
                    if tool_call:
                        tool_calls.append(tool_call)
            # Object containing calls/tools array
            elif "calls" in trace_data or "tools" in trace_data:
                messages = trace_data.get("calls", trace_data.get("tools", []))
                for message in messages:
                    tool_call = self._parse_mcp_message(message)
                    if tool_call:
                        tool_calls.append(tool_call)

        elif isinstance(trace_data, list):
            # Array of requests/responses
            for item in trace_data:
                if isinstance(item, dict):
                    tool_call = self._parse_mcp_message(item)
                    if tool_call:
                        tool_calls.append(tool_call)

        return tool_calls

    def _parse_mcp_message(self, message: dict[str, Any]) -> ToolCall | None:
        """Parse a single MCP JSON-RPC message.

        Args:
            message: MCP JSON-RPC message (request or response).

        Returns:
            ToolCall object or None if not a tool call.
        """
        # Check if this is a JSON-RPC 2.0 message
        if "jsonrpc" not in message and "method" not in message and "params" not in message and "error" not in message:
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

    def _parse_tool_result(self, response: dict[str, Any]) -> ToolCall | None:
        """Parse MCP tool call result.

        Args:
            response: JSON-RPC response message.

        Returns:
            ToolCall object with result populated, or None.
        """
        result = response.get("result", {})
        error = response.get("error")

        # Extract tool name from metadata if available
        # (MCP responses don't include tool name, so we use ID to match)
        tool_name = result.get("_tool_name", "unknown")

        # Extract result content
        content = result.get("content", [])
        structured_content = result.get("structuredContent")

        # Build result value
        if structured_content:
            result_value = structured_content
        elif content and isinstance(content, list) and content:
            # Extract text from content array
            result_value = " ".join(
                item.get("text", "") for item in content if item.get("type") == "text"
            )
        else:
            result_value = result

        # Check for errors
        is_error = result.get("isError", False) or error is not None

        return ToolCall(
            tool=tool_name,
            args={},
            result=result_value if not is_error else None,
            metadata={
                "format": "mcp",
                "jsonrpc_id": response.get("id"),
                "error": error.get("message") if error else None,
                "error_code": error.get("code") if error else None,
                "is_error": is_error,
            },
        )
