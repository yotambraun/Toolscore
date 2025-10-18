"""Tool correctness metric for evaluating tool selection accuracy.

This metric evaluates whether the agent called the correct tools and in what
proportion. It's a deterministic measure that complements semantic evaluation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.adapters.base import ToolCall


def calculate_tool_correctness(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    strict_order: bool = False,
) -> dict[str, Any]:
    """Calculate tool correctness metric.

    This metric evaluates whether the agent called the correct tools.
    Unlike selection accuracy which checks if each individual call matches,
    this checks if all expected tools were called at least once.

    Args:
        gold_calls: Expected tool calls
        trace_calls: Actual tool calls from agent
        strict_order: If True, tools must be called in the exact order

    Returns:
        Dictionary containing:
        - tool_correctness: Proportion of expected tools that were called (0.0 to 1.0)
        - expected_tools: Set of expected tool names
        - called_tools: Set of actually called tool names
        - missing_tools: Tools that should have been called but weren't
        - extra_tools: Tools that were called but weren't expected
        - correct_count: Number of correct tool calls
        - total_expected: Total number of expected tools

    Example:
        >>> gold = [
        ...     ToolCall(tool="search", args={"q": "test"}),
        ...     ToolCall(tool="read_file", args={"path": "data.txt"})
        ... ]
        >>> trace = [
        ...     ToolCall(tool="search", args={"query": "test"}),
        ...     ToolCall(tool="read_file", args={"path": "data.txt"}),
        ...     ToolCall(tool="write_file", args={"path": "out.txt"})
        ... ]
        >>> result = calculate_tool_correctness(gold, trace)
        >>> result["tool_correctness"]
        1.0  # All expected tools were called
        >>> result["extra_tools"]
        {'write_file'}  # Called but not expected
    """
    if not gold_calls:
        return {
            "tool_correctness": 1.0 if not trace_calls else 0.0,
            "expected_tools": [],
            "called_tools": sorted(list({call.tool for call in trace_calls})),
            "missing_tools": [],
            "extra_tools": sorted(list({call.tool for call in trace_calls})),
            "correct_count": 0,
            "total_expected": 0,
        }

    # Extract tool names
    expected_tools = {call.tool for call in gold_calls}
    called_tools = {call.tool for call in trace_calls}

    if strict_order:
        # For strict order, check if the sequence of tool names matches
        expected_sequence = [call.tool for call in gold_calls]
        called_sequence = [call.tool for call in trace_calls]

        # Count how many match in order
        correct_count = 0
        for i, expected_tool in enumerate(expected_sequence):
            if i < len(called_sequence) and called_sequence[i] == expected_tool:
                correct_count += 1

        tool_correctness = correct_count / len(expected_sequence) if expected_sequence else 1.0

        return {
            "tool_correctness": tool_correctness,
            "expected_tools": sorted(list(expected_tools)),
            "called_tools": sorted(list(called_tools)),
            "expected_sequence": expected_sequence,
            "called_sequence": called_sequence,
            "correct_count": correct_count,
            "total_expected": len(expected_sequence),
            "strict_order": True,
        }

    # For non-strict order, check if all expected tools appear
    missing_tools = expected_tools - called_tools
    extra_tools = called_tools - expected_tools
    correct_tools = expected_tools & called_tools

    tool_correctness = len(correct_tools) / len(expected_tools) if expected_tools else 1.0

    return {
        "tool_correctness": tool_correctness,
        "expected_tools": sorted(list(expected_tools)),
        "called_tools": sorted(list(called_tools)),
        "missing_tools": sorted(list(missing_tools)),
        "extra_tools": sorted(list(extra_tools)),
        "correct_count": len(correct_tools),
        "total_expected": len(expected_tools),
        "strict_order": False,
    }


def calculate_tool_correctness_with_args(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
) -> dict[str, Any]:
    """Calculate tool correctness including argument validation.

    This is a stricter version that checks both tool names and arguments.

    Args:
        gold_calls: Expected tool calls
        trace_calls: Actual tool calls from agent

    Returns:
        Dictionary containing:
        - tool_correctness_strict: Proportion where both tool and args match
        - matches: List of (gold_call, trace_call) tuples that match
        - mismatches: List of calls that don't match

    Example:
        >>> gold = [ToolCall(tool="search", args={"q": "test"})]
        >>> trace = [ToolCall(tool="search", args={"q": "test"})]
        >>> result = calculate_tool_correctness_with_args(gold, trace)
        >>> result["tool_correctness_strict"]
        1.0
    """
    if not gold_calls:
        return {
            "tool_correctness_strict": 1.0 if not trace_calls else 0.0,
            "matches": [],
            "mismatches": list(trace_calls) if trace_calls else [],
        }

    matches = []
    mismatches = []

    # Create a working copy of trace calls for matching
    remaining_trace = list(trace_calls)

    for gold_call in gold_calls:
        found_match = False
        for i, trace_call in enumerate(remaining_trace):
            if gold_call.tool == trace_call.tool and gold_call.args == trace_call.args:
                matches.append((gold_call, trace_call))
                remaining_trace.pop(i)
                found_match = True
                break

        if not found_match:
            mismatches.append(gold_call)

    # Add any remaining trace calls as mismatches
    mismatches.extend(remaining_trace)

    tool_correctness_strict = len(matches) / len(gold_calls) if gold_calls else 1.0

    return {
        "tool_correctness_strict": tool_correctness_strict,
        "matches": matches,
        "mismatches": mismatches,
        "match_count": len(matches),
        "total_expected": len(gold_calls),
    }
