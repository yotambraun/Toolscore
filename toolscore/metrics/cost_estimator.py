"""Cost estimation for LLM API calls.

Prices are list prices in USD per million tokens for standard (non-batch,
non-cached) text requests, verified on the providers' official pricing pages on
2026-11-01:

* Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
* OpenAI: https://developers.openai.com/api/docs/pricing
* Google: https://ai.google.dev/gemini-api/docs/pricing

Where a price depends on prompt length, the short-prompt tier is listed. Pass
``pricing=(input, output)`` to :func:`calculate_llm_cost` for any other model or
price.

Model names are matched exactly, then by the longest known name the model starts
with followed by ``-``, ``@`` or ``:`` (so ``claude-haiku-4-5-20251001`` is
priced as ``claude-haiku-4-5`` and ``gpt-5-mini-2025-08-07`` as
``gpt-5-mini``, not ``gpt-5``). Provider prefixes such as ``openai/`` or
``models/`` are ignored. An unknown model has no price: the functions return
``None`` and emit a :class:`UnknownModelPriceWarning` instead of guessing.
"""

from __future__ import annotations

import warnings
from typing import Any

#: Date the prices below were last checked.
PRICES_VERIFIED_ON = "2026-11-01"

#: (input, output) USD per 1M tokens. See the module docstring for sources.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-fable-5-1": (10.00, 50.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),  # prompts up to 100K tokens ($0.50/$2.50 above)
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),  # deprecated; retires 2026-11-30
    "claude-haiku-4-5": (1.00, 5.00),
    # OpenAI
    "gpt-6-astra": (10.00, 50.00),
    "gpt-6.1-sol": (2.00, 10.00),
    "gpt-6.1-terra": (1.00, 5.00),
    "gpt-6-sol": (2.00, 10.00),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5.6-sol": (4.00, 20.00),
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.2": (1.75, 14.00),
    "gpt-5.1": (1.25, 10.00),
    "gpt-5": (1.25, 10.00),  # gpt-5, -mini and -nano retire 2026-12-11
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-4.1": (2.00, 8.00),  # gpt-4.1, gpt-4o and their minis retire 2027-01-14
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    # Google Gemini
    "gemini-4-argon": (2.00, 10.00),  # $4.00/$20.00 from 2026-12-01
    "gemini-3.8-flash": (0.75, 3.75),  # $1.50/$7.50 from 2027-01-01
    "gemini-3.6-flash": (0.75, 3.75),  # $1.50/$7.50 from 2027-01-01
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-pro-preview": (2.00, 12.00),  # prompts up to 200K tokens
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3-flash-preview": (0.50, 3.00),
    "gemini-2.5-pro": (1.25, 10.00),  # prompts up to 200K tokens
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}

_SEPARATORS = ("-", "@", ":")


class UnknownModelPriceWarning(UserWarning):
    """Emitted when a model has no entry in :data:`MODEL_PRICING`."""


def lookup_pricing(model: str) -> tuple[float, float] | None:
    """Find the (input, output) price per 1M tokens for a model name.

    Matching is exact first, then the longest known name that ``model`` starts
    with, followed by ``-``, ``@`` or ``:`` (a dated snapshot or a variant).
    Case and provider prefixes (``openai/``, ``models/``) are ignored.

    Args:
        model: The model name.

    Returns:
        The price pair, or ``None`` for an unknown model.
    """
    name = model.strip().lower().rsplit("/", 1)[-1]
    if name in MODEL_PRICING:
        return MODEL_PRICING[name]
    best: str | None = None
    for key in MODEL_PRICING:
        if (
            name.startswith(key)
            and name[len(key) : len(key) + 1] in _SEPARATORS
            and (best is None or len(key) > len(best))
        ):
            best = key
    return MODEL_PRICING[best] if best is not None else None


def estimate_tokens(text: str) -> int:
    """Estimate number of tokens in text.

    Uses a rough heuristic: ~4 characters per token for English text.
    This is approximate and should be replaced with actual tokenizer for production.

    Args:
        text: Text to estimate tokens for.

    Returns:
        Estimated number of tokens.
    """
    if not text:
        return 0

    # Rough estimation: 1 token ≈ 4 characters
    return len(text) // 4


