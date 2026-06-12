"""LLM-as-a-judge metrics for semantic evaluation.

This module uses large language models to evaluate the semantic correctness
of tool calls beyond simple syntactic matching. It supports OpenAI, Anthropic,
Google Gemini, and any OpenAI-compatible endpoint (Ollama, vLLM, Groq, ...).

The provider is inferred from the model name unless given explicitly:

- ``claude-*``  -> ``anthropic``
- ``gemini-*``  -> ``gemini``
- anything else -> ``openai``
- a ``base_url`` set on the config -> ``openai_compatible`` (covers Ollama/vLLM/Groq)

SDK imports are performed lazily inside each backend, so the module imports
cleanly even when no provider SDK is installed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from toolscore.adapters.base import ToolCall

Provider = Literal["openai", "anthropic", "gemini", "openai_compatible"]

# Per-provider environment variables used when no api_key is supplied.
_ENV_KEYS: dict[Provider, str] = {
    "openai": "OPENAI_API_KEY",
    "openai_compatible": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}

# Per-provider pip install hint shown when the SDK is missing.
_INSTALL_HINT: dict[Provider, str] = {
    "openai": "pip install tool-scorer[llm]",
    "openai_compatible": "pip install tool-scorer[llm]",
    "anthropic": "pip install tool-scorer[anthropic]",
    "gemini": "pip install tool-scorer[gemini]",
}

_SYSTEM_PROMPT = (
    "You are an expert evaluator of LLM tool usage. "
    "Evaluate whether tool calls are semantically equivalent."
)


class _BatchParseError(Exception):
    """Raised internally when a batched judge response cannot be parsed.

    This is the *only* failure that triggers the per-pair fallback. Transport,
    authentication, and other SDK errors from ``backend.complete()`` propagate
    instead of silently fanning out into N doomed per-pair requests.
    """


@dataclass
class JudgeConfig:
    """Configuration for the LLM judge.

    Args:
        model: Model name (e.g. ``gpt-4o-mini``, ``claude-3-5-haiku``,
            ``gemini-2.0-flash``, ``llama3.1``).
        provider: Provider to use. ``None`` infers it from ``model`` /
            ``base_url`` (see module docstring).
        api_key: API key. ``None`` falls back to the per-provider env var
            (``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` / ``GOOGLE_API_KEY``).
        base_url: Custom endpoint. When set, the provider becomes
            ``openai_compatible`` (covers Ollama/vLLM/Groq/etc.).
        temperature: Sampling temperature (default ``0.0`` for determinism).
        max_retries: Max retries passed to the underlying SDK client.
    """

    model: str = "gpt-4o-mini"
    provider: Provider | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.0
    max_retries: int = 2


def infer_provider(config: JudgeConfig) -> Provider:
    """Resolve the effective provider for a config.

    Resolution rules:

    - An explicit ``provider`` wins. It is validated against ``base_url``:
      ``openai_compatible`` requires a ``base_url``; any other explicit provider
      must *not* be combined with a ``base_url`` (the combination is ambiguous).
    - With no explicit provider, a ``base_url`` forces ``openai_compatible``.
    - Otherwise the provider is inferred from the model name.

    Args:
        config: Judge configuration.

    Returns:
        The resolved provider.

    Raises:
        ValueError: If an explicit ``provider`` conflicts with ``base_url``.
    """
    if config.provider is not None:
        if config.provider == "openai_compatible":
            if config.base_url is None:
                raise ValueError(
                    "provider='openai_compatible' requires a base_url "
                    "(e.g. JudgeConfig(provider='openai_compatible', "
                    "base_url='http://localhost:11434/v1')). "
                    "Omit the provider to infer it from the model name instead."
                )
            return "openai_compatible"
        if config.base_url is not None:
            raise ValueError(
                f"provider='{config.provider}' conflicts with base_url="
                f"{config.base_url!r}. A base_url implies an OpenAI-compatible "
                "endpoint; either drop base_url, or use "
                "provider='openai_compatible' (or omit provider entirely)."
            )
        return config.provider

    if config.base_url is not None:
        return "openai_compatible"

    model = config.model.lower()
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gemini"):
        return "gemini"
    return "openai"


def _resolve_api_key(config: JudgeConfig, provider: Provider) -> str | None:
    """Resolve the API key, falling back to the per-provider env var(s).

    For Gemini, ``GOOGLE_API_KEY`` is checked first, then ``GEMINI_API_KEY``
    (the newer google-genai SDK accepts either).
    """
    if config.api_key is not None:
        return config.api_key
    key = os.getenv(_ENV_KEYS[provider])
    if key is None and provider == "gemini":
        key = os.getenv("GEMINI_API_KEY")
    return key


class _JudgeBackend(Protocol):
    """Minimal backend interface: turn (system, prompt) into raw text."""

    def complete(self, system: str, prompt: str) -> str:
        """Run one completion and return the raw text response."""
        ...


class _OpenAIBackend:
    """Backend for OpenAI and OpenAI-compatible endpoints (Ollama/vLLM/Groq)."""

    def __init__(self, config: JudgeConfig, provider: Provider) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "openai package required for this LLM judge. "
                f"Install with: {_INSTALL_HINT[provider]}"
            ) from e

        api_key = _resolve_api_key(config, provider)
        # OpenAI-compatible servers (Ollama/vLLM) often need no real key;
        # the SDK still requires a non-empty value, so default to a placeholder.
        if not api_key and config.base_url is not None:
            api_key = "not-needed"
        self._client = OpenAI(
            api_key=api_key,
            base_url=config.base_url,
            max_retries=config.max_retries,
        )
        self._model = config.model
        self._temperature = config.temperature

    def complete(self, system: str, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=self._temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        return content or ""


class _AnthropicBackend:
    """Backend for Anthropic Claude models (Messages API)."""

    def __init__(self, config: JudgeConfig) -> None:
        try:
            import anthropic
        except ImportError as e:
            raise ImportError(
                "anthropic package required for Claude LLM judge. "
                f"Install with: {_INSTALL_HINT['anthropic']}"
            ) from e

        self._client = anthropic.Anthropic(
            api_key=_resolve_api_key(config, "anthropic"),
            max_retries=config.max_retries,
        )
        self._model = config.model
        self._temperature = config.temperature

    def complete(self, system: str, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            temperature=self._temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        parts: list[str] = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "".join(parts)


class _GeminiBackend:
    """Backend for Google Gemini models (google-genai SDK)."""

    def __init__(self, config: JudgeConfig) -> None:
        try:
            from google import genai
        except ImportError as e:
            raise ImportError(
                "google-genai package required for Gemini LLM judge. "
                f"Install with: {_INSTALL_HINT['gemini']}"
            ) from e

        self._client = genai.Client(api_key=_resolve_api_key(config, "gemini"))
        self._model = config.model
        self._temperature = config.temperature
        # The google-genai SDK has no built-in retry knob like openai/anthropic,
        # so honor config.max_retries with a small retry loop.
        self._max_retries = max(0, config.max_retries)

    def complete(self, system: str, prompt: str) -> str:
        last_exc: Exception | None = None
        for _attempt in range(self._max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config={
                        "system_instruction": system,
                        "temperature": self._temperature,
                        "response_mime_type": "application/json",
                    },
                )
                return response.text or ""
            except Exception as e:
                # Retried below; re-raised after exhausting attempts.
                last_exc = e
        assert last_exc is not None
        raise last_exc


def _make_backend(config: JudgeConfig) -> _JudgeBackend:
    """Construct the backend for a config based on its resolved provider."""
    provider = infer_provider(config)
    if provider in ("openai", "openai_compatible"):
        return _OpenAIBackend(config, provider)
    if provider == "anthropic":
        return _AnthropicBackend(config)
    return _GeminiBackend(config)


def _coerce_config(judge: JudgeConfig | str | None) -> JudgeConfig:
    """Normalize the ``judge`` argument into a :class:`JudgeConfig`."""
    if judge is None:
        return JudgeConfig()
    if isinstance(judge, str):
        return JudgeConfig(model=judge)
    return judge


def _strip_code_fences(text: str) -> str:
    """Strip Markdown code fences (```json ... ```) from a model response."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    # Drop the opening fence (possibly ```json) and the trailing fence.
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _clamp_score(value: Any) -> float:
    """Coerce an arbitrary value to a float score clamped to [0.0, 1.0]."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def calculate_semantic_correctness(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    *,
    judge: JudgeConfig | str | None = None,
) -> dict[str, Any]:
    """Calculate semantic correctness using LLM-as-a-judge.

    Uses an LLM to evaluate whether the trace calls are semantically
    equivalent to the gold standard calls, even if they differ syntactically.

    By default this issues a single batched request containing every
    gold/trace pair and asks for a JSON array of per-pair scores. If the
    batched response cannot be parsed, it falls back to one request per pair.

    Args:
        gold_calls: Expected tool calls.
        trace_calls: Actual tool calls from the agent.
        judge: Judge configuration. May be a :class:`JudgeConfig`, a model-name
            string shorthand, or ``None`` (default ``JudgeConfig()``).

    Returns:
        Dictionary containing:

        - ``semantic_score``: Overall semantic correctness (0.0 to 1.0).
        - ``per_call_scores``: List of scores for each call pair.
        - ``explanations``: List of explanations for each evaluation.
        - ``model_used``: The model that was used.
        - ``gold_count``: Number of gold calls.
        - ``trace_count``: Number of trace calls.

    Raises:
        ImportError: If the required provider SDK is not installed.
        ValueError: If no API key is available for the resolved provider.

    Example:
        >>> gold = [ToolCall(tool="search", args={"query": "Python"})]
        >>> trace = [ToolCall(tool="web_search", args={"q": "Python"})]
        >>> result = calculate_semantic_correctness(gold, trace)
        >>> result["semantic_score"]
        0.95  # High score despite different naming
    """
    config = _coerce_config(judge)
    provider = infer_provider(config)

    if _resolve_api_key(config, provider) is None and provider != "openai_compatible":
        raise ValueError(
            f"API key required for provider '{provider}'. Set the "
            f"{_ENV_KEYS[provider]} environment variable or pass JudgeConfig(api_key=...)."
        )

    backend = _make_backend(config)

    min_len = min(len(gold_calls), len(trace_calls))

    if min_len == 0:
        per_call_scores: list[float] = []
        explanations: list[str] = []
    else:
        per_call_scores, explanations = _judge_pairs(backend, gold_calls, trace_calls, min_len)

    semantic_score = sum(per_call_scores) / len(per_call_scores) if per_call_scores else 0.0

    # Penalize length mismatch (preserved from the original behavior).
    if len(gold_calls) != len(trace_calls):
        length_penalty = 1.0 - (
            abs(len(gold_calls) - len(trace_calls)) / max(len(gold_calls), len(trace_calls), 1)
        )
        semantic_score *= length_penalty

    return {
        "semantic_score": semantic_score,
        "per_call_scores": per_call_scores,
        "explanations": explanations,
        "model_used": config.model,
        "gold_count": len(gold_calls),
        "trace_count": len(trace_calls),
    }


def _judge_pairs(
    backend: _JudgeBackend,
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    min_len: int,
) -> tuple[list[float], list[str]]:
    """Score the first ``min_len`` gold/trace pairs.

    Tries a single batched request first and falls back to per-pair requests
    if the batched response cannot be parsed.
    """
    batched = _judge_batched(backend, gold_calls, trace_calls, min_len)
    if batched is not None:
        return batched
    return _judge_per_pair(backend, gold_calls, trace_calls, min_len)


def _judge_batched(
    backend: _JudgeBackend,
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    min_len: int,
) -> tuple[list[float], list[str]] | None:
    """Issue a single request for all pairs; return ``None`` on parse failure.

    Only a :class:`_BatchParseError` (the batched response could not be parsed)
    triggers the per-pair fallback. Transport/SDK errors from
    ``backend.complete()`` propagate so an auth/network failure surfaces clearly
    instead of fanning out into N doomed per-pair requests.
    """
    prompt = _create_batch_prompt(gold_calls, trace_calls, min_len)
    raw = backend.complete(_SYSTEM_PROMPT, prompt)
    try:
        return _parse_batch_response(raw, min_len)
    except _BatchParseError:
        return None


def _parse_batch_response(raw: str, min_len: int) -> tuple[list[float], list[str]]:
    """Parse a batched JSON-array response into scores + explanations.

    Raises:
        _BatchParseError: If the response cannot be parsed into ``min_len``
            score/explanation pairs.
    """
    text = _strip_code_fences(raw)
    if not text:
        raise _BatchParseError("empty batched response")
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as e:
        raise _BatchParseError(f"invalid JSON: {e}") from e

    # Accept either a bare array or an object wrapping one (e.g. {"results": [...]}).
    if isinstance(data, dict):
        array = next((v for v in data.values() if isinstance(v, list)), None)
        if array is None:
            raise _BatchParseError("object response has no list value")
        data = array
    if not isinstance(data, list) or len(data) != min_len:
        raise _BatchParseError("response is not a list of the expected length")

    by_index: dict[int, dict[str, Any]] = {}
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise _BatchParseError("array item is not an object")
        idx = item.get("index", i)
        try:
            by_index[int(idx)] = item
        except (TypeError, ValueError):
            by_index[i] = item

    scores: list[float] = []
    explanations: list[str] = []
    for i in range(min_len):
        item = by_index.get(i)
        if item is None:
            raise _BatchParseError(f"missing item for index {i}")
        scores.append(_clamp_score(item.get("score", 0.0)))
        explanations.append(str(item.get("explanation", "No explanation provided")))
    return scores, explanations


def _judge_per_pair(
    backend: _JudgeBackend,
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    min_len: int,
) -> tuple[list[float], list[str]]:
    """Score each pair with an individual request (fallback path)."""
    scores: list[float] = []
    explanations: list[str] = []
    for i in range(min_len):
        prompt = _create_evaluation_prompt(gold_calls[i], trace_calls[i])
        try:
            raw = backend.complete(_SYSTEM_PROMPT, prompt)
            text = _strip_code_fences(raw)
            if text:
                result = json.loads(text)
                scores.append(_clamp_score(result.get("score", 0.0)))
                explanations.append(str(result.get("explanation", "No explanation provided")))
            else:
                scores.append(0.0)
                explanations.append("No response from model")
        except Exception as e:
            scores.append(0.0)
            explanations.append(f"Evaluation failed: {e!s}")
    return scores, explanations


def _format_call(call: ToolCall) -> str:
    """Render a tool call as a short labeled block for a prompt."""
    return f"- Tool: {call.tool}\n- Arguments: {json.dumps(call.args, indent=2)}"


def _create_evaluation_prompt(gold_call: ToolCall, trace_call: ToolCall) -> str:
    """Create the single-pair evaluation prompt for the LLM judge."""
    return f"""Evaluate whether these two tool calls are semantically equivalent.

