"""Tool usage efficiency metrics."""

from toolscore.adapters.base import ToolCall


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
    """
    if not trace_calls:
        return {
            "redundant_count": 0,
            "total_calls": 0,
            "redundant_rate": 0.0,
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

    return {
        "redundant_count": redundant_count,
        "total_calls": total_calls,
        "redundant_rate": redundant_rate,
    }
