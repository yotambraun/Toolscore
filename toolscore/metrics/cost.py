"""Latency and cost attribution metrics.

Traces often carry no timings or costs. A missing value is **unknown**, never
zero: the totals are ``None`` when no call has the value, and ``status`` says
how much of the trace was measured (``"measured"``: every call, ``"partial"``:
some, the totals cover only those; ``"unknown"``: none). Reports print
"unknown" instead of ``0``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.adapters.base import ToolCall


def _coverage(measured: int, total: int) -> str:
    """``"measured"``, ``"partial"`` or ``"unknown"`` for ``measured`` of ``total`` calls."""
    if measured == total:
        return "measured"
    return "partial" if measured else "unknown"


def calculate_latency(trace_calls: list[ToolCall]) -> dict[str, Any]:
    """Calculate latency metrics from tool calls.

    Args:
        trace_calls: Tool calls with timing information.

    Returns:
        Dictionary containing:
        - total_duration: Total time spent on the timed calls (seconds), or
          ``None`` when no call was timed
        - average_duration: Average duration per timed call (seconds) or ``None``
        - max_duration: Maximum duration of any timed call (seconds) or ``None``
        - min_duration: Minimum duration of any timed call (seconds) or ``None``
        - measured_calls: Calls that carry a duration
        - total_calls: All calls
        - status: ``"measured"``, ``"partial"`` or ``"unknown"`` (see the module docstring)
    """
    durations = [call.duration for call in trace_calls if call.duration is not None]
    coverage = {
        "measured_calls": len(durations),
        "total_calls": len(trace_calls),
        "status": _coverage(len(durations), len(trace_calls)),
    }
    if not durations:
        empty: float | None = 0.0 if not trace_calls else None
        return {
            "total_duration": empty,
            "average_duration": empty,
            "max_duration": empty,
            "min_duration": empty,
            **coverage,
        }

    return {
        "total_duration": sum(durations),
        "average_duration": sum(durations) / len(durations),
        "max_duration": max(durations),
        "min_duration": min(durations),
        **coverage,
    }


def calculate_cost_attribution(trace_calls: list[ToolCall]) -> dict[str, Any]:
    """Calculate cost attribution from tool calls.

    Args:
        trace_calls: Tool calls with cost information.

    Returns:
        Dictionary containing:
        - total_cost: Total cost of the calls that carry one (USD), or ``None``
          when no call does
        - average_cost: Average cost per costed call (USD) or ``None``
        - cost_by_tool: Dictionary mapping tool names to their total costs
          (costed calls only)
        - measured_calls, total_calls, status: as for :func:`calculate_latency`
    """
    costs = [call.cost for call in trace_calls if call.cost is not None]

    # Calculate cost per tool type
    cost_by_tool: dict[str, float] = {}
    for call in trace_calls:
        if call.cost is not None:
            cost_by_tool[call.tool] = cost_by_tool.get(call.tool, 0.0) + call.cost

    empty: float | None = 0.0 if not trace_calls else None
    return {
        "total_cost": sum(costs) if costs else empty,
        "average_cost": sum(costs) / len(costs) if costs else empty,
        "cost_by_tool": cost_by_tool,
        "measured_calls": len(costs),
        "total_calls": len(trace_calls),
        "status": _coverage(len(costs), len(trace_calls)),
    }


def format_measure(metrics: dict[str, Any] | None, key: str, unit: str = "s") -> str:
    """Render one latency or cost value for a report: a number, or ``"unknown"``.

    Args:
        metrics: ``latency_metrics`` or ``cost_metrics`` (``None`` when absent).
        key: The value to render (``"total_duration"``, ``"total_cost"``...).
        unit: ``"s"`` for seconds, ``"$"`` for US dollars.

    Returns:
        ``"1.234s"`` / ``"$0.0042"``, with ``" (3 of 5 calls)"`` when only some
        calls were measured, or ``"unknown"``.
    """
    values = metrics or {}
    value = values.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "unknown"
    text = f"${value:.4f}" if unit == "$" else f"{value:.3f}s"
    if values.get("status") == "partial":
        text += f" ({values.get('measured_calls')} of {values.get('total_calls')} calls)"
    return text
