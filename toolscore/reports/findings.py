"""Behavior and safety findings shared by the console and Markdown reports.

The score answers "did the agent make the expected calls?". These findings answer
the questions the score does not: did calls fail, did the agent retry a failure
unchanged, did it pass a credential into a tool, did it make a forbidden call?
Each finding is a ``(severity, message)`` pair; an empty list means nothing to
report.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult


def behavior_findings(result: EvaluationResult) -> list[tuple[str, str]]:
    """Collect behavior and safety findings from an evaluation result.

    Args:
        result: The evaluation result.

    Returns:
        ``(severity, message)`` pairs, ``"error"`` first (forbidden calls and
        credentials), then ``"warning"`` (failed calls and blind retries).
        Call numbers are 1-based positions in the actual trace.
    """
    metrics = result.metrics
    findings: list[tuple[str, str]] = []

    for violation in (metrics.get("policy_metrics") or {}).get("violations", []):
        reason = f": {violation['reason']}" if violation.get("reason") else ""
        findings.append(
            (
                "error",
                f"call {violation['index'] + 1} {violation['tool']} matches forbidden rule "
                f"{violation['rule'] + 1}{reason}",
            )
        )

    for secret in (metrics.get("security_metrics") or {}).get("secrets", []):
        findings.append(
            (
                "error",
                f"call {secret['index'] + 1} {secret['tool']} passes a {secret['kind']} "
                f"in '{secret['path']}' ({secret['preview']})",
            )
        )

    efficiency = metrics.get("efficiency_metrics") or {}
    error_count = efficiency.get("error_count", 0)
    if error_count:
        failed = Counter(call.tool for call in result.trace_calls if call.is_error)
        tools = ", ".join(
            f"{tool} x{count}" if count > 1 else tool for tool, count in failed.most_common()
        )
        findings.append(
            (
                "warning",
                f"{error_count} of {efficiency.get('total_calls', len(result.trace_calls))} "
                f"tool calls failed ({tools})",
            )
        )
    retries = efficiency.get("retry_after_error_count", 0)
    if retries:
        findings.append(
            (
                "warning",
                f"{retries} call(s) retried a failed call with the same arguments",
            )
        )

    return findings
