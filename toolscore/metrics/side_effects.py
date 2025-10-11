"""Side-effect validation metrics."""

from typing import Any

from toolscore.adapters.base import ToolCall


def calculate_side_effect_success_rate(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    validators: dict[str, Any] | None = None,
) -> dict[str, int | float | list[dict[str, Any]]]:
    """Calculate side-effect success rate.

    Evaluates whether tool calls achieved their intended side effects
    or outcomes.

    Args:
        gold_calls: Expected tool calls with side_effects specifications.
        trace_calls: Actual tool calls from agent trace.
        validators: Optional dict of validator functions for side effects.

    Returns:
        Dictionary containing:
        - total_checks: Total number of side effect checks
        - passed_checks: Number of passed checks
        - success_rate: Proportion of checks that passed (0-1)
        - details: List of detailed check results
    """
    if validators is None:
        validators = {}

    total_checks = 0
    passed_checks = 0
    details: list[dict[str, Any]] = []

    for i, gold_call in enumerate(gold_calls):
        # Get side_effects from metadata
        side_effects = gold_call.metadata.get("side_effects", {})

        if not side_effects:
            continue

        # Find corresponding trace call
        trace_call = None
        for j, tc in enumerate(trace_calls):
            if tc.tool == gold_call.tool and j >= i:
                trace_call = tc
                break

        if not trace_call:
            # Call wasn't made, all side effects fail
            for check_name in side_effects:
                total_checks += 1
                details.append(
                    {
                        "tool": gold_call.tool,
                        "check": check_name,
                        "passed": False,
                        "reason": "Tool call not found in trace",
                    }
                )
            continue

        # Validate each side effect
        for check_name, expected_value in side_effects.items():
            total_checks += 1

            # Use validator if available
            if check_name in validators:
                validator = validators[check_name]
                try:
                    passed = validator(trace_call, expected_value)
                    reason = "Validator passed" if passed else "Validator failed"
                except Exception as e:
                    passed = False
                    reason = f"Validator error: {e}"
            else:
                # Default validation: check if key exists in result
                passed = False
                reason = "No validator available"

            if passed:
                passed_checks += 1

            details.append(
                {
                    "tool": gold_call.tool,
                    "check": check_name,
                    "passed": passed,
                    "reason": reason,
                }
            )

    success_rate = passed_checks / total_checks if total_checks > 0 else 1.0

    return {
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "success_rate": success_rate,
        "details": details,
    }
