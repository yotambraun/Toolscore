"""Core evaluation logic for Toolscore."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from toolscore.adapters import (
    AnthropicAdapter,
    CustomAdapter,
    GeminiAdapter,
    LangChainAdapter,
    MCPAdapter,
    OpenAIAdapter,
)
from toolscore.adapters.base import BaseAdapter, ToolCall
from toolscore.metrics import (
    calculate_argument_f1,
    calculate_cost_attribution,
    calculate_edit_distance,
    calculate_invocation_accuracy,
    calculate_latency,
    calculate_redundant_call_rate,
    calculate_selection_accuracy,
    calculate_semantic_correctness,
    calculate_side_effect_success_rate,
    calculate_tool_correctness,
    calculate_trajectory_accuracy,
)
from toolscore.validators import (
    FileSystemValidator,
    HTTPValidator,
    SQLValidator,
    calculate_schema_validation_metrics,
)


class EvaluationResult:
    """Container for evaluation results."""

    # Default weights for composite score
    DEFAULT_WEIGHTS: ClassVar[dict[str, float]] = {
        "selection_accuracy": 0.4,
        "argument_f1": 0.3,
        "sequence_accuracy": 0.2,
        "redundant_rate": 0.1,
    }

    def __init__(self) -> None:
        """Initialize evaluation result."""
        self.metrics: dict[str, Any] = {}
        self.gold_calls: list[ToolCall] = []
        self.trace_calls: list[ToolCall] = []
        self._weights: dict[str, float] = dict(self.DEFAULT_WEIGHTS)

    @property
    def score(self) -> float:
        """Compute weighted composite score from key metrics.

        Default weights: selection_accuracy=0.4, argument_f1=0.3,
        sequence_accuracy=0.2, redundant_rate=0.1.

        Returns:
            Composite score between 0.0 and 1.0.
        """
        sel = self.selection_accuracy
        arg = self.argument_f1
        seq = self.sequence_accuracy
        red = float(self.metrics.get("efficiency_metrics", {}).get("redundant_rate", 0.0))

        w = self._weights
        composite: float = (
            w["selection_accuracy"] * sel
            + w["argument_f1"] * arg
            + w["sequence_accuracy"] * seq
            + w["redundant_rate"] * (1.0 - red)
        )
        return composite

    @property
    def selection_accuracy(self) -> float:
        """Selection accuracy: proportion of calls matching expected tool names."""
        return float(self.metrics.get("selection_accuracy", 0.0))

    @property
    def argument_f1(self) -> float:
        """Argument F1 score across all tool calls."""
        return float(self.metrics.get("argument_metrics", {}).get("f1", 0.0))

    @property
    def sequence_accuracy(self) -> float:
        """Sequence accuracy based on edit distance."""
        return float(self.metrics.get("sequence_metrics", {}).get("sequence_accuracy", 0.0))

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary.

        Returns:
            Dictionary representation of the evaluation result.
        """
        return {
            "metrics": self.metrics,
            "score": self.score,
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
        format: Trace format ('auto', 'openai', 'anthropic', 'gemini', 'mcp', 'langchain', 'custom').

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
    elif format == "gemini":
        adapter = GeminiAdapter()
    elif format == "mcp":
        adapter = MCPAdapter()
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
    # Check for MCP format (JSON-RPC 2.0)
    if isinstance(data, dict) and "jsonrpc" in data:
        return MCPAdapter()

    # Check for Gemini format (candidates with function calls)
    if isinstance(data, dict) and "candidates" in data:
        return GeminiAdapter()

    # Check for OpenAI format
    if isinstance(data, dict) and ("messages" in data or "choices" in data):
        return OpenAIAdapter()

    if isinstance(data, list) and data:
        first_item = data[0]
        if isinstance(first_item, dict):
            # Check for Gemini format (parts with functionCall)
            if "parts" in first_item:
                parts = first_item["parts"]
                if isinstance(parts, list) and parts and any("functionCall" in p for p in parts if isinstance(p, dict)):
                    return GeminiAdapter()

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
    use_llm_judge: bool = False,
    llm_judge_model: str = "gpt-4o-mini",
    llm_judge_api_key: str | None = None,
) -> EvaluationResult:
    """Evaluate an agent's trace against gold standard.

    Args:
        gold_file: Path to gold standard specification.
        trace_file: Path to agent trace.
        format: Trace format ('auto', 'openai', 'anthropic', 'gemini', 'langchain', 'custom').
        validate_side_effects: Whether to validate side effects.
        use_llm_judge: Whether to use LLM-as-a-judge for semantic evaluation.
        llm_judge_model: Model to use for LLM judge (default: gpt-4o-mini).
        llm_judge_api_key: OpenAI API key (defaults to OPENAI_API_KEY env var).

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

    tool_correctness_metrics = calculate_tool_correctness(gold_calls, trace_calls)
    result.metrics["tool_correctness_metrics"] = tool_correctness_metrics

    sequence_metrics = calculate_edit_distance(gold_calls, trace_calls)
    result.metrics["sequence_metrics"] = sequence_metrics

    # Trajectory evaluation: assess the path taken by the agent
    trajectory_metrics = calculate_trajectory_accuracy(gold_calls, trace_calls)
    result.metrics["trajectory_metrics"] = trajectory_metrics

    argument_metrics = calculate_argument_f1(gold_calls, trace_calls)
    result.metrics["argument_metrics"] = argument_metrics

    efficiency_metrics = calculate_redundant_call_rate(gold_calls, trace_calls)
    result.metrics["efficiency_metrics"] = efficiency_metrics

    # Schema validation (if schemas are provided in metadata)
    schema_metrics = calculate_schema_validation_metrics(gold_calls, trace_calls)
    if schema_metrics["total_validated"] > 0:
        result.metrics["schema_metrics"] = schema_metrics

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

    # LLM-as-a-judge semantic evaluation
    if use_llm_judge:
        try:
            semantic_metrics = calculate_semantic_correctness(
                gold_calls,
                trace_calls,
                api_key=llm_judge_api_key,
                model=llm_judge_model,
            )
            result.metrics["semantic_metrics"] = semantic_metrics
        except ImportError:
            # If openai not installed, skip silently
            pass
        except ValueError as e:
            # If API key missing, add warning to metrics
            result.metrics["semantic_metrics"] = {
                "error": str(e),
                "semantic_score": None,
            }

    return result


def _dicts_to_tool_calls(items: list[dict[str, Any]]) -> list[ToolCall]:
    """Convert a list of dicts to ToolCall objects.

    Each dict should have at least a 'tool' key and optionally 'args'.

    Args:
        items: List of dicts with tool call data.

    Returns:
        List of ToolCall objects.

    Raises:
        ValueError: If items is not a list of dicts or missing 'tool' keys.
    """
    if not isinstance(items, list):
        raise ValueError("Expected a list of dicts, got " + type(items).__name__)

    calls = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Item at index {i} is not a dict")
        tool_name = item.get("tool")
        if not tool_name:
            raise ValueError(f"Item at index {i} is missing 'tool' key")
        calls.append(
            ToolCall(
                tool=tool_name,
                args=item.get("args", {}),
            )
        )
    return calls


def evaluate(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> EvaluationResult:
    """Evaluate tool calls by comparing actual against expected (in-memory).

    This is the simplest way to use Toolscore - pass Python dicts directly,
    no file I/O required.

    Args:
        expected: List of expected tool calls, each a dict with 'tool' and optional 'args'.
        actual: List of actual tool calls from your agent, same format.
        weights: Optional custom weights for the composite score.
            Keys: 'selection_accuracy', 'argument_f1', 'sequence_accuracy', 'redundant_rate'.

    Returns:
        EvaluationResult with metrics and a composite .score property.

    Example:
        >>> from toolscore import evaluate
        >>> result = evaluate(
        ...     expected=[{"tool": "search", "args": {"q": "test"}}],
        ...     actual=[{"tool": "search", "args": {"q": "test"}}],
        ... )
        >>> result.score
        1.0
    """
    if not isinstance(expected, list):
        raise TypeError("expected must be a list of dicts, got " + type(expected).__name__)
    if not isinstance(actual, list):
        raise TypeError("actual must be a list of dicts, got " + type(actual).__name__)

    if weights is not None:
        valid_keys = set(EvaluationResult.DEFAULT_WEIGHTS.keys())
        unknown = set(weights.keys()) - valid_keys
        if unknown:
            raise ValueError(f"Unknown weight keys: {unknown}. Valid keys: {valid_keys}")
        for key, value in weights.items():
            if value < 0:
                raise ValueError(f"Weight for '{key}' must be non-negative, got {value}")

    gold_calls = _dicts_to_tool_calls(expected)
    trace_calls = _dicts_to_tool_calls(actual)

    result = EvaluationResult()
    result.gold_calls = gold_calls
    result.trace_calls = trace_calls

    if weights is not None:
        result._weights = {**result.DEFAULT_WEIGHTS, **weights}

    # Calculate core metrics
    result.metrics["invocation_accuracy"] = calculate_invocation_accuracy(
        gold_calls, trace_calls
    )
    result.metrics["selection_accuracy"] = calculate_selection_accuracy(gold_calls, trace_calls)

    tool_correctness_metrics = calculate_tool_correctness(gold_calls, trace_calls)
    result.metrics["tool_correctness_metrics"] = tool_correctness_metrics

    sequence_metrics = calculate_edit_distance(gold_calls, trace_calls)
    result.metrics["sequence_metrics"] = sequence_metrics

    trajectory_metrics = calculate_trajectory_accuracy(gold_calls, trace_calls)
    result.metrics["trajectory_metrics"] = trajectory_metrics

    argument_metrics = calculate_argument_f1(gold_calls, trace_calls)
    result.metrics["argument_metrics"] = argument_metrics

    efficiency_metrics = calculate_redundant_call_rate(gold_calls, trace_calls)
    result.metrics["efficiency_metrics"] = efficiency_metrics

    return result


class ToolScoreAssertionError(AssertionError):
    """Raised when assert_tools fails."""


def assert_tools(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    min_score: float = 0.9,
    weights: dict[str, float] | None = None,
) -> EvaluationResult:
    """Assert that actual tool calls meet a minimum composite score.

    Convenience function for use in pytest or any test framework.

    Args:
        expected: List of expected tool calls.
        actual: List of actual tool calls.
        min_score: Minimum composite score required (0.0 to 1.0).
        weights: Optional custom weights for the composite score.

    Returns:
        EvaluationResult if assertion passes.

    Raises:
        ToolScoreAssertionError: If the composite score is below min_score.
    """
    if not (0.0 <= min_score <= 1.0):
        raise ValueError(f"min_score must be between 0.0 and 1.0, got {min_score}")

    result = evaluate(expected, actual, weights=weights)
    if result.score < min_score:
        raise ToolScoreAssertionError(
            f"Tool call score {result.score:.3f} is below minimum {min_score:.3f}. "
            f"Selection: {result.selection_accuracy:.3f}, "
            f"Argument F1: {result.argument_f1:.3f}, "
            f"Sequence: {result.sequence_accuracy:.3f}"
        )
    return result
