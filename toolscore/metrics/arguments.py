"""Argument matching metrics."""

from typing import Any

from toolscore.adapters.base import ToolCall
from toolscore.matchers import Matcher


def _compare_values(expected: Any, actual: Any, strict: bool = False) -> bool:
    """Compare two values for equality with optional type flexibility.

    Args:
        expected: Expected value.
        actual: Actual value.
        strict: When True, require exact type and value equality throughout the
            entire structure — no int/float coercion, no string stripping.
            For containers (dict, list, tuple) the comparison recurses
            element-by-element in strict mode so that, for example,
            ``{"n": 1}`` does **not** match ``{"n": 1.0}``.  When False
            (default), int/float pairs are compared as floats and strings are
            stripped before comparison; containers use plain ``==`` which
            internally coerces numeric types.

    Returns:
        True if values match, False otherwise.
    """
    # Matcher check must come first — before strict type checks — so that
    # matchers work in both lenient and strict modes (including when they are
    # nested inside dicts/lists that strict mode recurses into).
    if isinstance(expected, Matcher):
        return expected.matches(actual)

    if strict:
        # Types must match exactly first
        if type(expected) is not type(actual):
            return False
        # Recurse into dicts
        if isinstance(expected, dict):
            if set(expected.keys()) != set(actual.keys()):
                return False
            return all(_compare_values(expected[k], actual[k], strict=True) for k in expected)
        # Recurse into lists and tuples (types already match from the check above)
        if isinstance(expected, (list, tuple)):
            if len(expected) != len(actual):
                return False
            return all(
                _compare_values(e, a, strict=True) for e, a in zip(expected, actual, strict=False)
            )
        # Scalar — type already matched; just check value
        return expected == actual  # type: ignore[no-any-return]

    # Lenient mode
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
    strict: bool = False,
) -> tuple[int, int, int]:
    """Calculate argument matching statistics.

    Args:
        expected_args: Expected arguments.
        actual_args: Actual arguments.
        strict: Passed through to :func:`_compare_values`.

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
        if key in actual_args and _compare_values(expected_val, actual_args[key], strict=strict):
            correct_count += 1

    return correct_count, expected_count, actual_count


def calculate_argument_f1(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    strict: bool = False,
) -> dict[str, float]:
    """Calculate F1 score for argument matching.

    Evaluates how well the arguments provided to each tool match
    the expected arguments.

    Args:
        gold_calls: Expected tool calls from gold standard.
        trace_calls: Actual tool calls from agent trace.
        strict: When True, disable int/float coercion and string stripping.
            Passed through to :func:`_compare_values`.

    Gold calls whose ``args is None`` carry a "do not check arguments"
    expectation (tool-name-only): they are skipped entirely from argument
    counting and never penalize the score.  An explicit ``args == {}`` keeps
    the strict "expect zero arguments" meaning.  When *every* matched gold call
    opts out of argument checking, there is nothing to score against, so the
    result is a perfect ``f1 == 1.0`` rather than an undefined 0/0.

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
    # Number of gold calls that matched a trace call but contributed nothing to
    # the argument counts: either "do not check arguments" (args is None), or a
    # genuinely argument-less pair ({} expected, {} provided).  Both are perfect
    # (vacuous) matches; we use them to resolve the nothing-counted case into
    # f1 == 1.0 rather than an undefined 0/0 -> 0.
    vacuous_matches = 0

    # Match calls by tool name and position
    for i, gold_call in enumerate(gold_calls):
        # Find corresponding trace call
        trace_call = None
        for j, tc in enumerate(trace_calls):
            if tc.tool == gold_call.tool and j >= i:
                trace_call = tc
                break

        # Gold call with args omitted (None) → "do not check arguments".
        # Skip it from argument counting entirely; a matched call is a perfect
        # (vacuous) arg match and must never lower precision or recall.
        if gold_call.args is None:
            if trace_call is not None:
                vacuous_matches += 1
            continue

        if trace_call:
            correct, expected, actual = _calculate_argument_match(
                gold_call.args, trace_call.args, strict=strict
            )
            total_correct += correct
            total_expected += expected
            total_actual += actual
            # "Expect zero args" met with zero args is a perfect match, not a
            # 0/0 hole (e.g. a correctly-called get_time()).
            if expected == 0 and actual == 0:
                vacuous_matches += 1
        else:
            # Call was missing, count expected args as missed
            if gold_call.args:
                total_expected += len(gold_call.args)

    # When every matched gold call was a vacuous arg match (opted out via
    # args=None, or zero-args expected and provided) and nothing concrete was
    # counted, the arguments are vacuously perfect.  Without this, an all-None
    # gold set — or an agent correctly calling no-argument tools — would fall
    # through to the 0/0 -> 0 division below and score f1 == 0.0.
    if total_expected == 0 and total_actual == 0 and vacuous_matches > 0:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

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
