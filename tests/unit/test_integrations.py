"""Tests for integration helpers (from_openai, from_anthropic, from_gemini, auto_extract,
from_langgraph, from_pydantic_ai, from_openai_agents, from_claude_agent_sdk, from_crewai)."""

import pytest

from toolscore.integrations import (
    auto_extract,
    from_anthropic,
    from_claude_agent_sdk,
    from_crewai,
    from_gemini,
    from_langgraph,
    from_openai,
    from_openai_agents,
    from_pydantic_ai,
)


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
        response = {"candidates": [{"content": {"parts": [{"text": "Hello!"}]}}]}
        calls = from_gemini(response)
        assert calls == []

    def test_empty_candidates(self):
        """Response with empty candidates should return empty list."""
        response = {"candidates": []}
        calls = from_gemini(response)
        assert calls == []


class TestFromLangGraph:
    """Tests for from_langgraph()."""

    def test_dict_state_with_messages(self):
        """Parse a LangGraph state dict containing messages with tool_calls."""
        state = {
            "messages": [
                {"role": "human", "content": "hello"},
                {
                    "role": "ai",
                    "tool_calls": [
                        {"name": "search", "args": {"q": "test"}, "id": "tc_1"},
                    ],
                },
            ]
        }
        calls = from_langgraph(state)
        assert len(calls) == 1
        assert calls[0]["tool"] == "search"
        assert calls[0]["args"] == {"q": "test"}

    def test_object_state(self):
        """Parse a LangGraph state object (attribute-based)."""

        class ToolCall:
            def __init__(self, name: str, args: dict) -> None:
                self.name = name
                self.args = args

        class Message:
            def __init__(self, tool_calls: list) -> None:
                self.tool_calls = tool_calls

        class State:
            def __init__(self, messages: list) -> None:
                self.messages = messages

        state = State(
            messages=[
                Message(tool_calls=[]),
                Message(tool_calls=[ToolCall("get_weather", {"city": "NYC"})]),
            ]
        )
        calls = from_langgraph(state)
        assert len(calls) == 1
        assert calls[0]["tool"] == "get_weather"
        assert calls[0]["args"] == {"city": "NYC"}

    def test_plain_message_list(self):
        """Pass a plain list of messages."""
        messages = [
            {"tool_calls": [{"name": "a", "args": {"x": 1}, "id": "1"}]},
            {"tool_calls": [{"name": "b", "args": {"y": 2}, "id": "2"}]},
        ]
        calls = from_langgraph(messages)
        assert len(calls) == 2
        assert calls[0]["tool"] == "a"
        assert calls[1]["tool"] == "b"

    def test_order_preserved_across_messages(self):
        """Tool call order is preserved across multiple messages."""
        messages = [
            {"tool_calls": [{"name": "first", "args": {}, "id": "1"}]},
            {"tool_calls": [{"name": "second", "args": {}, "id": "2"}]},
            {"tool_calls": [{"name": "third", "args": {}, "id": "3"}]},
        ]
        calls = from_langgraph(messages)
        assert [c["tool"] for c in calls] == ["first", "second", "third"]

    def test_no_tool_calls_in_messages(self):
        """Messages without tool_calls return empty list."""
        state = {
            "messages": [
                {"role": "human", "content": "hello"},
                {"role": "ai", "content": "Hi there!"},
            ]
        }
        calls = from_langgraph(state)
        assert calls == []

    def test_empty_messages(self):
        """Empty messages list returns empty list."""
        calls = from_langgraph({"messages": []})
        assert calls == []

    def test_json_string_args(self):
        """JSON-string args are parsed."""
        messages = [
            {"tool_calls": [{"name": "tool", "args": '{"key": "value"}', "id": "1"}]},
        ]
        calls = from_langgraph(messages)
        assert calls[0]["args"] == {"key": "value"}

    def test_empty_tool_calls_skipped(self):
        """Messages with empty tool_calls list are skipped."""
        messages = [
            {"tool_calls": []},
            {"tool_calls": [{"name": "real_tool", "args": {}, "id": "1"}]},
        ]
        calls = from_langgraph(messages)
        assert len(calls) == 1
        assert calls[0]["tool"] == "real_tool"

    def test_openai_wire_format_nested_function(self):
        """OpenAI conversation-history shape nests under ``function``."""
        state = {
            "messages": [
                {"role": "user", "content": "search please"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "search",
                                "arguments": '{"q": "test"}',
                            },
                        }
                    ],
                },
            ]
        }
        calls = from_langgraph(state)
        assert len(calls) == 1
        assert calls[0]["tool"] == "search"
        assert calls[0]["args"] == {"q": "test"}

    def test_openai_wire_format_object_function(self):
        """OpenAI wire format via attribute access (function.name / .arguments)."""

        class Func:
            def __init__(self, name: str, arguments: str) -> None:
                self.name = name
                self.arguments = arguments

        class ToolCall:
            def __init__(self, func: Func) -> None:
                self.function = func

        class Message:
            def __init__(self, tool_calls: list) -> None:
                self.tool_calls = tool_calls

        messages = [Message([ToolCall(Func("lookup", '{"id": 5}'))])]
        calls = from_langgraph(messages)
        assert len(calls) == 1
        assert calls[0]["tool"] == "lookup"
        assert calls[0]["args"] == {"id": 5}

    def test_top_level_name_preferred_over_function(self):
        """Top-level ``name``/``args`` win when both shapes are present."""
        state = {
            "messages": [
                {
                    "tool_calls": [
                        {
                            "name": "top_tool",
                            "args": {"a": 1},
                            "function": {"name": "nested_tool", "arguments": "{}"},
                        }
                    ]
                }
            ]
        }
        calls = from_langgraph(state)
        assert len(calls) == 1
        assert calls[0]["tool"] == "top_tool"
        assert calls[0]["args"] == {"a": 1}


