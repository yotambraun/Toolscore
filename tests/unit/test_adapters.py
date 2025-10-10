"""Unit tests for trace adapters."""

import pytest

from toolscore.adapters import AnthropicAdapter, CustomAdapter, OpenAIAdapter, ToolCall


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_create_tool_call(self) -> None:
        """Test creating a tool call."""
        call = ToolCall(tool="test_tool", args={"key": "value"})
        assert call.tool == "test_tool"
        assert call.args == {"key": "value"}

    def test_tool_call_defaults(self) -> None:
        """Test tool call default values."""
        call = ToolCall(tool="test")
        assert call.args == {}
        assert call.result is None
        assert call.metadata == {}

    def test_tool_call_validation(self) -> None:
        """Test tool call validation."""
        with pytest.raises(ValueError, match="Tool name cannot be empty"):
            ToolCall(tool="")


class TestOpenAIAdapter:
    """Tests for OpenAI adapter."""

    def test_parse_function_call(self) -> None:
        """Test parsing OpenAI function call format."""
        trace_data = [
            {
                "role": "assistant",
                "function_call": {
                    "name": "get_weather",
                    "arguments": '{"location": "Boston"}',
                },
            }
        ]

        adapter = OpenAIAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "get_weather"
        assert calls[0].args == {"location": "Boston"}

    def test_parse_tool_calls(self) -> None:
        """Test parsing OpenAI tool_calls format."""
        trace_data = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call_123",
                        "function": {
                            "name": "search",
                            "arguments": '{"query": "python"}',
                        },
                    }
                ],
            }
        ]

        adapter = OpenAIAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "search"
        assert calls[0].args == {"query": "python"}


class TestAnthropicAdapter:
    """Tests for Anthropic adapter."""

    def test_parse_tool_use(self) -> None:
        """Test parsing Anthropic tool_use format."""
        trace_data = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_123",
                        "name": "search_web",
                        "input": {"query": "Python tutorials"},
                    }
                ],
            }
        ]

        adapter = AnthropicAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "search_web"
        assert calls[0].args == {"query": "Python tutorials"}


class TestCustomAdapter:
    """Tests for custom adapter."""

    def test_parse_calls_array(self) -> None:
        """Test parsing custom format with calls array."""
        trace_data = {
            "calls": [
                {"tool": "read_file", "args": {"path": "test.txt"}},
                {"tool": "write_file", "args": {"path": "out.txt", "content": "data"}},
            ]
        }

        adapter = CustomAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 2
        assert calls[0].tool == "read_file"
        assert calls[1].tool == "write_file"

    def test_parse_direct_array(self) -> None:
        """Test parsing direct array of calls."""
        trace_data = [
            {"name": "tool1", "arguments": {"x": 1}},
            {"tool": "tool2", "args": {"y": 2}},
        ]

        adapter = CustomAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 2
        assert calls[0].tool == "tool1"
        assert calls[1].tool == "tool2"
