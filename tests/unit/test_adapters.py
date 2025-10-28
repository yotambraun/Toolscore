"""Unit tests for trace adapters."""

import pytest

from toolscore.adapters import (
    AnthropicAdapter,
    CustomAdapter,
    GeminiAdapter,
    OpenAIAdapter,
    ToolCall,
)


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


class TestGeminiAdapter:
    """Tests for Gemini adapter."""

    def test_parse_candidates_format(self) -> None:
        """Test parsing Gemini candidates format."""
        trace_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_weather",
                                    "args": {"location": "San Francisco", "unit": "celsius"},
                                }
                            }
                        ]
                    }
                }
            ]
        }

        adapter = GeminiAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "get_weather"
        assert calls[0].args == {"location": "San Francisco", "unit": "celsius"}
        assert calls[0].metadata["format"] == "gemini"

    def test_parse_multiple_function_calls(self) -> None:
        """Test parsing multiple function calls in Gemini format."""
        trace_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "search",
                                    "args": {"query": "Python"},
                                }
                            },
                            {
                                "functionCall": {
                                    "name": "summarize",
                                    "args": {"text": "results"},
                                }
                            },
                        ]
                    }
                }
            ]
        }

        adapter = GeminiAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 2
        assert calls[0].tool == "search"
        assert calls[0].args == {"query": "Python"}
        assert calls[1].tool == "summarize"
        assert calls[1].args == {"text": "results"}

    def test_parse_parts_list_format(self) -> None:
        """Test parsing direct parts list format."""
        trace_data = [
            {
                "parts": [
                    {
                        "functionCall": {
                            "name": "calculate",
                            "args": {"x": 5, "y": 3, "operation": "add"},
                        }
                    }
                ]
            }
        ]

        adapter = GeminiAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "calculate"
        assert calls[0].args == {"x": 5, "y": 3, "operation": "add"}

    def test_parse_function_call_alternative_format(self) -> None:
        """Test parsing function_call (snake_case) format."""
        trace_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "function_call": {
                                    "name": "send_email",
                                    "arguments": {"to": "test@example.com", "subject": "Hello"},
                                }
                            }
                        ]
                    }
                }
            ]
        }

        adapter = GeminiAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "send_email"
        assert calls[0].args == {"to": "test@example.com", "subject": "Hello"}

    def test_parse_string_arguments(self) -> None:
        """Test parsing when arguments are provided as JSON string."""
        trace_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "test_tool",
                                    "args": '{"key": "value", "num": 42}',
                                }
                            }
                        ]
                    }
                }
            ]
        }

        adapter = GeminiAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "test_tool"
        assert calls[0].args == {"key": "value", "num": 42}

    def test_parse_empty_arguments(self) -> None:
        """Test parsing function call with no arguments."""
        trace_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_current_time",
                                    "args": {},
                                }
                            }
                        ]
                    }
                }
            ]
        }

        adapter = GeminiAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "get_current_time"
        assert calls[0].args == {}

    def test_parse_content_as_list(self) -> None:
        """Test parsing when content is directly a list."""
        trace_data = {
            "candidates": [
                {
                    "content": [
                        {
                            "functionCall": {
                                "name": "list_files",
                                "args": {"directory": "/home"},
                            }
                        }
                    ]
                }
            ]
        }

        adapter = GeminiAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].tool == "list_files"
        assert calls[0].args == {"directory": "/home"}

    def test_parse_empty_trace(self) -> None:
        """Test parsing empty Gemini trace."""
        trace_data = {"candidates": [{"content": {"parts": []}}]}

        adapter = GeminiAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 0

    def test_parse_mixed_parts(self) -> None:
        """Test parsing parts with both text and function calls."""
        trace_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Let me search for that"},
                            {
                                "functionCall": {
                                    "name": "web_search",
                                    "args": {"query": "machine learning"},
                                }
                            },
                        ]
                    }
                }
            ]
        }

        adapter = GeminiAdapter()
        calls = adapter.parse(trace_data)

        # Should only extract function calls, ignore text
        assert len(calls) == 1
        assert calls[0].tool == "web_search"
        assert calls[0].args == {"query": "machine learning"}

    def test_parse_with_id(self) -> None:
        """Test parsing function call with ID metadata."""
        trace_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "test",
                                    "args": {"x": 1},
                                    "id": "func_123",
                                }
                            }
                        ]
                    }
                }
            ]
        }

        adapter = GeminiAdapter()
        calls = adapter.parse(trace_data)

        assert len(calls) == 1
        assert calls[0].metadata["id"] == "func_123"
