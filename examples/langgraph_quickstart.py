#!/usr/bin/env python3
"""Example: evaluate a LangGraph agent's tool calls with Toolscore.

This script is **self-contained** -- it builds a fake LangGraph-shaped result
(the same duck-typed shape a real ``create_react_agent(...).invoke(...)`` call
returns) so it runs WITHOUT langgraph installed. Swap the ``run_agent`` body for
your real agent and everything below works unchanged.

Run it:

    uv run python examples/langgraph_quickstart.py
"""

from __future__ import annotations

from toolscore import ANY, assert_tools, evaluate
from toolscore.integrations import from_langgraph


# ---------------------------------------------------------------------------
# A fake LangGraph result.
#
# LangGraph's final state is a dict with a "messages" list; AI messages carry a
# "tool_calls" list of {"name", "args", "id"} dicts. Toolscore auto-detects this
# shape -- you can pass it straight to evaluate() (no from_langgraph() needed),
# or call from_langgraph() explicitly to inspect the extracted calls.
# ---------------------------------------------------------------------------
def run_agent(prompt: str) -> dict:
    """Stand-in for ``create_react_agent(model, tools).invoke({"messages": ...})``."""
    return {
        "messages": [
            {"role": "human", "content": prompt},
            {
                "role": "ai",
                "tool_calls": [
                    {"name": "search_flights", "args": {"destination": "NYC"}, "id": "call_1"},
                    {"name": "book_flight", "args": {"flight_id": "FL-42"}, "id": "call_2"},
                ],
            },
        ]
    }


def main() -> None:
    state = run_agent("book me a flight to NYC")

    # 1. Inspect the extracted calls (optional).
    calls = from_langgraph(state)
    print("=== Extracted tool calls ===")
    for call in calls:
        print(f"  {call['tool']}({call['args']})")
    print()

    # 2. Evaluate directly against an expected spec. The raw LangGraph state is
    #    auto-detected, so no manual extraction is required here.
    expected = [
        {"tool": "search_flights", "args": {"destination": "NYC"}},
        {"tool": "book_flight", "args": {"flight_id": ANY}},  # any flight id is fine
    ]
    result = evaluate(expected=expected, actual=state)
    print("=== evaluate() ===")
    print(f"  Composite score : {result.score:.3f}")
    print(f"  Selection acc.  : {result.selection_accuracy:.3f}")
    print(f"  Argument F1     : {result.argument_f1:.3f}")
    print()

    # 3. One-liner assertion for a pytest test.
    assert_tools(expected=expected, actual=state, min_score=0.9)
    print("assert_tools passed!")


if __name__ == "__main__":
    main()
