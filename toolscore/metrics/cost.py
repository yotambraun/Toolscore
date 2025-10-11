"""Latency and cost attribution metrics."""

from toolscore.adapters.base import ToolCall


def calculate_latency(trace_calls: list[ToolCall]) -> dict[str, float]:
    """Calculate latency metrics from tool calls.

    Args:
        trace_calls: Tool calls with timing information.

    Returns:
        Dictionary containing:
        - total_duration: Total time spent on all tool calls (seconds)
        - average_duration: Average duration per call (seconds)
        - max_duration: Maximum duration of any single call (seconds)
        - min_duration: Minimum duration of any single call (seconds)
    """
    durations = [call.duration for call in trace_calls if call.duration is not None]

    if not durations:
        return {
            "total_duration": 0.0,
            "average_duration": 0.0,
            "max_duration": 0.0,
            "min_duration": 0.0,
        }

    return {
        "total_duration": sum(durations),
        "average_duration": sum(durations) / len(durations),
        "max_duration": max(durations),
        "min_duration": min(durations),
    }


def calculate_cost_attribution(trace_calls: list[ToolCall]) -> dict[str, float | dict[str, float]]:
    """Calculate cost attribution from tool calls.

    Args:
        trace_calls: Tool calls with cost information.

    Returns:
        Dictionary containing:
        - total_cost: Total cost of all tool calls (USD)
        - average_cost: Average cost per call (USD)
        - cost_by_tool: Dictionary mapping tool names to their total costs
    """
    costs = [call.cost for call in trace_calls if call.cost is not None]
    total_cost = sum(costs) if costs else 0.0
    average_cost = total_cost / len(costs) if costs else 0.0

    # Calculate cost per tool type
    cost_by_tool: dict[str, float] = {}
    for call in trace_calls:
        if call.cost is not None:
            cost_by_tool[call.tool] = cost_by_tool.get(call.tool, 0.0) + call.cost

    return {
        "total_cost": total_cost,
        "average_cost": average_cost,
        "cost_by_tool": cost_by_tool,
    }
