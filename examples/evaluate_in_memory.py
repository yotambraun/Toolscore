#!/usr/bin/env python3
"""Example: In-memory evaluation with Toolscore.

Demonstrates the evaluate(), assert_tools(), and integration helpers
using hardcoded mock data — no API keys or file I/O required.
"""

from toolscore import assert_tools, evaluate
from toolscore.integrations import from_anthropic, from_openai

# ---------------------------------------------------------------------------
# 1. Basic evaluate() usage with Python dicts
# ---------------------------------------------------------------------------
expected = [
    {"tool": "get_weather", "args": {"city": "San Francisco"}},
    {"tool": "send_email", "args": {"to": "alice@example.com", "body": "Hi!"}},
]
actual = [
    {"tool": "get_weather", "args": {"city": "San Francisco"}},
    {"tool": "send_email", "args": {"to": "alice@example.com", "body": "Hi!"}},
]

result = evaluate(expected, actual)
print("=== Basic evaluate() ===")
print(f"  Composite score : {result.score:.3f}")
print(f"  Selection acc.  : {result.selection_accuracy:.3f}")
print(f"  Argument F1     : {result.argument_f1:.3f}")
print(f"  Sequence acc.   : {result.sequence_accuracy:.3f}")
print()

# ---------------------------------------------------------------------------
# 2. Using from_openai() with a mock response dict
# ---------------------------------------------------------------------------
openai_response = {
    "choices": [
        {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "San Francisco"}',
                        }
                    }
                ]
            }
        }
    ]
}
actual_from_openai = from_openai(openai_response)
print("=== from_openai() ===")
print(f"  Extracted calls: {actual_from_openai}")

result_openai = evaluate(
    expected=[{"tool": "get_weather", "args": {"city": "San Francisco"}}],
    actual=actual_from_openai,
)
print(f"  Score: {result_openai.score:.3f}")
print()

# ---------------------------------------------------------------------------
# 3. Using from_anthropic() with a mock response dict
# ---------------------------------------------------------------------------
anthropic_response = {
    "content": [
        {
            "type": "tool_use",
            "name": "get_weather",
            "input": {"city": "San Francisco"},
        }
    ]
}
actual_from_anthropic = from_anthropic(anthropic_response)
print("=== from_anthropic() ===")
print(f"  Extracted calls: {actual_from_anthropic}")

result_anthropic = evaluate(
    expected=[{"tool": "get_weather", "args": {"city": "San Francisco"}}],
    actual=actual_from_anthropic,
)
print(f"  Score: {result_anthropic.score:.3f}")
print()

# ---------------------------------------------------------------------------
# 4. One-liner assertion with assert_tools()
# ---------------------------------------------------------------------------
print("=== assert_tools() ===")
result_assert = assert_tools(expected, actual, min_score=0.9)
print(f"  Passed! Score: {result_assert.score:.3f}")
print()

# ---------------------------------------------------------------------------
# 5. Custom weights
# ---------------------------------------------------------------------------
result_custom = evaluate(
    expected=[{"tool": "search"}],
    actual=[{"tool": "search"}],
    weights={"selection_accuracy": 1.0, "argument_f1": 0.0, "sequence_accuracy": 0.0, "redundant_rate": 0.0},
)
print("=== Custom weights ===")
print(f"  Score (selection only): {result_custom.score:.3f}")

# ---------------------------------------------------------------------------
# 6. Auto-detect: pass raw provider responses directly to evaluate()
# ---------------------------------------------------------------------------
print("\n=== Auto-detect (no from_openai() needed) ===")
result_auto = evaluate(
    expected=[{"tool": "get_weather", "args": {"city": "San Francisco"}}],
    actual=openai_response,  # raw OpenAI dict — auto-detected!
)
print(f"  Score: {result_auto.score:.3f}")

result_auto_anthropic = evaluate(
    expected=[{"tool": "get_weather", "args": {"city": "San Francisco"}}],
    actual=anthropic_response,  # raw Anthropic dict — auto-detected!
)
print(f"  Anthropic auto-detect score: {result_auto_anthropic.score:.3f}")

# ---------------------------------------------------------------------------
# 7. test_agent() — end-to-end helper
# ---------------------------------------------------------------------------
from toolscore import test_agent


def my_mock_agent(prompt):
    """Simulate an agent that always calls get_weather."""
    return [{"tool": "get_weather", "args": {"city": "San Francisco"}}]


print("\n=== test_agent() ===")
result_agent = test_agent(
    agent=my_mock_agent,
    input="What's the weather in SF?",
    expected=[{"tool": "get_weather", "args": {"city": "San Francisco"}}],
    min_score=0.9,
)
print(f"  Score: {result_agent.score:.3f}")

print("\nAll examples completed successfully!")
