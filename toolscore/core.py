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

    from toolscore.metrics.honesty import HonestyConfig
    from toolscore.metrics.llm_judge import JudgeConfig

from toolscore.adapters import (
    AnthropicAdapter,
    BrowserUseAdapter,
    ClaudeCodeSessionAdapter,
    CodexSessionAdapter,
    CustomAdapter,
    GeminiAdapter,
    LangChainAdapter,
    MCPAdapter,
    OpenAIAdapter,
)
from toolscore.adapters.base import BaseAdapter, ToolCall
from toolscore.adapters.otel import OTelAdapter, looks_like_otel
from toolscore.metrics import (
    calculate_argument_f1,
    calculate_cost_attribution,
    calculate_edit_distance,
    calculate_invocation_accuracy,
    calculate_latency,
    calculate_redundant_call_rate,
    calculate_required_call_recall,
    calculate_selection_accuracy,
    calculate_semantic_correctness,
    calculate_side_effect_success_rate,
    calculate_tool_correctness,
    calculate_trajectory_accuracy,
)
from toolscore.metrics.honesty import apply_injections, check_honesty
from toolscore.metrics.policy import check_forbidden_calls
from toolscore.metrics.security import find_secrets
from toolscore.validators import (
    FileSystemValidator,
    HTTPValidator,
    SQLValidator,
    calculate_schema_validation_metrics,
)
from toolscore.verdict import letter_grade


