"""Tool usage efficiency metrics."""

import json

from toolscore.adapters.base import ToolCall


def _call_signature(call: ToolCall) -> tuple[str, str]:
    """Tool name plus canonical arguments; ``None`` and ``{}`` both mean no arguments."""
    return call.tool, json.dumps(call.args or {}, sort_keys=True, default=str)


def calculate_redundant_call_rate(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
) -> dict[str, float]:
    """Calculate redundant call rate.

    Measures inefficiency in tool use by quantifying how many tool calls
    were unnecessary or redundant.

    Args:
        gold_calls: Expected tool calls from gold standard.
        trace_calls: Actual tool calls from agent trace.

    Returns:
        Dictionary containing:
        - redundant_count: Number of redundant calls
        - total_calls: Total number of calls made
        - redundant_rate: Proportion of calls that were redundant (0-1)
        - identical_count: Calls that exactly repeat an earlier call (same tool
          and same arguments). Unlike ``redundant_count``, which counts calls
          beyond the gold's per-tool expectation, this isolates loop-like
          repetition from productive repeated use of a tool.
        - identical_rate: ``identical_count`` / ``total_calls`` (0-1)
    """
    if not trace_calls:
        return {
            "redundant_count": 0,
            "total_calls": 0,
            "redundant_rate": 0.0,
            "identical_count": 0,
            "identical_rate": 0.0,
        }

    gold_tool_names = [call.tool for call in gold_calls]
    trace_tool_names = [call.tool for call in trace_calls]

    # Count expected occurrences of each tool
    expected_counts: dict[str, int] = {}
    for tool in gold_tool_names:
        expected_counts[tool] = expected_counts.get(tool, 0) + 1

    # Count actual occurrences
    actual_counts: dict[str, int] = {}
    for tool in trace_tool_names:
        actual_counts[tool] = actual_counts.get(tool, 0) + 1

    # Calculate redundant calls
    redundant_count = 0

    for tool, actual_count in actual_counts.items():
        expected_count = expected_counts.get(tool, 0)
        if actual_count > expected_count:
            redundant_count += actual_count - expected_count

    total_calls = len(trace_calls)
    redundant_rate = redundant_count / total_calls if total_calls > 0 else 0.0
    identical_count = total_calls - len({_call_signature(call) for call in trace_calls})

    return {
        "redundant_count": redundant_count,
        "total_calls": total_calls,
        "redundant_rate": redundant_rate,
        "identical_count": identical_count,
        "identical_rate": identical_count / total_calls,
    }
