#!/usr/bin/env python3
"""Example: evaluate a Pydantic AI agent's tool calls with Toolscore.

This script is **self-contained** -- it builds a fake Pydantic-AI-shaped result
(the same duck-typed shape a real ``Agent(...).run_sync(...)`` result exposes via
``all_messages()``) so it runs WITHOUT pydantic-ai installed. Swap the
``run_agent`` body for your real agent and everything below works unchanged.

Run it:

    uv run python examples/pydantic_ai_quickstart.py
"""

from __future__ import annotations

from toolscore import Regex, assert_tools, evaluate
from toolscore.integrations import from_pydantic_ai


# ---------------------------------------------------------------------------
# A fake Pydantic AI result.
#
# A real AgentRunResult exposes all_messages(); each message has a ``parts`` list
# and tool calls are parts with ``part_kind == "tool-call"`` carrying
# ``tool_name`` and ``args``. We mirror that exact shape with tiny stand-in
# objects so from_pydantic_ai()/auto_extract handle it identically to the real
# thing.
# ---------------------------------------------------------------------------
class ToolCallPart:
    """Mirrors a Pydantic AI tool-call message part."""

    def __init__(self, tool_name: str, args: dict) -> None:
        self.part_kind = "tool-call"
        self.tool_name = tool_name
        self.args = args


class Message:
    """Mirrors a Pydantic AI message with a ``parts`` list."""

    def __init__(self, parts: list) -> None:
        self.parts = parts


class AgentRunResult:
    """Mirrors a Pydantic AI run result exposing ``all_messages()``."""

    def __init__(self, messages: list) -> None:
        self._messages = messages

    def all_messages(self) -> list:
        return self._messages


def run_agent(prompt: str) -> AgentRunResult:  # noqa: ARG001 - stub ignores the prompt
    """Stand-in for ``Agent('openai:gpt-4o', tools=[...]).run_sync(prompt)``."""
    return AgentRunResult(
        messages=[
            Message(parts=[ToolCallPart("get_weather", {"city": "NYC"})]),
            Message(parts=[ToolCallPart("send_email", {"to": "alice@example.com"})]),
        ]
    )


def main() -> None:
    result_obj = run_agent("email Alice the weather in NYC")

    # 1. Inspect the extracted calls (optional).
    calls = from_pydantic_ai(result_obj)
    print("=== Extracted tool calls ===")
    for call in calls:
        print(f"  {call['tool']}({call['args']})")
    print()

    # 2. Evaluate directly. The AgentRunResult is auto-detected (it has a
    #    callable all_messages()), so the raw object goes straight to evaluate().
    expected = [
        {"tool": "get_weather", "args": {"city": "NYC"}},
        {"tool": "send_email", "args": {"to": Regex(r".+@.+")}},  # any email address
    ]
    result = evaluate(expected=expected, actual=result_obj)
    print("=== evaluate() ===")
    print(f"  Composite score : {result.score:.3f}")
    print(f"  Selection acc.  : {result.selection_accuracy:.3f}")
    print(f"  Argument F1     : {result.argument_f1:.3f}")
    print()

    # 3. One-liner assertion for a pytest test.
    assert_tools(expected=expected, actual=result_obj, min_score=0.9)
    print("assert_tools passed!")


if __name__ == "__main__":
    main()
