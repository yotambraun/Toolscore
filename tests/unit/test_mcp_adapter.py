"""Unit tests for MCP (Model Context Protocol) adapter."""

import pytest

from toolscore.adapters.mcp import MCPAdapter


class TestMCPAdapter:
    """Tests for MCP adapter."""

    def test_parse_standard_tool_call(self) -> None:
        """Test parsing standard MCP tool call request."""
        trace_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "get_weather",
                "arguments": {"location": "San Francisco", "unit": "celsius"},
            },
            "id": 1,
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "get_weather"
        assert calls[0].args == {"location": "San Francisco", "unit": "celsius"}
        assert calls[0].metadata["format"] == "mcp"
        assert calls[0].metadata["jsonrpc_id"] == 1

    def test_parse_tool_call_with_string_arguments(self) -> None:
        """Test parsing MCP tool call with JSON string arguments."""
        trace_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search",
                "arguments": '{"query": "Python tutorials", "limit": 10}',
            },
            "id": 2,
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "search"
        assert calls[0].args == {"query": "Python tutorials", "limit": 10}

    def test_parse_tool_call_array(self) -> None:
        """Test parsing array of MCP tool calls."""
        trace_data = [
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "search", "arguments": {"query": "AI"}},
                "id": 1,
            },
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "summarize", "arguments": {"text": "results"}},
                "id": 2,
            },
        ]

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 2
        assert calls[0].tool == "search"
        assert calls[1].tool == "summarize"

    def test_parse_direct_method_call(self) -> None:
        """Test parsing MCP call where tool name is the method."""
        trace_data = {
            "jsonrpc": "2.0",
            "method": "get_weather",
            "params": {"location": "Boston", "unit": "fahrenheit"},
            "id": 3,
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "get_weather"
        assert calls[0].args == {"location": "Boston", "unit": "fahrenheit"}

    def test_parse_messages_array(self) -> None:
        """Test parsing MCP trace with messages array."""
        trace_data = {
            "messages": [
                {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "calculate", "arguments": {"x": 5, "y": 3}},
                    "id": 1,
                },
                {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "format", "arguments": {"value": 8}},
                    "id": 2,
                },
            ]
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 2
        assert calls[0].tool == "calculate"
        assert calls[1].tool == "format"

    def test_parse_calls_array(self) -> None:
        """Test parsing MCP trace with calls array."""
        trace_data = {
            "calls": [
                {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "read_file", "arguments": {"path": "data.txt"}},
                    "id": 1,
                },
            ]
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "read_file"

    def test_parse_tool_result(self) -> None:
        """Test parsing MCP tool call result."""
        trace_data = {
            "jsonrpc": "2.0",
            "id": 5,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '{"temperature": 22.5, "conditions": "Partly cloudy"}',
                    }
                ]
            },
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].result is not None
        assert "22.5" in calls[0].result
        assert calls[0].metadata["format"] == "mcp"

    def test_parse_tool_result_with_structured_content(self) -> None:
        """Test parsing MCP result with structuredContent."""
        trace_data = {
            "jsonrpc": "2.0",
            "id": 6,
            "result": {
                "content": [{"type": "text", "text": "Temperature: 22.5"}],
                "structuredContent": {"temperature": 22.5, "unit": "celsius"},
            },
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].result == {"temperature": 22.5, "unit": "celsius"}

    def test_parse_error_response(self) -> None:
        """Test parsing MCP error response."""
        trace_data = {
            "jsonrpc": "2.0",
            "id": 3,
            "error": {"code": -32602, "message": "Unknown tool: invalid_tool_name"},
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].metadata["is_error"] is True
        assert calls[0].metadata["error"] == "Unknown tool: invalid_tool_name"
        assert calls[0].metadata["error_code"] == -32602

    def test_parse_tool_execution_error(self) -> None:
        """Test parsing MCP tool execution error."""
        trace_data = {
            "jsonrpc": "2.0",
            "id": 4,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "Failed to fetch weather data: API rate limit exceeded",
                    }
                ],
                "isError": True,
            },
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].metadata["is_error"] is True
        assert calls[0].result is None  # Error results are None

    def test_parse_empty_trace(self) -> None:
        """Test parsing empty MCP trace."""
        adapter = MCPAdapter()

        # Empty dict
        calls = adapter.parse({})
        assert len(calls) == 0

        # Empty list
        calls = adapter.parse([])
        assert len(calls) == 0

    def test_parse_invalid_arguments_json(self) -> None:
        """Test parsing MCP call with invalid JSON in arguments."""
        trace_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "test", "arguments": "invalid json{"},
            "id": 1,
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].args == {}  # Falls back to empty dict

    def test_parse_mixed_content(self) -> None:
        """Test parsing MCP trace with mixed valid and invalid messages."""
        trace_data = [
            {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "valid_tool", "arguments": {}},
                "id": 1,
            },
            {"not_a_jsonrpc": "message"},  # Invalid
            {
                "jsonrpc": "2.0",
                "method": "another_tool",
                "params": {"key": "value"},
                "id": 2,
            },
        ]

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 2  # Only valid ones
        assert calls[0].tool == "valid_tool"
        assert calls[1].tool == "another_tool"

    def test_parse_empty_tool_name(self) -> None:
        """Test parsing MCP call with empty tool name."""
        trace_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "", "arguments": {}},
            "id": 1,
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 0  # Empty tool names are ignored

    def test_parse_result_without_content(self) -> None:
        """Test parsing MCP result without content field."""
        trace_data = {
            "jsonrpc": "2.0",
            "id": 7,
            "result": {"status": "success", "value": 42},
        }

        adapter = MCPAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].result == {"status": "success", "value": 42}
