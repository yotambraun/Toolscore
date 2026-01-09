"""Self-explaining metrics module for Toolscore.

This module generates human-readable explanations for evaluation metrics,
helping users understand exactly what went wrong and how to fix it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.adapters.base import ToolCall
    from toolscore.core import EvaluationResult


@dataclass
class Explanation:
    """A single explanation item with category and details."""

    category: str  # "missing", "extra", "mismatch", "tip", "info"
    message: str
    severity: str = "info"  # "error", "warning", "info", "success"
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricExplanation:
    """Explanations for a specific metric."""

    metric_name: str
    score: float
    score_description: str  # e.g., "3 of 4 correct"
    items: list[Explanation] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)


def _find_similar_names(name: str, candidates: set[str], threshold: float = 0.6) -> list[str]:
    """Find names in candidates that are similar to the given name.

    Args:
        name: Name to match
        candidates: Set of candidate names
        threshold: Minimum similarity ratio (0.0 to 1.0)

    Returns:
        List of similar names sorted by similarity
    """
    similar = []
    for candidate in candidates:
        ratio = SequenceMatcher(None, name.lower(), candidate.lower()).ratio()
        if ratio >= threshold:
            similar.append((candidate, ratio))
    return [name for name, _ in sorted(similar, key=lambda x: -x[1])]


def explain_selection_accuracy(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    accuracy: float,
) -> MetricExplanation:
    """Generate explanation for selection accuracy metric.

    Args:
        gold_calls: Expected tool calls
        trace_calls: Actual tool calls from agent
        accuracy: The calculated accuracy score

    Returns:
        MetricExplanation with detailed breakdown
    """
    gold_tools = [call.tool for call in gold_calls]
    trace_tools = [call.tool for call in trace_calls]

    # Count matches
    matches = sum(1 for g, t in zip(gold_tools, trace_tools, strict=False) if g == t)
    total = max(len(gold_tools), len(trace_tools))

    explanation = MetricExplanation(
        metric_name="Selection Accuracy",
        score=accuracy,
        score_description=f"{matches} of {total} correct" if total > 0 else "N/A",
    )

    gold_set = set(gold_tools)
    trace_set = set(trace_tools)

    # Find mismatches at each position
    for i, (g, t) in enumerate(zip(gold_tools, trace_tools, strict=False)):
        if g != t:
            similar = _find_similar_names(t, gold_set)
            if similar and similar[0] == g:
                explanation.items.append(
                    Explanation(
                        category="mismatch",
                        message=f"Position {i + 1}: Expected '{g}' but got '{t}' (similar names)",
                        severity="warning",
                        details={"position": i, "expected": g, "actual": t, "similar": True},
                    )
                )
            else:
                explanation.items.append(
                    Explanation(
                        category="mismatch",
                        message=f"Position {i + 1}: Expected '{g}' but got '{t}'",
                        severity="error",
                        details={"position": i, "expected": g, "actual": t},
                    )
                )

    # Extra calls at the end
    if len(trace_tools) > len(gold_tools):
        for i, tool in enumerate(trace_tools[len(gold_tools) :], start=len(gold_tools)):
            explanation.items.append(
                Explanation(
                    category="extra",
                    message=f"Position {i + 1}: Unexpected extra call to '{tool}'",
                    severity="warning",
                    details={"position": i, "tool": tool},
                )
            )

    # Missing calls at the end
    if len(gold_tools) > len(trace_tools):
        for i, tool in enumerate(gold_tools[len(trace_tools) :], start=len(trace_tools)):
            explanation.items.append(
                Explanation(
                    category="missing",
                    message=f"Position {i + 1}: Missing expected call to '{tool}'",
                    severity="error",
                    details={"position": i, "tool": tool},
                )
            )

    # Check for semantic similarity (different names, same intent)
    missing_in_trace = gold_set - trace_set
    extra_in_trace = trace_set - gold_set

    for missing in missing_in_trace:
        similar = _find_similar_names(missing, extra_in_trace, threshold=0.5)
        if similar:
            explanation.tips.append(
                f"'{missing}' might be equivalent to '{similar[0]}' - use --llm-judge to verify"
            )

    if explanation.items and not explanation.tips:
        explanation.tips.append("Use --llm-judge flag to catch semantic equivalence")

    return explanation


def explain_tool_correctness(
    tool_correctness_metrics: dict[str, Any],
) -> MetricExplanation:
    """Generate explanation for tool correctness metric.

    Args:
        tool_correctness_metrics: The tool correctness metrics dict

    Returns:
        MetricExplanation with detailed breakdown
    """
    correctness = tool_correctness_metrics.get("tool_correctness", 0.0)
    correct_count = tool_correctness_metrics.get("correct_count", 0)
    total_expected = tool_correctness_metrics.get("total_expected", 0)
    missing_tools = tool_correctness_metrics.get("missing_tools", [])
    extra_tools = tool_correctness_metrics.get("extra_tools", [])

    explanation = MetricExplanation(
        metric_name="Tool Correctness",
        score=correctness,
        score_description=f"{correct_count} of {total_expected} expected tools called",
    )

    for tool in missing_tools:
        explanation.items.append(
            Explanation(
                category="missing",
                message=f"Expected tool '{tool}' was never called",
                severity="error",
                details={"tool": tool},
            )
        )

    for tool in extra_tools:
        explanation.items.append(
            Explanation(
                category="extra",
                message=f"Tool '{tool}' was called but not expected",
                severity="warning",
                details={"tool": tool},
            )
        )

    if missing_tools:
        explanation.tips.append("Check that your agent has access to all required tools")
        explanation.tips.append("Verify tool names match exactly (case-sensitive)")

    return explanation


def explain_argument_metrics(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    argument_metrics: dict[str, Any],
) -> MetricExplanation:
    """Generate explanation for argument metrics.

    Args:
        gold_calls: Expected tool calls
        trace_calls: Actual tool calls from agent
        argument_metrics: The argument metrics dict

    Returns:
        MetricExplanation with detailed breakdown
    """
    f1 = argument_metrics.get("f1", 0.0)
    precision = argument_metrics.get("precision", 0.0)
    recall = argument_metrics.get("recall", 0.0)

    explanation = MetricExplanation(
        metric_name="Argument F1",
        score=f1,
        score_description=f"Precision: {precision:.1%}, Recall: {recall:.1%}",
    )

    # Analyze argument differences for matching tool calls
    min_len = min(len(gold_calls), len(trace_calls))

    for i in range(min_len):
        gold = gold_calls[i]
        trace = trace_calls[i]

        if gold.tool == trace.tool:
            # Same tool, check argument differences
            gold_args = set(gold.args.keys())
            trace_args = set(trace.args.keys())

            missing_args = gold_args - trace_args
            extra_args = trace_args - gold_args
            common_args = gold_args & trace_args

            for arg in missing_args:
                explanation.items.append(
                    Explanation(
                        category="missing",
                        message=f"'{gold.tool}': Missing argument '{arg}'",
                        severity="error",
                        details={"tool": gold.tool, "argument": arg, "position": i},
                    )
                )

            for arg in extra_args:
                explanation.items.append(
                    Explanation(
                        category="extra",
                        message=f"'{trace.tool}': Unexpected argument '{arg}'",
                        severity="warning",
                        details={"tool": trace.tool, "argument": arg, "position": i},
                    )
                )

            # Check value mismatches
            for arg in common_args:
                gold_val = gold.args[arg]
                trace_val = trace.args[arg]
                if gold_val != trace_val:
                    # Check for type mismatch vs value mismatch
                    if type(gold_val) != type(trace_val):
                        explanation.items.append(
                            Explanation(
                                category="mismatch",
                                message=f"'{gold.tool}.{arg}': Type mismatch - expected {type(gold_val).__name__}, got {type(trace_val).__name__}",
                                severity="error",
                                details={
                                    "tool": gold.tool,
                                    "argument": arg,
                                    "expected_type": type(gold_val).__name__,
                                    "actual_type": type(trace_val).__name__,
                                },
                            )
                        )
                    else:
                        # Truncate long values
                        gold_str = str(gold_val)[:50]
                        trace_str = str(trace_val)[:50]
                        if len(str(gold_val)) > 50:
                            gold_str += "..."
                        if len(str(trace_val)) > 50:
                            trace_str += "..."
                        explanation.items.append(
                            Explanation(
                                category="mismatch",
                                message=f"'{gold.tool}.{arg}': Value mismatch - expected '{gold_str}', got '{trace_str}'",
                                severity="warning",
                                details={
                                    "tool": gold.tool,
                                    "argument": arg,
                                    "expected": gold_val,
                                    "actual": trace_val,
                                },
                            )
                        )

    if precision < recall:
        explanation.tips.append("Low precision: Agent is passing extra/wrong arguments")
    if recall < precision:
        explanation.tips.append("Low recall: Agent is missing required arguments")

    return explanation


def explain_sequence_metrics(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    sequence_metrics: dict[str, Any],
) -> MetricExplanation:
    """Generate explanation for sequence metrics.

    Args:
        gold_calls: Expected tool calls
        trace_calls: Actual tool calls from agent
        sequence_metrics: The sequence metrics dict

    Returns:
        MetricExplanation with detailed breakdown
    """
    seq_accuracy = sequence_metrics.get("sequence_accuracy", 0.0)
    edit_distance = sequence_metrics.get("edit_distance", 0)

    gold_sequence = [call.tool for call in gold_calls]
    trace_sequence = [call.tool for call in trace_calls]

    explanation = MetricExplanation(
        metric_name="Sequence Accuracy",
        score=seq_accuracy,
        score_description=f"Edit distance: {edit_distance}",
    )

    if edit_distance > 0:
        explanation.items.append(
            Explanation(
                category="info",
                message=f"Expected sequence: {' -> '.join(gold_sequence)}",
                severity="info",
            )
        )
        explanation.items.append(
            Explanation(
                category="info",
                message=f"Actual sequence: {' -> '.join(trace_sequence)}",
                severity="info",
            )
        )

        # Try to identify specific issues
        if len(trace_sequence) > len(gold_sequence):
            explanation.items.append(
                Explanation(
                    category="extra",
                    message=f"Agent made {len(trace_sequence) - len(gold_sequence)} extra tool call(s)",
                    severity="warning",
                )
            )
        elif len(trace_sequence) < len(gold_sequence):
            explanation.items.append(
                Explanation(
                    category="missing",
                    message=f"Agent missed {len(gold_sequence) - len(trace_sequence)} tool call(s)",
                    severity="error",
                )
            )

        if edit_distance > len(gold_sequence) // 2:
            explanation.tips.append("Sequence is significantly different - review agent's planning logic")
        else:
            explanation.tips.append("Minor sequence differences - may be acceptable depending on task")

    return explanation


def explain_efficiency_metrics(
    efficiency_metrics: dict[str, Any],
) -> MetricExplanation:
    """Generate explanation for efficiency metrics.

    Args:
        efficiency_metrics: The efficiency metrics dict

    Returns:
        MetricExplanation with detailed breakdown
    """
    redundant_rate = efficiency_metrics.get("redundant_rate", 0.0)
    redundant_count = efficiency_metrics.get("redundant_count", 0)
    total_calls = efficiency_metrics.get("total_calls", 0)

    explanation = MetricExplanation(
        metric_name="Redundant Call Rate",
        score=1.0 - redundant_rate,  # Invert for display (lower is better)
        score_description=f"{redundant_count} of {total_calls} calls redundant",
    )

    if redundant_count > 0:
        explanation.items.append(
            Explanation(
                category="warning",
                message=f"Agent made {redundant_count} redundant/duplicate tool call(s)",
                severity="warning",
                details={"redundant_count": redundant_count},
            )
        )
        explanation.tips.append("Consider caching tool results or improving planning")

    return explanation


def generate_explanations(result: EvaluationResult) -> dict[str, MetricExplanation]:
    """Generate explanations for all metrics in an evaluation result.

    Args:
        result: The evaluation result

    Returns:
        Dictionary mapping metric names to their explanations
    """
    explanations = {}
    metrics = result.metrics

    # Selection Accuracy
    sel_acc = metrics.get("selection_accuracy", 0.0)
    explanations["selection_accuracy"] = explain_selection_accuracy(
        result.gold_calls, result.trace_calls, sel_acc
    )

    # Tool Correctness
    tool_correctness_metrics = metrics.get("tool_correctness_metrics", {})
    if tool_correctness_metrics:
        explanations["tool_correctness"] = explain_tool_correctness(tool_correctness_metrics)

    # Argument Metrics
    argument_metrics = metrics.get("argument_metrics", {})
    if argument_metrics:
        explanations["argument_metrics"] = explain_argument_metrics(
            result.gold_calls, result.trace_calls, argument_metrics
        )

    # Sequence Metrics
    sequence_metrics = metrics.get("sequence_metrics", {})
    if sequence_metrics:
        explanations["sequence_metrics"] = explain_sequence_metrics(
            result.gold_calls, result.trace_calls, sequence_metrics
        )

    # Efficiency Metrics
    efficiency_metrics = metrics.get("efficiency_metrics", {})
    if efficiency_metrics:
        explanations["efficiency_metrics"] = explain_efficiency_metrics(efficiency_metrics)

    return explanations


def get_top_issues(
    explanations: dict[str, MetricExplanation],
    max_issues: int = 5,
) -> list[Explanation]:
    """Get the top issues across all metrics, sorted by severity.

    Args:
        explanations: Dictionary of metric explanations
        max_issues: Maximum number of issues to return

    Returns:
        List of top issues sorted by severity
    """
    severity_order = {"error": 0, "warning": 1, "info": 2, "success": 3}

    all_issues = []
    for explanation in explanations.values():
        all_issues.extend(explanation.items)

    # Sort by severity
    all_issues.sort(key=lambda x: severity_order.get(x.severity, 99))

    return all_issues[:max_issues]


def get_all_tips(explanations: dict[str, MetricExplanation]) -> list[str]:
    """Get all unique tips from explanations.

    Args:
        explanations: Dictionary of metric explanations

    Returns:
        List of unique tips
    """
    tips = []
    seen = set()

    for explanation in explanations.values():
        for tip in explanation.tips:
            if tip not in seen:
                tips.append(tip)
                seen.add(tip)

    return tips
