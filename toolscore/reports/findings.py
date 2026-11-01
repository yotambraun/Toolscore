"""Behavior and safety findings shared by the console and Markdown reports.

The score answers "did the agent make the expected calls?". These findings answer
the questions the score does not: did calls fail, did the agent retry a failure
unchanged, did it pass a credential into a tool, did it make a forbidden call,
and did it tell the truth about what its tools did (the honesty checks)? Each
finding is a ``(severity, message)`` pair; an empty list means nothing to
report. Honesty findings end with their rule ID in parentheses.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from toolscore.metrics.security import redact_secrets

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult


def behavior_findings(result: EvaluationResult) -> list[tuple[str, str]]:
    """Collect behavior and safety findings from an evaluation result.

    Args:
        result: The evaluation result.

    Returns:
        ``(severity, message)`` pairs, ``"error"`` first (forbidden calls,
        credentials, false success claims, escape hatches), then ``"warning"``
        (failed calls, blind retries, undisclosed warnings). Call numbers are
        1-based positions in the actual trace.
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
                f"call {secret['index'] + 1} {secret['tool']} passes a credential "
                f"({secret['kind']}) in '{secret['path']}': {secret['preview']}",
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
        noun = "call repeats" if retries == 1 else "calls repeat"
        findings.append(("warning", f"{retries} {noun} a failed call with the same arguments"))

    honesty = metrics.get("honesty_metrics") or {}
    for finding in honesty.get("findings", []):
        message = redact_secrets(f"{finding['message']} ({finding['rule']})")
        findings.append((finding["severity"], message))

    order = {"error": 0, "warning": 1}
    findings.sort(key=lambda item: order.get(item[0], 2))
    return findings
