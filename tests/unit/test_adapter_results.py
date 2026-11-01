"""Chat-history adapters keep what each tool returned (1.11)."""

from __future__ import annotations

from toolscore.adapters import AnthropicAdapter, OpenAIAdapter


def test_openai_tool_messages_become_results() -> None:
    calls = OpenAIAdapter().parse(
        [
            {"role": "user", "content": "weather?"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "a", "type": "function", "function": {"name": "w", "arguments": "{}"}},
                    {"id": "b", "type": "function", "function": {"name": "w", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "b", "content": "rain"},
            {"role": "tool", "tool_call_id": "a", "content": [{"type": "text", "text": "sun"}]},
            {"role": "assistant", "function_call": {"name": "old", "arguments": "{}"}},
            {"role": "function", "name": "old", "content": "legacy"},
        ]
    )
    assert [(c.tool, c.result) for c in calls] == [("w", "sun"), ("w", "rain"), ("old", "legacy")]
    assert not any(c.is_error for c in calls)


def test_anthropic_tool_results_and_errors() -> None:
    calls = AnthropicAdapter().parse(
        [
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "read", "input": {}},
                    {"type": "tool_use", "id": "t2", "name": "write", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "hello"},
                    {
                        "type": "tool_result",
                        "tool_use_id": "t2",
                        "is_error": True,
                        "content": [{"type": "text", "text": "EACCES"}],
                    },
                ],
            },
        ]
    )
    assert (calls[0].result, calls[0].is_error) == ("hello", False)
    assert (calls[1].result, calls[1].is_error, calls[1].metadata["error"]) == (
        None,
        True,
        "EACCES",
    )