class TestFromPydanticAI:
    """Tests for from_pydantic_ai()."""

    def test_agent_run_result_with_all_messages(self):
        """AgentRunResult with all_messages() callable is supported."""

        class ToolCallPart:
            def __init__(self, tool_name: str, args: dict) -> None:
                self.part_kind = "tool-call"
                self.tool_name = tool_name
                self._args = args

            def args_as_dict(self) -> dict:
                return self._args

        class Message:
            def __init__(self, parts: list) -> None:
                self.parts = parts

        class AgentRunResult:
            def all_messages(self) -> list:
                return [
                    Message(parts=[ToolCallPart("search", {"q": "python"})]),
                ]

        calls = from_pydantic_ai(AgentRunResult())
        assert len(calls) == 1
        assert calls[0]["tool"] == "search"
        assert calls[0]["args"] == {"q": "python"}

    def test_plain_message_list_dict_style(self):
        """Plain list of messages in dict format."""
        messages = [
            {
                "parts": [
                    {"part_kind": "tool-call", "tool_name": "weather", "args": {"city": "NYC"}},
                ]
            }
        ]
        calls = from_pydantic_ai(messages)
        assert len(calls) == 1
        assert calls[0]["tool"] == "weather"
        assert calls[0]["args"] == {"city": "NYC"}

    def test_non_tool_call_parts_skipped(self):
        """Parts that are not tool-call are skipped."""
        messages = [
            {
                "parts": [
                    {"part_kind": "text", "content": "Hello"},
                    {"part_kind": "tool-call", "tool_name": "ping", "args": {}},
                ]
            }
        ]
        calls = from_pydantic_ai(messages)
        assert len(calls) == 1
        assert calls[0]["tool"] == "ping"

    def test_class_name_tool_call_part(self):
        """Part with class name ToolCallPart is accepted."""

        class ToolCallPart:
            def __init__(self, tool_name: str, args: dict) -> None:
                # part_kind intentionally absent — class name used instead
                self.tool_name = tool_name
                self.args = args

        class Message:
            def __init__(self, parts: list) -> None:
                self.parts = parts

        calls = from_pydantic_ai([Message(parts=[ToolCallPart("my_tool", {"x": 1})])])
        assert len(calls) == 1
        assert calls[0]["tool"] == "my_tool"
        assert calls[0]["args"] == {"x": 1}

    def test_json_string_args(self):
        """JSON-string args are parsed."""
        messages = [
            {
                "parts": [
                    {
                        "part_kind": "tool-call",
                        "tool_name": "tool",
                        "args": '{"key": "val"}',
                    }
                ]
            }
        ]
        calls = from_pydantic_ai(messages)
        assert calls[0]["args"] == {"key": "val"}

    def test_empty_messages(self):
        """Empty list returns empty list."""
        assert from_pydantic_ai([]) == []

    def test_no_tool_call_parts(self):
        """Messages without tool-call parts return empty list."""
        messages = [{"parts": [{"part_kind": "text", "content": "hello"}]}]
        assert from_pydantic_ai(messages) == []


