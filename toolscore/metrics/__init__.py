"""Metrics for evaluating tool usage performance."""

from toolscore.metrics.accuracy import (
    calculate_invocation_accuracy,
    calculate_selection_accuracy,
)
from toolscore.metrics.arguments import calculate_argument_f1
from toolscore.metrics.cost import calculate_cost_attribution, calculate_latency
from toolscore.metrics.cost_estimator import (
    calculate_cost_savings,
    calculate_llm_cost,
    estimate_tokens,
    estimate_trace_cost,
    format_cost,
)
from toolscore.metrics.efficiency import calculate_redundant_call_rate

# LLM judge metrics. SDK imports are lazy (inside each backend), so the module
# imports cleanly regardless of which provider SDK (if any) is installed.
from toolscore.metrics.llm_judge import (
    JudgeConfig,
    calculate_batch_semantic_correctness,
    calculate_semantic_correctness,
)
from toolscore.metrics.sequence import calculate_edit_distance
from toolscore.metrics.side_effects import calculate_side_effect_success_rate
from toolscore.metrics.tool_correctness import (
    calculate_tool_correctness,
    calculate_tool_correctness_with_args,
)
from toolscore.metrics.trajectory import (
    calculate_partial_trajectory_accuracy,
    calculate_trajectory_accuracy,
)

__all__ = [
    "JudgeConfig",
    "calculate_argument_f1",
    "calculate_batch_semantic_correctness",
    "calculate_cost_attribution",
    "calculate_cost_savings",
    "calculate_edit_distance",
    "calculate_invocation_accuracy",
    "calculate_latency",
    "calculate_llm_cost",
    "calculate_partial_trajectory_accuracy",
    "calculate_redundant_call_rate",
    "calculate_selection_accuracy",
    "calculate_semantic_correctness",
    "calculate_side_effect_success_rate",
    "calculate_tool_correctness",
    "calculate_tool_correctness_with_args",
    "calculate_trajectory_accuracy",
    "estimate_tokens",
    "estimate_trace_cost",
    "format_cost",
]