def estimate_json_tokens(data: dict[str, Any]) -> int:
    """Estimate tokens for JSON data.

    Args:
        data: JSON data to estimate tokens for.

    Returns:
        Estimated number of tokens.
    """
    import json

    json_str = json.dumps(data)
    return estimate_tokens(json_str)


def calculate_llm_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    pricing: tuple[float, float] | None = None,
) -> float | None:
    """Calculate the cost of an LLM API call.

    Args:
        model: Model name (e.g. ``"gpt-6-luna"``, ``"claude-haiku-5-5"``).
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.
        pricing: Optional ``(input, output)`` USD per 1M tokens, used instead of
            the built-in table (for unlisted models or negotiated prices).

    Returns:
        Cost in USD, or ``None`` (with an :class:`UnknownModelPriceWarning`)
        when the model is unknown and no ``pricing`` was given.
    """
    prices = pricing if pricing is not None else lookup_pricing(model)
    if prices is None:
        warnings.warn(
            f"No price is known for model {model!r}; pass pricing=(input, output) per 1M "
            "tokens. Returning None instead of guessing.",
            UnknownModelPriceWarning,
            stacklevel=2,
        )
        return None

    input_cost_per_1m, output_cost_per_1m = prices
    input_cost = (input_tokens / 1_000_000) * input_cost_per_1m
    output_cost = (output_tokens / 1_000_000) * output_cost_per_1m
    return input_cost + output_cost


def estimate_trace_cost(
    trace_data: dict[str, Any] | list[Any],
    model: str = "gpt-6-luna",
    pricing: tuple[float, float] | None = None,
) -> float | None:
    """Estimate cost for an entire trace.

    Args:
        trace_data: Trace data (messages, tool calls, etc.).
        model: Model name for pricing.
        pricing: Optional ``(input, output)`` USD per 1M tokens.

    Returns:
        Estimated cost in USD, or ``None`` for an unknown model (see
        :func:`calculate_llm_cost`).
    """
    total_tokens = 0

    if isinstance(trace_data, dict):
        # Estimate tokens from entire trace
        total_tokens = estimate_json_tokens(trace_data)
    elif isinstance(trace_data, list):
        # Sum tokens from all items
        for item in trace_data:
            if isinstance(item, dict):
                total_tokens += estimate_json_tokens(item)
            elif isinstance(item, str):
                total_tokens += estimate_tokens(item)

    # Assume 70% input, 30% output split (typical for tool calling)
    input_tokens = int(total_tokens * 0.7)
    output_tokens = int(total_tokens * 0.3)

    return calculate_llm_cost(model, input_tokens, output_tokens, pricing=pricing)


def format_cost(cost: float) -> str:
    """Format cost as currency string.

    Args:
        cost: Cost in USD.

    Returns:
        Formatted cost string (e.g., "$0.0042", "$1.23").
    """
    if cost < 0.01:
        # Show 4 decimal places for small costs
        return f"${cost:.4f}"
    else:
        # Show 2 decimal places for larger costs
        return f"${cost:.2f}"


def calculate_cost_savings(
    baseline_cost: float,
    optimized_cost: float,
) -> dict[str, float | str]:
    """Calculate cost savings from optimization.

    Args:
        baseline_cost: Cost before optimization.
        optimized_cost: Cost after optimization.

    Returns:
        Dictionary containing:
        - absolute_savings: Dollar amount saved
        - percentage_savings: Percentage reduction
        - formatted_savings: Human-readable savings string
    """
    absolute_savings = baseline_cost - optimized_cost
    percentage_savings = (absolute_savings / baseline_cost * 100) if baseline_cost > 0 else 0.0

    formatted_savings = f"{format_cost(absolute_savings)} ({percentage_savings:.1f}% reduction)"

    return {
        "absolute_savings": absolute_savings,
        "percentage_savings": percentage_savings,
        "formatted_savings": formatted_savings,
    }
