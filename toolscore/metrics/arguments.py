"""Argument matching metrics."""

from typing import Any

from toolscore.adapters.base import ToolCall


def _compare_values(expected: Any, actual: Any) -> bool:
    """Compare two values for equality with type flexibility.

    Args:
        expected: Expected value.
        actual: Actual value.

    Returns:
        True if values match, False otherwise.
    """
    # Direct equality
    if expected == actual:
        return True

    # Type conversion attempts
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return float(expected) == float(actual)

    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip() == actual.strip()

    return False


def _calculate_argument_match(
    expected_args: dict[str, Any] | None,
    actual_args: dict[str, Any] | None,
) -> tuple[int, int, int]:
    """Calculate argument matching statistics.

    Args:
        expected_args: Expected arguments.
        actual_args: Actual arguments.

    Returns:
        Tuple of (correct_count, expected_count, actual_count).
    """
    if expected_args is None:
        expected_args = {}
    if actual_args is None:
        actual_args = {}

    expected_count = len(expected_args)
    actual_count = len(actual_args)
    correct_count = 0

    for key, expected_val in expected_args.items():
        if key in actual_args and _compare_values(expected_val, actual_args[key]):
            correct_count += 1

    return correct_count, expected_count, actual_count


def calculate_argument_f1(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
) -> dict[str, float]:
    """Calculate F1 score for argument matching.

    Evaluates how well the arguments provided to each tool match
    the expected arguments.

    Args:
        gold_calls: Expected tool calls from gold standard.
        trace_calls: Actual tool calls from agent trace.

    Returns:
        Dictionary containing:
        - precision: Proportion of provided arguments that were correct
        - recall: Proportion of expected arguments that were provided
        - f1: Harmonic mean of precision and recall
    """
    if not gold_calls or not trace_calls:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    total_correct = 0
    total_expected = 0
    total_actual = 0

    # Match calls by tool name and position
    for i, gold_call in enumerate(gold_calls):
        # Find corresponding trace call
        trace_call = None
        for j, tc in enumerate(trace_calls):
            if tc.tool == gold_call.tool and j >= i:
                trace_call = tc
                break

        if trace_call:
            correct, expected, actual = _calculate_argument_match(
                gold_call.args, trace_call.args
            )
            total_correct += correct
            total_expected += expected
            total_actual += actual
        else:
            # Call was missing, count expected args as missed
            if gold_call.args:
                total_expected += len(gold_call.args)

    # Calculate precision and recall
    precision = total_correct / total_actual if total_actual > 0 else 0.0
    recall = total_correct / total_expected if total_expected > 0 else 0.0

    # Calculate F1 score
    f1 = 2 * (precision * recall) / (precision + recall) if precision + recall > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }
