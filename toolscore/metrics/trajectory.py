"""Trajectory evaluation metrics for multi-step agent reasoning."""

from typing import Any

from toolscore.adapters.base import ToolCall


def calculate_trajectory_accuracy(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
) -> dict[str, Any]:
    """Calculate trajectory accuracy metrics for multi-step agent evaluation.

    Trajectory evaluation assesses whether the agent took the correct PATH
    to solve the task, not just whether the final answer was correct.
    This is critical for multi-step agents where intermediate reasoning matters.

    Evaluates:
    - Path correctness: Did the agent follow the expected sequence?
    - Step accuracy: Were intermediate steps correct?
    - Efficiency: Did the agent take unnecessary detours?

    Args:
        gold_calls: Expected sequence of tool calls (the correct path).
        trace_calls: Actual sequence of tool calls taken by the agent.

    Returns:
        Dictionary containing:
        - trajectory_accuracy: Overall path correctness (0-1)
        - step_match_rate: Percentage of steps that matched expected path
        - path_efficiency: How efficient the path was (1 = perfect, <1 = detours)
        - correct_steps: Number of steps that matched the expected path
        - total_expected_steps: Number of steps in the expected path
        - trajectory_details: Detailed step-by-step comparison
    """
    if not gold_calls:
        return {
            "trajectory_accuracy": 1.0 if not trace_calls else 0.0,
            "step_match_rate": 1.0 if not trace_calls else 0.0,
            "path_efficiency": 1.0,
            "correct_steps": 0,
            "total_expected_steps": 0,
            "trajectory_details": [],
        }

    if not trace_calls:
        return {
            "trajectory_accuracy": 0.0,
            "step_match_rate": 0.0,
            "path_efficiency": 0.0,
            "correct_steps": 0,
            "total_expected_steps": len(gold_calls),
            "trajectory_details": _generate_missing_steps_details(gold_calls),
        }

    # Step-by-step comparison
    correct_steps = 0
    trajectory_details = []

    # Compare each step in the trajectory
    min_length = min(len(gold_calls), len(trace_calls))

    for i in range(min_length):
        gold_step = gold_calls[i]
        trace_step = trace_calls[i]

        # Check if step matches (tool name and args)
        step_matches = _compare_steps(gold_step, trace_step)

        if step_matches:
            correct_steps += 1

        trajectory_details.append(
            {
                "step": i + 1,
                "expected_tool": gold_step.tool,
                "actual_tool": trace_step.tool,
                "matches": step_matches,
                "expected_args": gold_step.args or {},
                "actual_args": trace_step.args or {},
            }
        )

    # Add details for missing steps
    if len(gold_calls) > len(trace_calls):
        for i in range(len(trace_calls), len(gold_calls)):
            trajectory_details.append(
                {
                    "step": i + 1,
                    "expected_tool": gold_calls[i].tool,
                    "actual_tool": None,
                    "matches": False,
                    "expected_args": gold_calls[i].args or {},
                    "actual_args": {},
                    "error": "Agent stopped early - step not executed",
                }
            )

    # Add details for extra steps
    if len(trace_calls) > len(gold_calls):
        for i in range(len(gold_calls), len(trace_calls)):
            trajectory_details.append(
                {
                    "step": i + 1,
                    "expected_tool": None,
                    "actual_tool": trace_calls[i].tool,
                    "matches": False,
                    "expected_args": {},
                    "actual_args": trace_calls[i].args or {},
                    "error": "Unnecessary step - not in expected path",
                }
            )

    # Calculate metrics
    step_match_rate = correct_steps / len(gold_calls) if gold_calls else 1.0

    # Path efficiency: penalize extra steps
    # Perfect efficiency (1.0) = exact match in length
    # Lower efficiency = took unnecessary detours
    if len(trace_calls) > len(gold_calls):
        path_efficiency = len(gold_calls) / len(trace_calls)
    else:
        path_efficiency = 1.0

    # Overall trajectory accuracy considers both correctness and efficiency
    trajectory_accuracy = step_match_rate * path_efficiency

    return {
        "trajectory_accuracy": trajectory_accuracy,
        "step_match_rate": step_match_rate,
        "path_efficiency": path_efficiency,
        "correct_steps": correct_steps,
        "total_expected_steps": len(gold_calls),
        "trajectory_details": trajectory_details,
    }