**Expected Tool Call:**
{_format_call(gold_call)}

**Actual Tool Call:**
{_format_call(trace_call)}

{_SCORING_GUIDE}

Respond with a JSON object:
{{
    "score": <float between 0.0 and 1.0>,
    "explanation": "<brief explanation of your evaluation>"
}}"""


def _create_batch_prompt(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    min_len: int,
) -> str:
    """Create a batched prompt covering all gold/trace pairs."""
    blocks = []
    for i in range(min_len):
        blocks.append(
            f"""### Pair {i}
**Expected Tool Call:**
{_format_call(gold_calls[i])}

**Actual Tool Call:**
{_format_call(trace_calls[i])}"""
        )
    pairs = "\n\n".join(blocks)
    return f"""Evaluate whether each pair of tool calls is semantically equivalent.

{pairs}

{_SCORING_GUIDE}

Respond with a JSON array containing one object per pair, in order:
[
    {{"index": 0, "score": <float 0.0-1.0>, "explanation": "<brief explanation>"}},
    ...
]
Return exactly {min_len} objects, one for each pair (index 0 to {min_len - 1})."""


_SCORING_GUIDE = """Evaluate semantic equivalence considering:
1. Tool names may differ but serve the same purpose (e.g., "search" vs "web_search")
2. Argument names may differ but contain the same data (e.g., "query" vs "q")
3. Argument values may be phrased differently but mean the same thing
4. Missing optional arguments are acceptable if they don't change the intent
5. Order of arguments doesn't matter

