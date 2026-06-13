"""Core evaluation logic for Toolscore."""

from __future__ import annotations

import inspect
import json
import math
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from toolscore.metrics.llm_judge import JudgeConfig

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

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    # Accept a snapshot file (top-level dict with a "calls" list) in addition to
    # a bare JSON array of tool calls.
    if isinstance(data, dict) and isinstance(data.get("calls"), list):
        data = data["calls"]

    if not isinstance(data, list):
        raise ValueError("Gold standard must be a JSON array of tool calls")

    gold_calls = []
    for item in data:
        if not isinstance(item, dict):
            continue

        tool_name = item.get("tool")
        if not tool_name:
            continue

        # Preserve None (args key absent or explicit null) so that a gold file
        # which omits "args" expresses "do not check arguments" rather than
        # "expect zero arguments".  An explicit "args": {} still means
        # "expect the tool to be called with no arguments".
        args = item.get("args")
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

    with path.open(encoding="utf-8") as f:
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
                if (
                    isinstance(parts, list)
                    and parts
                    and any("functionCall" in p for p in parts if isinstance(p, dict))
                ):
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
    judge: JudgeConfig | str | bool = False,
) -> EvaluationResult:
    """Evaluate an agent's trace against gold standard.

    Args:
        gold_file: Path to gold standard specification.
        trace_file: Path to agent trace.
        format: Trace format ('auto', 'openai', 'anthropic', 'gemini', 'mcp', 'langchain', 'custom').
        validate_side_effects: Whether to validate side effects.
        judge: LLM-as-a-judge configuration for semantic evaluation. ``False``
            (default) disables it. ``True`` uses a default ``JudgeConfig()``.
            A string is treated as a model-name shorthand. A ``JudgeConfig`` is
            used as given. Provider is inferred from the model name (or set
            explicitly via ``JudgeConfig``): ``claude-*`` -> Anthropic,
            ``gemini-*`` -> Gemini, a ``base_url`` -> any OpenAI-compatible
            endpoint (Ollama/vLLM/Groq), otherwise OpenAI.

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
    result.metrics["invocation_accuracy"] = calculate_invocation_accuracy(gold_calls, trace_calls)
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
    if judge is not False:
        judge_config: JudgeConfig | str | None
        judge_config = None if judge is True else judge
        try:
            semantic_metrics = calculate_semantic_correctness(
                gold_calls,
                trace_calls,
                judge=judge_config,
            )
            result.metrics["semantic_metrics"] = semantic_metrics
        except ImportError as e:
            # Provider SDK not installed: warn but continue gracefully.
            warnings.warn(str(e), UserWarning, stacklevel=2)
        except ValueError as e:
            # If API key missing, add warning to metrics
            result.metrics["semantic_metrics"] = {
                "error": str(e),
                "semantic_score": None,
            }

    return result


def _dicts_to_tool_calls(items: list[dict[str, Any]]) -> list[ToolCall]:
    """Convert a list of dicts to ToolCall objects.

    Each dict should have at least a ``'tool'`` key and optionally ``'args'``.

    Argument handling follows the gold-side contract:

    * ``'args'`` **present and a dict** (including ``{}``) → kept as-is.  An
      explicit ``{}`` means "expect this tool to be called with no arguments".
    * ``'args'`` **omitted** or set to ``None`` → ``ToolCall.args`` is left as
      ``None``, which downstream metrics interpret as "do not check arguments"
      for that call (a tool-name-only expectation).

    For actual/trace dicts the same mapping applies, but a ``None`` there is
    harmless: trace-side metrics treat missing args as an empty mapping.

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
        # Preserve None (omitted / explicit null) instead of substituting {} so
        # that "args omitted" stays distinct from "expect zero args" ({}).
        calls.append(
            ToolCall(
                tool=tool_name,
                args=item.get("args"),
            )
        )
    return calls