class EvaluationResult:
    """Container for evaluation results."""

    # Default weights for composite score
    DEFAULT_WEIGHTS: ClassVar[dict[str, float]] = {
        "selection_accuracy": 0.4,
        "argument_f1": 0.3,
        "sequence_accuracy": 0.2,
        "redundant_rate": 0.1,
        # Opt-in: 0 by default so existing scores do not change.
        "required_call_recall": 0.0,
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
        sequence_accuracy=0.2, redundant_rate=0.1, required_call_recall=0.0.

        Selection accuracy only judges the calls that were made, so by default a
        trace that skips required calls can still score well. Give
        ``required_call_recall`` a weight (for example
        ``weights={"required_call_recall": 0.3}``) to make missing and failed
        required calls lower the score.

        Returns:
            Composite score between 0.0 and 1.0.
        """
        sel = self.selection_accuracy
        arg = self.argument_f1
        seq = self.sequence_accuracy
        red = float(self.metrics.get("efficiency_metrics", {}).get("redundant_rate", 0.0))
        recall = self.required_call_recall
        completed = 1.0 if recall is None else recall

        w = self._weights
        # fsum adds the weighted terms without accumulating rounding error, so a
        # perfect run is exactly 1.0 (plain addition of 0.4 + 0.3 + 0.2 + 0.1
        # gives 0.9999999999999999). The clamp keeps float noise inside [0, 1].
        composite = math.fsum(
            (
                w["selection_accuracy"] * sel,
                w["argument_f1"] * arg,
                w["sequence_accuracy"] * seq,
                w["redundant_rate"] * (1.0 - red),
                w.get("required_call_recall", 0.0) * completed,
            )
        )
        return min(1.0, max(0.0, round(composite, 12)))

    @property
    def grade(self) -> str:
        """Letter grade (``"A"`` … ``"F"``) for :attr:`score`."""
        return letter_grade(self.score)

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

    @property
    def required_call_recall(self) -> float | None:
        """Share of required (expected) calls that were made and did not fail, counting repeats.

        ``None`` when nothing was required. See
        :func:`toolscore.metrics.calculate_required_call_recall`.
        """
        value = self.metrics.get("required_call_recall")
        return None if value is None else float(value)

    @property
    def false_success(self) -> dict[str, Any] | None:
        """The honesty summary counts (see :mod:`toolscore.metrics.honesty`), or ``None``."""
        honesty = self.metrics.get("honesty_metrics")
        if not isinstance(honesty, dict):
            return None
        counts = honesty.get("false_success")
        return counts if isinstance(counts, dict) else None

    @property
    def scored_calls(self) -> list[ToolCall]:
        """The calls the score compares with the expected ones.

        Every trace call, except those a contract's ``optional`` entries left
        out of the score (marked ``metadata["contract_optional"]``).
        """
        return [c for c in self.trace_calls if not c.metadata.get("contract_optional")]

    @property
    def evidence(self) -> dict[str, Any]:
        """Tri-state checks (pass / fail / unknown) and evidence coverage.

        A check that lacks the data it needs (no results captured, no final
        answer) is ``unknown``, never a pass. See :mod:`toolscore.evidence`.
        """
        from toolscore.evidence import evaluation_evidence

        return evaluation_evidence(self)

    @property
    def policy_violations(self) -> list[dict[str, Any]]:
        """Calls that matched a ``forbidden`` rule (empty when no rules were given)."""
        policy = self.metrics.get("policy_metrics") or {}
        violations: list[dict[str, Any]] = policy.get("violations", [])
        return violations

    #: Version of the :meth:`to_dict` record layout. Bumped on any change that
    #: could break a consumer; new keys alone do not bump it.
    RECORD_SCHEMA_VERSION: ClassVar[str] = "2"

    def to_dict(self) -> dict[str, Any]:
        """Return a complete, JSON-safe record of the evaluation.

        The record is meant to be stored or handed to other tools as-is:

        - ``schema_version``: layout version of this record (``"2"``).
        - ``score``, ``grade``, ``weights``: the composite score, its letter
          grade and the normalized weights that produced it.
        - ``required_call_recall``: see :attr:`required_call_recall`.
        - ``metrics``: every computed metric.
        - ``evidence``: the tri-state checks (``pass`` / ``fail`` /
          ``unknown``), their counts and the evidence coverage
          (:attr:`evidence`).
        - ``calls``: ``expected`` and ``actual`` calls with their arguments and,
          for actual calls, ``id``, ``result``, ``is_error``, ``error``,
          ``duration``, ``cost`` and ``timestamp`` (``null`` when the trace does
          not have them: unknown, never 0). Values that are not JSON (matcher
          objects, arbitrary result objects) are stored as their ``repr``.
        - ``gold_calls_count``, ``trace_calls_count``: kept for compatibility.

        Returns:
            Dictionary representation of the evaluation result.
        """
        record = _json_safe(
            {
                "schema_version": self.RECORD_SCHEMA_VERSION,
                "score": self.score,
                "grade": self.grade,
                "weights": dict(self._weights),
                "required_call_recall": self.required_call_recall,
                "metrics": self.metrics,
                "evidence": self.evidence,
                "calls": {
                    "expected": [{"tool": c.tool, "args": c.args} for c in self.gold_calls],
                    "actual": [_call_record(c) for c in self.trace_calls],
                },
                "gold_calls_count": len(self.gold_calls),
                "trace_calls_count": len(self.trace_calls),
            }
        )
        assert isinstance(record, dict)
        return record


def _json_safe(value: Any) -> Any:
    """Return ``value`` with every non-JSON leaf replaced by its ``repr``."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return repr(value)


def _call_record(call: ToolCall) -> dict[str, Any]:
    """The record of one actual call in :meth:`EvaluationResult.to_dict`."""
    error = call.metadata.get("error")
    return {
        "id": call.id,
        "tool": call.tool,
        "args": call.args,
        "result": call.result,
        "is_error": call.is_error,
        "error": None if isinstance(error, bool) else error,
        "duration": call.duration,
        "cost": call.cost,
        "timestamp": call.timestamp,
    }


def _add_trace_checks(
    result: EvaluationResult,
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    forbidden: list[dict[str, Any]] | None = None,
    final_answer: str | None = None,
    final_source: str | None = None,
    honesty: HonestyConfig | None = None,
) -> None:
    """Add the metrics shared by :func:`evaluate` and :func:`evaluate_trace`."""
    result.metrics["required_call_recall"] = calculate_required_call_recall(gold_calls, trace_calls)
    # Always present: a trace without timings or costs reports them as unknown
    # (status "unknown", totals None), never as 0.
    result.metrics["latency_metrics"] = calculate_latency(trace_calls)
    result.metrics["cost_metrics"] = calculate_cost_attribution(trace_calls)
    result.metrics["security_metrics"] = find_secrets(trace_calls)
    if forbidden is not None:
        result.metrics["policy_metrics"] = check_forbidden_calls(trace_calls, forbidden)
    result.metrics["honesty_metrics"] = check_honesty(
        trace_calls,
        final_answer,
        gold_calls=gold_calls,
        config=honesty,
        final_source=final_source,
    )


#: Every trace format name ``load_trace`` and the CLI ``--format`` options accept.
TRACE_FORMATS = (
    "auto", "openai", "anthropic", "gemini", "mcp", "langchain", "otel", "browser-use",
    "claude-code", "codex", "custom",
)  # fmt: skip


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
        format: Trace format (one of :data:`TRACE_FORMATS`; 'auto' detects it).

    Returns:
        List of tool calls from the trace.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If format is invalid or unsupported.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Trace file not found: {file_path}")

    data = read_trace_data(path)
    return adapter_for(data, format).parse(data)


def read_trace_data(path: str | Path) -> Any:
    """Read a trace file: one JSON document, or JSON Lines (one value per line).

    Coding-agent sessions (Claude Code transcripts, Codex CLI rollouts) and
    other logs are JSON Lines; they are returned as the list of their lines'
    values. Blank lines and lines that are not JSON (a partly written last
    line, for example) are skipped.

    Args:
        path: The trace file.

    Returns:
        The parsed data.

    Raises:
        ValueError: If the file is neither JSON nor JSON Lines.
    """
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        lines: list[Any] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if not lines:
            raise ValueError(f"{path} is neither JSON nor JSON Lines: {exc}") from exc
        return lines


def adapter_for(data: Any, format: str = "auto") -> BaseAdapter:
    """The adapter that reads ``data`` in ``format`` (``"auto"`` detects it).

    Args:
        data: The parsed trace.
        format: One of :data:`TRACE_FORMATS` ('auto' detects it).

    Returns:
        The adapter.

    Raises:
        ValueError: If the format is not supported.
    """
    adapters: dict[str, type[BaseAdapter]] = {
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter,
        "gemini": GeminiAdapter,
        "mcp": MCPAdapter,
        "langchain": LangChainAdapter,
        "custom": CustomAdapter,
        "otel": OTelAdapter,
        "browser-use": BrowserUseAdapter,
        "claude-code": ClaudeCodeSessionAdapter,
        "codex": CodexSessionAdapter,
    }
    if format == "auto":
        return _detect_format(data)
    if format not in adapters:
        raise ValueError(f"Unsupported format: {format}")
    return adapters[format]()


def _is_jsonrpc_list(value: Any) -> bool:
    """Whether ``value`` is a non-empty list whose first item is a JSON-RPC message."""
    return (
        isinstance(value, list)
        and bool(value)
        and isinstance(value[0], dict)
        and value[0].get("jsonrpc") == "2.0"
    )


def _detect_format(data: Any) -> BaseAdapter:
    """Auto-detect trace format.

    Args:
        data: Trace data to analyze.

    Returns:
        Appropriate adapter for the detected format.
    """
    # Check for MCP format (JSON-RPC 2.0): a single message, a recorded session
    # ({"format": "mcp", "messages": [...]}, as written by `toolscore mcp record`),
    # or a log of JSON-RPC messages. OpenAI "messages" carry "role", never "jsonrpc".
    if isinstance(data, dict) and "jsonrpc" in data:
        return MCPAdapter()
    if isinstance(data, dict) and (
        data.get("format") == "mcp" or _is_jsonrpc_list(data.get("messages"))
    ):
        return MCPAdapter()
    if _is_jsonrpc_list(data):
        return MCPAdapter()

    # Coding-agent sessions (JSON Lines): Claude Code transcripts, Codex CLI rollouts
    from toolscore.adapters.sessions import looks_like_claude_code, looks_like_codex

    if looks_like_codex(data):
        return CodexSessionAdapter()
    if looks_like_claude_code(data):
        return ClaudeCodeSessionAdapter()

    # browser-use AgentHistoryList dumps ({"history": [steps]} or the step list)
    from toolscore.adapters.browser_use import looks_like_browser_use

    if looks_like_browser_use(data):
        return BrowserUseAdapter()

    # OpenTelemetry GenAI tool spans (OTLP JSON export or a span list)
    if looks_like_otel(data):
        return OTelAdapter()

    # Check for Gemini format (candidates with function calls)
    if isinstance(data, dict) and "candidates" in data:
        return GeminiAdapter()

    # Check for OpenAI format (Chat Completions, then the Responses API)
    if isinstance(data, dict) and ("messages" in data or "choices" in data):
        return OpenAIAdapter()
    from toolscore.integrations import _is_responses_payload

    if _is_responses_payload(data):
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

        # A full chat history usually starts with a user or system message.
        messages = [m for m in data if isinstance(m, dict)]
        if any(
            m.get("role") == "assistant"
            and isinstance(m.get("content"), list)
            and any(isinstance(b, dict) and b.get("type") == "tool_use" for b in m["content"])
            for m in messages
        ):
            return AnthropicAdapter()
        if any(
            m.get("role") == "assistant" and ("tool_calls" in m or "function_call" in m)
            for m in messages
        ):
            return OpenAIAdapter()

    # Default to custom format
    return CustomAdapter()


def _normalize_weights(weights: dict[str, float] | None) -> dict[str, float] | None:
    """Validate custom weights, merge them with the defaults and renormalize to sum 1.

    Args:
        weights: Custom weights, or ``None`` for the defaults.

    Returns:
        The merged, normalized weights, or ``None`` when ``weights`` is ``None``.

    Raises:
        ValueError: On an unknown key, a negative or non-finite value, or weights
            that sum to zero.
    """
    if weights is None:
        return None
    valid_keys = set(EvaluationResult.DEFAULT_WEIGHTS.keys())
    unknown = set(weights.keys()) - valid_keys
    if unknown:
        raise ValueError(f"Unknown weight keys: {unknown}. Valid keys: {valid_keys}")
    for key, value in weights.items():
        if not math.isfinite(value):
            raise ValueError(f"Weight for '{key}' must be a finite number, got {value}")
        if value < 0:
            raise ValueError(f"Weight for '{key}' must be non-negative, got {value}")
    merged = {**EvaluationResult.DEFAULT_WEIGHTS, **weights}
    total = sum(merged.values())
    if total == 0.0:
        raise ValueError(
            "Weights sum to zero after merging with defaults; at least one weight must be positive."
        )
    return {k: v / total for k, v in merged.items()}


def evaluate_trace(
    gold_file: str | Path,
    trace_file: str | Path,
    format: str = "auto",
    validate_side_effects: bool = True,
    judge: JudgeConfig | str | bool = False,
    forbidden: list[dict[str, Any]] | None = None,
    weights: dict[str, float] | None = None,
    final_answer: str | None = None,
    honesty: HonestyConfig | None = None,
    injections: list[dict[str, Any]] | None = None,
) -> EvaluationResult:
    """Evaluate an agent's trace against gold standard.

    Args:
        gold_file: Path to gold standard specification, or a contract file
            (required / optional / forbidden calls and alternatives, see
            :mod:`toolscore.contract`).
        trace_file: Path to agent trace.
        format: Trace format (one of :data:`TRACE_FORMATS`; 'auto' detects it).
        validate_side_effects: Whether to validate side effects.
        judge: LLM-as-a-judge configuration for semantic evaluation. ``False``
            (default) disables it. ``True`` uses a default ``JudgeConfig()``.
            A string is treated as a model-name shorthand. A ``JudgeConfig`` is
            used as given. Provider is inferred from the model name (or set
            explicitly via ``JudgeConfig``): ``claude-*`` -> Anthropic,
            ``gemini-*`` -> Gemini, a ``base_url`` -> any OpenAI-compatible
            endpoint (Ollama/vLLM/Groq), otherwise OpenAI.
        forbidden: Optional calls the agent must never make (see
            :func:`evaluate`); violations go to ``metrics["policy_metrics"]``.
        weights: Optional custom weights for the composite score (see
            :func:`evaluate`).
        final_answer: The agent's final answer, when the trace does not hold
            it; the honesty checks use it (``metrics["honesty_metrics"]``).
        honesty: Patterns and tool lists for the honesty checks.
        injections: Faults injected by ``toolscore mcp proxy --inject``, from a
            separate proxy session file; matched to the trace's calls by tool
            name and order. A proxy session trace carries its own.

    Returns:
        EvaluationResult containing all computed metrics.

    Raises:
        FileNotFoundError: If files don't exist.
        ValueError: If file formats are invalid.
    """
    from toolscore.contract import contract_file_data, evaluate_contract, is_contract
    from toolscore.transcript import load_transcript

    gold_data = contract_file_data(gold_file) if Path(gold_file).exists() else None
    if is_contract(gold_data):
        transcript = load_transcript(trace_file, format=format, final_answer=final_answer)
        if injections:
            apply_injections(transcript.calls, injections)
        contract = dict(gold_data)
        if forbidden is not None:
            contract["forbidden"] = list(contract.get("forbidden") or []) + list(forbidden)
        return evaluate_contract(
            contract,
            [_tool_call_dict(c) for c in transcript.calls],
            weights=weights,
            final_answer=transcript.final_answer,
            honesty=honesty,
        )

    merged_weights = _normalize_weights(weights)

    # Load data
    gold_calls = load_gold_standard(gold_file)
    transcript = load_transcript(trace_file, format=format, final_answer=final_answer)
    trace_calls = transcript.calls
    if injections:
        apply_injections(trace_calls, injections)

    # Create result
    result = EvaluationResult()
    result.gold_calls = gold_calls
    result.trace_calls = trace_calls
    if merged_weights is not None:
        result._weights = merged_weights

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
    _add_trace_checks(
        result,
        gold_calls,
        trace_calls,
        forbidden,
        final_answer=transcript.final_answer,
        final_source=transcript.final_source,
        honesty=honesty,
    )

    # Schema validation (if schemas are provided in metadata)
    schema_metrics = calculate_schema_validation_metrics(gold_calls, trace_calls)
    if schema_metrics["total_validated"] > 0:
        result.metrics["schema_metrics"] = schema_metrics

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


def _tool_call_dict(call: ToolCall) -> dict[str, Any]:
    """A :class:`ToolCall` as a trace dict that :func:`_dicts_to_tool_calls` reads back unchanged."""
    return {
        "tool": call.tool,
        "args": call.args,
        "result": call.result,
        "timestamp": call.timestamp,
        "duration": call.duration,
        "cost": call.cost,
        "metadata": dict(call.metadata),
    }


def _call_metadata(item: dict[str, Any]) -> dict[str, Any]:
    """Build a call's metadata from a trace dict: its ``metadata``, ``id`` and failure fields."""
    metadata: dict[str, Any] = (
        dict(item["metadata"]) if isinstance(item.get("metadata"), dict) else {}
    )
    if item.get("id") is not None:
        metadata["id"] = item["id"]
    if "error" in item:
        error = item["error"]
        if isinstance(error, bool):
            metadata["is_error"] = error
        elif error:  # "", {}, [] and None mean "no error", as many frameworks emit them
            metadata["error"] = str(error)
            metadata["is_error"] = True
    if isinstance(item.get("is_error"), bool):
        metadata["is_error"] = item["is_error"]
    return metadata


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

    Optional fields describe what happened and are kept on the call:
    ``result``, ``timestamp``, ``duration``, ``cost``, ``id``, a ``metadata``
    dict, and failure information (``error`` as a message or ``True``, and/or
    ``is_error``). They feed the error metrics and reports; they never change
    how calls are matched or scored.

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
                result=item.get("result"),
                timestamp=item.get("timestamp"),
                duration=item.get("duration"),
                cost=item.get("cost"),
                metadata=_call_metadata(item),
            )
        )
    return calls