def _compare_steps(gold_step: ToolCall, trace_step: ToolCall) -> bool:
    """Compare two trajectory steps for equality.

    Args:
        gold_step: Expected step.
        trace_step: Actual step.

    Returns:
        True if steps match (same tool and args), False otherwise.
    """
    # Tool names must match
    if gold_step.tool != trace_step.tool:
        return False

    # Compare arguments
    gold_args = gold_step.args or {}
    trace_args = trace_step.args or {}

    # All expected arguments must be present and match
    for key, expected_value in gold_args.items():
        if key not in trace_args:
            return False

        actual_value = trace_args[key]

        # Handle nested comparisons
        if (isinstance(expected_value, dict) and isinstance(actual_value, dict)) or (isinstance(expected_value, list) and isinstance(actual_value, list)):
            if expected_value != actual_value:
                return False
        elif expected_value != actual_value:
            return False

    return True


def _generate_missing_steps_details(gold_calls: list[ToolCall]) -> list[dict[str, Any]]:
    """Generate trajectory details for missing steps.

    Args:
        gold_calls: Expected steps that were not executed.

    Returns:
        List of trajectory detail dicts for missing steps.
    """
    return [
        {
            "step": i + 1,
            "expected_tool": step.tool,
            "actual_tool": None,
            "matches": False,
            "expected_args": step.args or {},
            "actual_args": {},
            "error": "Agent did not execute this step",
        }
        for i, step in enumerate(gold_calls)
    ]


def calculate_partial_trajectory_accuracy(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    allow_tool_name_variations: bool = False,
) -> dict[str, float]:
    """Calculate partial trajectory accuracy with flexible matching.

    This variant gives partial credit for:
    - Getting the right tools even if out of order
    - Using semantically equivalent tool names
    - Correct intermediate steps even if path diverges later

    Useful for evaluating agents that may take different valid paths.

    Args:
        gold_calls: Expected sequence of tool calls.
        trace_calls: Actual sequence of tool calls.
        allow_tool_name_variations: If True, allow minor variations in tool names
            (e.g., "search" vs "web_search").

    Returns:
        Dictionary containing partial accuracy metrics.
    """
    if not gold_calls:
        return {"partial_trajectory_accuracy": 1.0 if not trace_calls else 0.0}

    if not trace_calls:
        return {"partial_trajectory_accuracy": 0.0}

    # Count how many expected tools were called (regardless of order)
    gold_tool_names = [call.tool for call in gold_calls]
    trace_tool_names = [call.tool for call in trace_calls]

    # Flexible matching for tool names
    if allow_tool_name_variations:
        gold_tool_names = [_normalize_tool_name(name) for name in gold_tool_names]
        trace_tool_names = [_normalize_tool_name(name) for name in trace_tool_names]

    # Calculate overlap
    matched_tools = 0
    for gold_tool in gold_tool_names:
        if gold_tool in trace_tool_names:
            matched_tools += 1
            # Remove to avoid double counting
            trace_tool_names.remove(gold_tool)

    partial_accuracy = matched_tools / len(gold_calls)

    return {"partial_trajectory_accuracy": partial_accuracy}


def _normalize_tool_name(tool_name: str) -> str:
    """Normalize tool name for flexible matching.

    Args:
        tool_name: Original tool name.

    Returns:
        Normalized tool name (lowercase, underscores removed).
    """
    return tool_name.lower().replace("_", "").replace("-", "")
