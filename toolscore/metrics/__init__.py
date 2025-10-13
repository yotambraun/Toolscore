"""Metrics for evaluating tool usage performance."""

from toolscore.metrics.accuracy import (
    calculate_invocation_accuracy,
    calculate_selection_accuracy,
)
from toolscore.metrics.arguments import calculate_argument_f1
from toolscore.metrics.cost import calculate_cost_attribution, calculate_latency
from toolscore.metrics.efficiency import calculate_redundant_call_rate
from toolscore.metrics.sequence import calculate_edit_distance
from toolscore.metrics.side_effects import calculate_side_effect_success_rate

# Optional LLM judge metrics (requires openai package)
try:
    from toolscore.metrics.llm_judge import (
        calculate_batch_semantic_correctness,
        calculate_semantic_correctness,
    )

    _llm_available = True
except ImportError:
    _llm_available = False
    calculate_semantic_correctness = None  # type: ignore[assignment]
    calculate_batch_semantic_correctness = None  # type: ignore[assignment]

__all__ = [
    "calculate_argument_f1",
    "calculate_cost_attribution",
    "calculate_edit_distance",
    "calculate_invocation_accuracy",
    "calculate_latency",
    "calculate_redundant_call_rate",
    "calculate_selection_accuracy",
    "calculate_side_effect_success_rate",
]

# Add LLM metrics if available
if _llm_available:
    __all__.extend([
        "calculate_batch_semantic_correctness",
        "calculate_semantic_correctness",
    ])