Examples of scoring:
- 1.0: Semantically identical, same intent and data
- 0.8-0.9: Minor differences that don't affect meaning
- 0.5-0.7: Similar intent but significant differences
- 0.0-0.4: Different intent or missing critical information
- 0.0: Completely different or wrong tool/arguments"""


def calculate_batch_semantic_correctness(
    evaluations: list[tuple[list[ToolCall], list[ToolCall]]],
    *,
    judge: JudgeConfig | str | None = None,
) -> dict[str, Any]:
    """Calculate semantic correctness for multiple independent evaluations.

    This is useful for evaluating multiple test cases at once. Each evaluation
    is judged with :func:`calculate_semantic_correctness` (itself batched).

    Args:
        evaluations: List of ``(gold_calls, trace_calls)`` tuples.
        judge: Judge configuration (see :func:`calculate_semantic_correctness`).

    Returns:
        Dictionary containing:

        - ``average_score``: Average semantic score across all evaluations.
        - ``individual_scores``: List of scores for each evaluation.
        - ``total_evaluations``: Number of evaluations performed.
    """
    individual_scores = []

    for gold_calls, trace_calls in evaluations:
        result = calculate_semantic_correctness(gold_calls, trace_calls, judge=judge)
        individual_scores.append(result["semantic_score"])

    average_score = sum(individual_scores) / len(individual_scores) if individual_scores else 0.0

    return {
        "average_score": average_score,
        "individual_scores": individual_scores,
        "total_evaluations": len(evaluations),
    }