class TestFromOpenAIAgents:
    """Tests for from_openai_agents()."""

    def test_run_result_object(self):
        """RunResult with new_items attribute."""

        class RawItem:
            def __init__(self, name: str, arguments: str) -> None:
                self.name = name
                self.arguments = arguments

        class Item:
            def __init__(self, name: str, arguments: str) -> None:
                self.type = "tool_call_item"
                self.raw_item = RawItem(name, arguments)

        class RunResult:
            def __init__(self) -> None:
                self.new_items = [
                    Item("search", '{"q": "python"}'),
                ]

        calls = from_openai_agents(RunResult())
        assert len(calls) == 1
        assert calls[0]["tool"] == "search"
        assert calls[0]["args"] == {"q": "python"}

    def test_plain_list_of_items(self):
        """Plain list of item dicts."""
        items = [
            {
                "type": "tool_call_item",
                "raw_item": {"name": "get_weather", "arguments": '{"city": "NYC"}'},
            }
        ]
        calls = from_openai_agents(items)
        assert len(calls) == 1
        assert calls[0]["tool"] == "get_weather"
        assert calls[0]["args"] == {"city": "NYC"}

    def test_non_tool_call_items_skipped(self):
        """Items that are not tool_call_item are skipped."""
        items = [
            {"type": "message_output_item", "raw_item": {}},
            {
                "type": "tool_call_item",
                "raw_item": {"name": "ping", "arguments": "{}"},
            },
        ]
        calls = from_openai_agents(items)
        assert len(calls) == 1
        assert calls[0]["tool"] == "ping"

    def test_attribute_style_items(self):
        """Items as objects with attributes."""

        class RawItem:
            def __init__(self) -> None:
                self.name = "my_tool"
                self.arguments = '{"a": 1}'

        class Item:
            def __init__(self) -> None:
                self.type = "tool_call_item"
                self.raw_item = RawItem()

        calls = from_openai_agents([Item()])
        assert calls[0]["tool"] == "my_tool"
        assert calls[0]["args"] == {"a": 1}

    def test_empty_new_items(self):
        """Empty new_items returns empty list."""

        class RunResult:
            def __init__(self) -> None:
                self.new_items: list = []

        assert from_openai_agents(RunResult()) == []

    def test_empty_list(self):
        """Empty list returns empty list."""
        assert from_openai_agents([]) == []


class TestFromClaudeAgentSDK:
    """Tests for from_claude_agent_sdk()."""

    def test_list_of_dict_messages(self):
        """List of dict messages with tool_use content blocks."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll search."},
                    {"type": "tool_use", "id": "tu_1", "name": "search", "input": {"q": "test"}},
                ],
            }
        ]
        calls = from_claude_agent_sdk(messages)
        assert len(calls) == 1
        assert calls[0]["tool"] == "search"
        assert calls[0]["args"] == {"q": "test"}

    def test_list_of_object_messages(self):
        """List of object-style messages."""

        class Block:
            def __init__(self, type_: str, name: str = "", input_: dict | None = None) -> None:
                self.type = type_
                self.name = name
                self.input = input_ or {}

        class Message:
            def __init__(self, content: list) -> None:
                self.content = content

        messages = [
            Message(
                content=[
                    Block("text"),
                    Block("tool_use", name="get_weather", input_={"city": "NYC"}),
                ]
            )
        ]
        calls = from_claude_agent_sdk(messages)
        assert len(calls) == 1
        assert calls[0]["tool"] == "get_weather"
        assert calls[0]["args"] == {"city": "NYC"}

    def test_multiple_messages_multiple_tool_uses(self):
        """Tool calls from multiple messages are collected in order."""
        messages = [
            {
                "content": [
                    {"type": "tool_use", "name": "first", "input": {}},
                ]
            },
            {
                "content": [
                    {"type": "tool_use", "name": "second", "input": {}},
                ]
            },
        ]
        calls = from_claude_agent_sdk(messages)
        assert [c["tool"] for c in calls] == ["first", "second"]

    def test_non_tool_use_blocks_skipped(self):
        """Blocks that are not tool_use are skipped."""
        messages = [
            {
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "tool_use", "name": "ping", "input": {}},
                ]
            }
        ]
        calls = from_claude_agent_sdk(messages)
        assert len(calls) == 1
        assert calls[0]["tool"] == "ping"

    def test_empty_list(self):
        """Empty list returns empty list."""
        assert from_claude_agent_sdk([]) == []

    def test_non_list_returns_empty(self):
        """Non-list input returns empty list gracefully."""
        assert from_claude_agent_sdk({"content": []}) == []

    def test_string_content_skipped(self):
        """Messages with plain string content don't crash."""
        messages = [{"role": "user", "content": "Hello there"}]
        assert from_claude_agent_sdk(messages) == []


