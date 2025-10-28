"""Cost estimation for LLM API calls."""

from typing import Any

# Pricing per 1M tokens (as of October 2025)
# Format: (input_cost_per_1m, output_cost_per_1m)
# Sources:
# - OpenAI: https://openai.com/api/pricing/
# - Anthropic: https://docs.claude.com/en/docs/about-claude/pricing
# - Google: https://ai.google.dev/gemini-api/docs/pricing
MODEL_PRICING = {
    # OpenAI models (October 2025)
    "gpt-5": (1.25, 10.00),  # Released Aug 2025, flagship model
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-4o": (2.50, 10.00),  # Still available
    "gpt-4o-mini": (0.15, 0.60),
    # Anthropic Claude models (October 2025)
    "claude-sonnet-4-5": (3.00, 15.00),  # Released Sep 2025
    "claude-haiku-4-5": (1.00, 5.00),  # Released Oct 15, 2025
    "claude-opus-4-1": (15.00, 75.00),  # Released Aug 2025
    # Legacy Claude models (for backward compatibility)
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-sonnet": (3.00, 15.00),
    "claude-3-opus": (15.00, 75.00),
    "claude-3-haiku": (0.25, 1.25),
    # Google Gemini 2.x models (October 2025)
    "gemini-2.5-pro": (1.25, 10.00),  # For prompts ≤200k tokens
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.0-flash": (0.10, 0.40),
    # Legacy Gemini 1.5 models (for backward compatibility)
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
}


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
) -> float:
    """Calculate cost for LLM API call.

    Args:
        model: Model name (e.g., "gpt-4", "claude-3-5-sonnet", "gemini-1.5-pro").
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        Cost in USD.
    """
    # Normalize model name
    model_lower = model.lower()

    # Find matching pricing
    pricing = None
    for model_key, model_pricing in MODEL_PRICING.items():
        if model_key in model_lower:
            pricing = model_pricing
            break

    if pricing is None:
        # Default to gpt-4o-mini pricing for unknown models
        pricing = MODEL_PRICING["gpt-4o-mini"]

    input_cost_per_1m, output_cost_per_1m = pricing

    # Calculate cost
    input_cost = (input_tokens / 1_000_000) * input_cost_per_1m
    output_cost = (output_tokens / 1_000_000) * output_cost_per_1m

    return input_cost + output_cost


def estimate_trace_cost(
    trace_data: dict[str, Any] | list[Any],
    model: str = "gpt-4o-mini",
) -> float:
    """Estimate cost for an entire trace.

    Args:
        trace_data: Trace data (messages, tool calls, etc.).
        model: Model name for pricing.

    Returns:
        Estimated cost in USD.
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

    return calculate_llm_cost(model, input_tokens, output_tokens)


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
