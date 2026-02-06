"""Tests for integration helpers (from_openai, from_anthropic, from_gemini)."""

from toolscore.integrations import from_anthropic, from_gemini, from_openai


class TestFromOpenAI:
    """Tests for from_openai()."""

    def test_modern_tool_calls(self):
        """Parse modern OpenAI tool_calls format."""
        response = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_123",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"city": "NYC"}',
                                },
                            }
                        ]
                    }
                }
            ]
        }
        calls = from_openai(response)
        assert len(calls) == 1
        assert calls[0]["tool"] == "get_weather"
        assert calls[0]["args"] == {"city": "NYC"}

    def test_legacy_function_call(self):
        """Parse legacy OpenAI function_call format."""
        response = {
            "choices": [
                {
                    "message": {
                        "function_call": {
                            "name": "search",
                            "arguments": '{"query": "python"}',
                        }
                    }
                }
            ]
        }
        calls = from_openai(response)
        assert len(calls) == 1
        assert calls[0]["tool"] == "search"
        assert calls[0]["args"] == {"query": "python"}

    def test_multiple_tool_calls(self):
        """Parse multiple tool calls in a single message."""
        response = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "search",
                                    "arguments": '{"q": "a"}',
                                },
                            },
                            {
                                "function": {
                                    "name": "read",
                                    "arguments": '{"file": "b.txt"}',
                                },
                            },
                        ]
                    }
                }
            ]
        }
        calls = from_openai(response)
        assert len(calls) == 2
        assert calls[0]["tool"] == "search"
        assert calls[1]["tool"] == "read"

    def test_no_tool_calls(self):
        """Response with no tool calls should return empty list."""
        response = {"choices": [{"message": {"content": "Hello"}}]}
        calls = from_openai(response)
        assert calls == []

    def test_empty_choices(self):
        """Response with empty choices should return empty list."""
        response = {"choices": []}
        calls = from_openai(response)
        assert calls == []

    def test_invalid_arguments_json(self):
        """Invalid JSON in arguments should return empty dict."""
        response = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "test",
                                    "arguments": "not valid json",
                                },
                            }
                        ]
                    }
                }
            ]
        }
        calls = from_openai(response)
        assert len(calls) == 1
        assert calls[0]["tool"] == "test"
        assert calls[0]["args"] == {}

    def test_with_model_dump(self):
        """Object with model_dump() method should work."""

        class FakeResponse:
            def model_dump(self):  # type: ignore[no-untyped-def]
                return {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "ping",
                                            "arguments": "{}",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }

        calls = from_openai(FakeResponse())
        assert len(calls) == 1
        assert calls[0]["tool"] == "ping"


class TestFromAnthropic:
    """Tests for from_anthropic()."""

    def test_tool_use_blocks(self):
        """Parse Anthropic tool_use content blocks."""
        response = {
            "content": [
                {
                    "type": "text",
                    "text": "I'll search for that.",
                },
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "web_search",
                    "input": {"query": "python tutorials"},
                },
            ]
        }
        calls = from_anthropic(response)
        assert len(calls) == 1
        assert calls[0]["tool"] == "web_search"
        assert calls[0]["args"] == {"query": "python tutorials"}

    def test_multiple_tool_use(self):
        """Parse multiple tool_use blocks."""
        response = {
            "content": [
                {
                    "type": "tool_use",
                    "name": "search",
                    "input": {"q": "a"},
                },
                {
                    "type": "tool_use",
                    "name": "read",
                    "input": {"file": "b.txt"},
                },
            ]
        }
        calls = from_anthropic(response)
        assert len(calls) == 2
        assert calls[0]["tool"] == "search"
        assert calls[1]["tool"] == "read"

    def test_no_tool_use(self):
        """Response with no tool_use should return empty list."""
        response = {
            "content": [
                {"type": "text", "text": "Hello!"},
            ]
        }
        calls = from_anthropic(response)
        assert calls == []

    def test_empty_content(self):
        """Response with empty content should return empty list."""
        response = {"content": []}
        calls = from_anthropic(response)
        assert calls == []

    def test_empty_input(self):
        """Tool use with no input should default to empty dict."""
        response = {
            "content": [
                {
                    "type": "tool_use",
                    "name": "ping",
                    "input": None,
                },
            ]
        }
        calls = from_anthropic(response)
        assert len(calls) == 1
        assert calls[0]["args"] == {}


class TestFromGemini:
    """Tests for from_gemini()."""

    def test_function_call_parts(self):
        """Parse Gemini functionCall parts."""
        response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_weather",
                                    "args": {"location": "NYC"},
                                }
                            }
                        ]
                    }
                }
            ]
        }
        calls = from_gemini(response)
        assert len(calls) == 1
        assert calls[0]["tool"] == "get_weather"
        assert calls[0]["args"] == {"location": "NYC"}

    def test_snake_case_function_call(self):
        """Parse snake_case function_call format (dict representation)."""
        response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "function_call": {
                                    "name": "search",
                                    "args": {"q": "test"},
                                }
                            }
                        ]
                    }
                }
            ]
        }
        calls = from_gemini(response)
        assert len(calls) == 1
        assert calls[0]["tool"] == "search"

    def test_no_function_calls(self):
        """Response with no function calls should return empty list."""
        response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Hello!"}
                        ]
                    }
                }
            ]
        }
        calls = from_gemini(response)
        assert calls == []

    def test_empty_candidates(self):
        """Response with empty candidates should return empty list."""
        response = {"candidates": []}
        calls = from_gemini(response)
        assert calls == []