class TestFromCrewAI:
    """Tests for from_crewai()."""

    def test_plain_list_of_dicts(self):
        """List of tool-result dicts."""
        entries = [
            {"tool_name": "search", "tool_args": {"q": "test"}},
        ]
        calls = from_crewai(entries)
        assert len(calls) == 1
        assert calls[0]["tool"] == "search"
        assert calls[0]["args"] == {"q": "test"}

    def test_object_with_tools_results(self):
        """Object with tools_results attribute."""

        class ToolResult:
            def __init__(self, tool_name: str, tool_args: dict) -> None:
                self.tool_name = tool_name
                self.tool_args = tool_args

        class CrewResult:
            def __init__(self) -> None:
                self.tools_results = [ToolResult("get_weather", {"city": "NYC"})]

        calls = from_crewai(CrewResult())
        assert len(calls) == 1
        assert calls[0]["tool"] == "get_weather"
        assert calls[0]["args"] == {"city": "NYC"}

    def test_dict_with_tools_results(self):
        """Dict with tools_results key."""
        result = {
            "tools_results": [
                {"tool_name": "search", "tool_args": {"q": "python"}},
            ]
        }
        calls = from_crewai(result)
        assert len(calls) == 1
        assert calls[0]["tool"] == "search"

    def test_json_string_args(self):
        """JSON-string tool_args are parsed."""
        entries = [
            {"tool_name": "tool", "tool_args": '{"key": "val"}'},
        ]
        calls = from_crewai(entries)
        assert calls[0]["args"] == {"key": "val"}

    def test_empty_list(self):
        """Empty list returns empty list."""
        assert from_crewai([]) == []

    def test_attribute_style_entries(self):
        """Attribute-style entries (object)."""

        class Entry:
            def __init__(self) -> None:
                self.tool_name = "my_tool"
                self.tool_args = {"x": 42}

        calls = from_crewai([Entry()])
        assert calls[0]["tool"] == "my_tool"
        assert calls[0]["args"] == {"x": 42}


