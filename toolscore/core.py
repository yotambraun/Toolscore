"""Core evaluation logic for Toolscore."""

import json
from pathlib import Path
from typing import Any

from toolscore.adapters import AnthropicAdapter, CustomAdapter, LangChainAdapter, OpenAIAdapter
from toolscore.adapters.base import BaseAdapter, ToolCall
from toolscore.metrics import (
    calculate_argument_f1,
    calculate_cost_attribution,
    calculate_edit_distance,
    calculate_invocation_accuracy,
    calculate_latency,
    calculate_redundant_call_rate,
    calculate_selection_accuracy,
    calculate_side_effect_success_rate,
)
from toolscore.validators import FileSystemValidator, HTTPValidator, SQLValidator


class EvaluationResult:
    """Container for evaluation results."""

    def __init__(self) -> None:
        """Initialize evaluation result."""
        self.metrics: dict[str, Any] = {}
        self.gold_calls: list[ToolCall] = []
        self.trace_calls: list[ToolCall] = []

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary.

        Returns:
            Dictionary representation of the evaluation result.
        """
        return {
            "metrics": self.metrics,
            "gold_calls_count": len(self.gold_calls),
            "trace_calls_count": len(self.trace_calls),
        }


def load_gold_standard(file_path: str | Path) -> list[ToolCall]:
    """Load gold standard specification from JSON file.

    Args:
        file_path: Path to gold_calls.json file.

    Returns:
        List of expected tool calls.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If file format is invalid.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Gold standard file not found: {file_path}")

    with path.open() as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Gold standard must be a JSON array of tool calls")

    gold_calls = []
    for item in data:
        if not isinstance(item, dict):
            continue

        tool_name = item.get("tool")
        if not tool_name:
            continue

        args = item.get("args", {})
        side_effects = item.get("side_effects", {})
        description = item.get("description", "")

        metadata = {"side_effects": side_effects}
        if description:
            metadata["description"] = description

        gold_calls.append(
            ToolCall(
                tool=tool_name,
                args=args,
                metadata=metadata,
            )
        )

    return gold_calls


def load_trace(
    file_path: str | Path,
    format: str = "auto",
) -> list[ToolCall]:
    """Load agent trace from JSON file.

    Args:
        file_path: Path to trace file.
        format: Trace format ('auto', 'openai', 'anthropic', 'langchain', 'custom').

    Returns:
        List of tool calls from the trace.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If format is invalid or unsupported.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Trace file not found: {file_path}")

    with path.open() as f:
        data = json.load(f)

    # Select adapter
    adapter: BaseAdapter
    if format == "auto":
        adapter = _detect_format(data)
    elif format == "openai":
        adapter = OpenAIAdapter()
    elif format == "anthropic":
        adapter = AnthropicAdapter()
    elif format == "langchain":
        adapter = LangChainAdapter()
    elif format == "custom":
        adapter = CustomAdapter()
    else:
        raise ValueError(f"Unsupported format: {format}")

    return adapter.parse(data)


def _detect_format(data: Any) -> BaseAdapter:
    """Auto-detect trace format.

    Args:
        data: Trace data to analyze.

    Returns:
        Appropriate adapter for the detected format.
    """
    # Check for OpenAI format
    if isinstance(data, dict) and ("messages" in data or "choices" in data):
        return OpenAIAdapter()

    if isinstance(data, list) and data:
        first_item = data[0]
        if isinstance(first_item, dict):
            # Check for Anthropic format
            if first_item.get("role") == "assistant" and isinstance(
                first_item.get("content"), list
            ):
                return AnthropicAdapter()

            # Check for OpenAI messages
            if "function_call" in first_item or "tool_calls" in first_item:
                return OpenAIAdapter()

    # Default to custom format
    return CustomAdapter()


def evaluate_trace(
    gold_file: str | Path,
    trace_file: str | Path,
    format: str = "auto",
    validate_side_effects: bool = True,
) -> EvaluationResult:
    """Evaluate an agent's trace against gold standard.

    Args:
        gold_file: Path to gold standard specification.
        trace_file: Path to agent trace.
        format: Trace format ('auto', 'openai', 'anthropic', 'custom').
        validate_side_effects: Whether to validate side effects.

    Returns:
        EvaluationResult containing all computed metrics.

    Raises:
        FileNotFoundError: If files don't exist.
        ValueError: If file formats are invalid.
    """
    # Load data
    gold_calls = load_gold_standard(gold_file)
    trace_calls = load_trace(trace_file, format=format)

    # Create result
    result = EvaluationResult()
    result.gold_calls = gold_calls
    result.trace_calls = trace_calls

    # Calculate metrics
    result.metrics["invocation_accuracy"] = calculate_invocation_accuracy(
        gold_calls, trace_calls
    )
    result.metrics["selection_accuracy"] = calculate_selection_accuracy(gold_calls, trace_calls)

    sequence_metrics = calculate_edit_distance(gold_calls, trace_calls)
    result.metrics["sequence_metrics"] = sequence_metrics

    argument_metrics = calculate_argument_f1(gold_calls, trace_calls)
    result.metrics["argument_metrics"] = argument_metrics

    efficiency_metrics = calculate_redundant_call_rate(gold_calls, trace_calls)
    result.metrics["efficiency_metrics"] = efficiency_metrics

    # Latency and cost (if available)
    latency_metrics = calculate_latency(trace_calls)
    if latency_metrics["total_duration"] > 0:
        result.metrics["latency_metrics"] = latency_metrics

    cost_metrics = calculate_cost_attribution(trace_calls)
    total_cost = cost_metrics.get("total_cost", 0.0)
    if isinstance(total_cost, (int, float)) and total_cost > 0:
        result.metrics["cost_metrics"] = cost_metrics

    # Side effects validation
    if validate_side_effects:
        validators = {
            "http_ok": HTTPValidator().validate,
            "file_exists": FileSystemValidator().validate,
            "sql_rows": SQLValidator().validate,
        }

        side_effect_metrics = calculate_side_effect_success_rate(
            gold_calls, trace_calls, validators
        )
        result.metrics["side_effect_metrics"] = side_effect_metrics

    return result