def evaluate(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]] | Any,
    weights: dict[str, float] | None = None,
    strict: bool = False,
    forbidden: list[dict[str, Any]] | None = None,
    final_answer: str | None = None,
    honesty: HonestyConfig | None = None,
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
            Keys: 'selection_accuracy', 'argument_f1', 'sequence_accuracy', 'redundant_rate',
            'required_call_recall' (0 by default; give it a weight to penalize
            required calls that were skipped or failed).
            Provided values are merged with the defaults then renormalized so that all
            weights sum to 1.0 before computing the composite score.
        strict: When True, argument comparison uses pure equality (no int/float
            coercion, no string strip).  Default is False (lenient matching).
        forbidden: Optional calls the agent must never make, as rule dicts with
            ``tool``, optional ``args`` (values or matchers) and optional
            ``reason``. Violations are reported in ``metrics["policy_metrics"]``
            and :attr:`EvaluationResult.policy_violations`; they do not change the
            score. See :mod:`toolscore.metrics.policy`.
        final_answer: What the agent told the user at the end. When omitted it
            is read from a raw ``actual`` that holds one (a chat history ending
            in an assistant message, a Responses output, an agent result).
            The honesty checks (``metrics["honesty_metrics"]``) use it; they do
            not change the score.
        honesty: Patterns and tool lists for the honesty checks
            (:class:`toolscore.metrics.honesty.HonestyConfig`).

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
    from toolscore.transcript import final_answer_of

    final_source: str | None = "provided" if final_answer else None
    if not final_answer and isinstance(actual, (dict, list)):
        final_answer, final_source = final_answer_of(actual)
    actual = auto_extract(actual)

    merged_weights = _normalize_weights(weights)

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
    if final_answer is None and trace_calls:
        from toolscore.transcript import final_answer_of as _final

        final_answer, final_source = _final(None, trace_calls)
    _add_trace_checks(
        result,
        gold_calls,
        trace_calls,
        forbidden,
        final_answer=final_answer,
        final_source=final_source,
        honesty=honesty,
    )

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