class TestAutoExtract:
    """Tests for auto_extract()."""

    def test_passthrough_list(self):
        """Already-formatted list of dicts passes through unchanged."""
        data = [{"tool": "search", "args": {"q": "test"}}]
        result = auto_extract(data)
        assert result == data

    def test_passthrough_empty_list(self):
        """Empty list passes through."""
        assert auto_extract([]) == []

    def test_openai_dict(self):
        """Dict with 'choices' key is detected as OpenAI."""
        response = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"city": "NYC"}',
                                }
                            }
                        ]
                    }
                }
            ]
        }
        calls = auto_extract(response)
        assert len(calls) == 1
        assert calls[0]["tool"] == "get_weather"
        assert calls[0]["args"] == {"city": "NYC"}

    def test_anthropic_dict(self):
        """Dict with 'content' containing tool_use blocks is detected as Anthropic."""
        response = {
            "content": [
                {
                    "type": "tool_use",
                    "name": "web_search",
                    "input": {"query": "python"},
                }
            ]
        }
        calls = auto_extract(response)
        assert len(calls) == 1
        assert calls[0]["tool"] == "web_search"

    def test_gemini_dict(self):
        """Dict with 'candidates' key is detected as Gemini."""
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
        calls = auto_extract(response)
        assert len(calls) == 1
        assert calls[0]["tool"] == "get_weather"

    def test_model_dump_object(self):
        """Object with model_dump() is converted to dict and then detected."""

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
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }

        calls = auto_extract(FakeResponse())
        assert len(calls) == 1
        assert calls[0]["tool"] == "ping"

    def test_unrecognized_raises(self):
        """Unrecognized input raises TypeError."""
        with pytest.raises(TypeError, match="Cannot auto-detect"):
            auto_extract({"random": "data"})

    def test_unrecognized_string_raises(self):
        """String input raises TypeError."""
        with pytest.raises(TypeError, match="Cannot auto-detect"):
            auto_extract("not a response")

    # ---- New framework detection tests ----

    def test_langgraph_dict_state(self):
        """Dict with 'messages' where a message has tool_calls → LangGraph."""
        state = {
            "messages": [
                {"role": "human", "content": "search for me"},
                {
                    "role": "ai",
                    "tool_calls": [{"name": "search", "args": {"q": "test"}, "id": "1"}],
                },
            ]
        }
        calls = auto_extract(state)
        assert len(calls) == 1
        assert calls[0]["tool"] == "search"

    def test_langgraph_object_state(self):
        """Object with messages attribute having tool_calls → LangGraph."""

        class TC:
            def __init__(self) -> None:
                self.name = "my_tool"
                self.args: dict = {"k": "v"}

        class Msg:
            def __init__(self, tool_calls: list) -> None:
                self.tool_calls = tool_calls

        class State:
            def __init__(self) -> None:
                self.messages = [Msg([TC()])]

        calls = auto_extract(State())
        assert len(calls) == 1
        assert calls[0]["tool"] == "my_tool"

    def test_pydantic_ai_run_result(self):
        """Object with callable all_messages → Pydantic AI."""

        class Part:
            def __init__(self) -> None:
                self.part_kind = "tool-call"
                self.tool_name = "weather"
                self.args: dict = {"city": "LA"}

        class Msg:
            def __init__(self) -> None:
                self.parts = [Part()]

        class AgentResult:
            def all_messages(self) -> list:
                return [Msg()]

        calls = auto_extract(AgentResult())
        assert len(calls) == 1
        assert calls[0]["tool"] == "weather"

    def test_openai_agents_run_result(self):
        """Object with new_items → OpenAI Agents SDK."""

        class Raw:
            def __init__(self) -> None:
                self.name = "search"
                self.arguments = '{"q": "hi"}'

        class Item:
            def __init__(self) -> None:
                self.type = "tool_call_item"
                self.raw_item = Raw()

        class RunResult:
            def __init__(self) -> None:
                self.new_items = [Item()]

        calls = auto_extract(RunResult())
        assert len(calls) == 1
        assert calls[0]["tool"] == "search"

    def test_claude_agent_sdk_list(self):
        """List of messages with tool_use content blocks → Claude Agent SDK."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "ping", "input": {}},
                ],
            }
        ]
        calls = auto_extract(messages)
        assert len(calls) == 1
        assert calls[0]["tool"] == "ping"

    def test_no_shadowing_anthropic_single_message(self):
        """A single Anthropic Message dict (not a list) still uses from_anthropic."""
        response = {
            "content": [
                {"type": "tool_use", "name": "web_search", "input": {"query": "x"}},
            ]
        }
        calls = auto_extract(response)
        assert len(calls) == 1
        assert calls[0]["tool"] == "web_search"

    def test_no_shadowing_openai_choices(self):
        """OpenAI choices dict is not confused with LangGraph."""
        response = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [{"function": {"name": "search", "arguments": '{"q": "x"}'}}]
                    }
                }
            ]
        }
        calls = auto_extract(response)
        assert calls[0]["tool"] == "search"

    def test_no_shadowing_gemini_candidates(self):
        """Gemini candidates dict is not confused with LangGraph."""
        response = {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "tool", "args": {}}}]}}]
        }
        calls = auto_extract(response)
        assert calls[0]["tool"] == "tool"