def evaluate(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]] | Any,
    weights: dict[str, float] | None = None,
    strict: bool = False,
) -> EvaluationResult:
    """Evaluate tool calls by comparing actual against expected (in-memory).

    This is the simplest way to use Toolscore - pass Python dicts directly,
    no file I/O required. Raw OpenAI, Anthropic, Gemini, LangGraph, Pydantic AI,
    OpenAI Agents SDK, and Claude Agent SDK responses are auto-detected and
    converted automatically, including list-shaped formats (Claude Agent SDK
    message lists and bare LangGraph message lists).

    Args:
        expected: List of expected tool calls, each a dict with 'tool' and optional 'args'.
        actual: List of actual tool calls from your agent, same format. Also accepts
            raw OpenAI/Anthropic/Gemini response objects or dicts (auto-detected).
        weights: Optional custom weights for the composite score.
            Keys: 'selection_accuracy', 'argument_f1', 'sequence_accuracy', 'redundant_rate'.
            Provided values are merged with the defaults then renormalized so that all
            weights sum to 1.0 before computing the composite score.
        strict: When True, argument comparison uses pure equality (no int/float
            coercion, no string strip).  Default is False (lenient matching).

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
    # Always route through auto_extract: already-normalized [{"tool": ...}] lists
    # pass through unchanged, while list-shaped raw formats (Claude Agent SDK
    # message lists, bare LangGraph message lists) are detected and converted.
    from toolscore.integrations import auto_extract

    actual = auto_extract(actual)

    merged_weights: dict[str, float] | None = None
    if weights is not None:
        valid_keys = set(EvaluationResult.DEFAULT_WEIGHTS.keys())
        unknown = set(weights.keys()) - valid_keys
        if unknown:
            raise ValueError(f"Unknown weight keys: {unknown}. Valid keys: {valid_keys}")
        for key, value in weights.items():
            if not math.isfinite(value):
                raise ValueError(f"Weight for '{key}' must be a finite number, got {value}")
            if value < 0:
                raise ValueError(f"Weight for '{key}' must be non-negative, got {value}")
        merged_weights = {**EvaluationResult.DEFAULT_WEIGHTS, **weights}
        total = sum(merged_weights.values())
        if total == 0.0:
            raise ValueError(
                "Weights sum to zero after merging with defaults; "
                "at least one weight must be positive."
            )
        merged_weights = {k: v / total for k, v in merged_weights.items()}

    gold_calls = _dicts_to_tool_calls(expected)
    trace_calls = _dicts_to_tool_calls(actual)

    result = EvaluationResult()
    result.gold_calls = gold_calls
    result.trace_calls = trace_calls

    if merged_weights is not None:
        result._weights = merged_weights

    # Calculate core metrics
    result.metrics["invocation_accuracy"] = calculate_invocation_accuracy(gold_calls, trace_calls)
    result.metrics["selection_accuracy"] = calculate_selection_accuracy(gold_calls, trace_calls)

    tool_correctness_metrics = calculate_tool_correctness(gold_calls, trace_calls)
    result.metrics["tool_correctness_metrics"] = tool_correctness_metrics

    sequence_metrics = calculate_edit_distance(gold_calls, trace_calls)
    result.metrics["sequence_metrics"] = sequence_metrics

    trajectory_metrics = calculate_trajectory_accuracy(gold_calls, trace_calls)
    result.metrics["trajectory_metrics"] = trajectory_metrics

    argument_metrics = calculate_argument_f1(gold_calls, trace_calls, strict=strict)
    result.metrics["argument_metrics"] = argument_metrics

    efficiency_metrics = calculate_redundant_call_rate(gold_calls, trace_calls)
    result.metrics["efficiency_metrics"] = efficiency_metrics

    return result


class ToolScoreAssertionError(AssertionError):
    """Raised when assert_tools fails."""


def assert_tools(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]] | Any,
    min_score: float = 0.9,
    weights: dict[str, float] | None = None,
    strict: bool = False,
) -> EvaluationResult:
    """Assert that actual tool calls meet a minimum composite score.

    Convenience function for use in pytest or any test framework.

    Args:
        expected: List of expected tool calls.
        actual: List of actual tool calls.
        min_score: Minimum composite score required (0.0 to 1.0).
        weights: Optional custom weights for the composite score.
        strict: When True, argument comparison uses pure equality (no int/float
            coercion, no string strip).  Default is False.

    Returns:
        EvaluationResult if assertion passes.

    Raises:
        ValueError: If min_score is outside [0.0, 1.0].
        ToolScoreAssertionError: If the composite score is below min_score.
    """
    if not (0.0 <= min_score <= 1.0):
        raise ValueError(f"min_score must be between 0.0 and 1.0, got {min_score}")

    result = evaluate(expected, actual, weights=weights, strict=strict)
    _check_min_score(result, min_score)
    return result


def _check_min_score(result: EvaluationResult, min_score: float | None) -> None:
    """Raise ToolScoreAssertionError if result.score is below min_score.

    When *min_score* is not None and ``result.score < min_score``, renders a
    rich expected-vs-actual diff via :func:`toolscore.diff.render_failure`.
    If ``sys.stderr`` is a TTY the colored rendering is also printed to stderr
    before raising, so interactive sessions get color output while the
    exception message (embedded in pytest output) stays plain text.

    Args:
        result: The EvaluationResult to check.
        min_score: Minimum composite score required (0.0 to 1.0), or None to skip.

    Raises:
        ValueError: If min_score is outside [0.0, 1.0].
        ToolScoreAssertionError: If result.score < min_score.
    """
    if min_score is None:
        return
    if not (0.0 <= min_score <= 1.0):
        raise ValueError(f"min_score must be between 0.0 and 1.0, got {min_score}")
    # The composite score sums float-weighted metrics, so an exact match lands at
    # ~0.9999999999999999 rather than a clean 1.0.  Nudge the threshold down by a
    # tiny epsilon here (the shared chokepoint for every threshold check) so float
    # noise does not spuriously fail a genuine perfect match; real drift drops the
    # score far below this tolerance and is still caught.
    if result.score < max(0.0, min_score - 1e-9):
        from toolscore.diff import render_failure

        plain_msg = render_failure(result, min_score, color=False)
        # Print colored version to stderr when running in a terminal
        try:
            if sys.stderr.isatty():
                colored_msg = render_failure(result, min_score, color=True)
                sys.stderr.write(colored_msg)
        except Exception:
            pass
        raise ToolScoreAssertionError(plain_msg)


def test_agent(
    agent: Callable[..., Any],
    input: str,
    expected: list[dict[str, Any]],
    min_score: float | None = None,
    weights: dict[str, float] | None = None,
    strict: bool = False,
) -> EvaluationResult:
    """End-to-end test helper: run an agent, extract tool calls, evaluate.

    Calls ``agent(input)``, passes the response through auto-detection to
    extract tool calls, and evaluates against *expected*.

    Args:
        agent: Any callable that accepts a string and returns an LLM response
            (raw provider response or list of tool-call dicts).  Must be a
            synchronous callable; use :func:`test_agent_async` for async agents.
        input: The prompt / user message to send to the agent.
        expected: List of expected tool calls.
        min_score: If provided, raises ``ToolScoreAssertionError`` when the
            composite score is below this threshold.
        weights: Optional custom weights for the composite score.
        strict: When True, argument comparison uses pure equality.

    Returns:
        EvaluationResult with metrics and a composite ``.score`` property.

    Raises:
        TypeError: If *agent* is an async function or returns an awaitable.
        ValueError: If *min_score* is outside [0.0, 1.0].
        ToolScoreAssertionError: If *min_score* is set and the score is below it.
    """
    if min_score is not None and not (0.0 <= min_score <= 1.0):
        raise ValueError(f"min_score must be between 0.0 and 1.0, got {min_score}")
    if inspect.iscoroutinefunction(agent):
        raise TypeError("agent is async — use `await toolscore.test_agent_async(...)` instead.")
    response = agent(input)
    if inspect.iscoroutine(response):
        # Close the coroutine to avoid an "un-awaited coroutine" warning.
        response.close()
        raise TypeError("agent is async — use `await toolscore.test_agent_async(...)` instead.")
    if inspect.isawaitable(response):
        raise TypeError("agent is async — use `await toolscore.test_agent_async(...)` instead.")
    result = evaluate(expected, response, weights=weights, strict=strict)
    _check_min_score(result, min_score)
    return result


test_agent.__test__ = False  # type: ignore[attr-defined]


async def test_agent_async(
    agent: Callable[..., Any],
    input: str,
    expected: list[dict[str, Any]],
    min_score: float | None = None,
    weights: dict[str, float] | None = None,
    strict: bool = False,
) -> EvaluationResult:
    """Async end-to-end test helper: run an agent, extract tool calls, evaluate.

    Works for both synchronous and asynchronous agents.  Calls ``agent(input)``
    and, if the result is awaitable, awaits it.

    Args:
        agent: Any callable that accepts a string and returns an LLM response
            (raw provider response or list of tool-call dicts).  May be sync
            or async.
        input: The prompt / user message to send to the agent.
        expected: List of expected tool calls.
        min_score: If provided, raises ``ToolScoreAssertionError`` when the
            composite score is below this threshold.
        weights: Optional custom weights for the composite score.
        strict: When True, argument comparison uses pure equality.

    Returns:
        EvaluationResult with metrics and a composite ``.score`` property.

    Raises:
        ValueError: If *min_score* is outside [0.0, 1.0].
        ToolScoreAssertionError: If *min_score* is set and the score is below it.
    """
    if min_score is not None and not (0.0 <= min_score <= 1.0):
        raise ValueError(f"min_score must be between 0.0 and 1.0, got {min_score}")
    response = agent(input)
    if inspect.isawaitable(response):
        response = await response
    result = evaluate(expected, response, weights=weights, strict=strict)
    _check_min_score(result, min_score)
    return result


test_agent_async.__test__ = False  # type: ignore[attr-defined]
