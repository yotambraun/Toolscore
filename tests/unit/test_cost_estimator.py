"""Model pricing lookup: exact match, longest prefix, and no silent fallback."""

from __future__ import annotations

import warnings

import pytest

from toolscore.metrics import (
    MODEL_PRICING,
    UnknownModelPriceWarning,
    calculate_llm_cost,
    estimate_trace_cost,
    lookup_pricing,
)
from toolscore.metrics.cost_estimator import PRICES_VERIFIED_ON


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        # Exact names.
        ("claude-opus-5-5", (4.00, 20.00)),
        ("claude-sonnet-5-5", (2.00, 10.00)),
        ("claude-haiku-5-5", (0.10, 0.50)),
        ("claude-opus-4-6", (5.00, 25.00)),
        ("claude-sonnet-4-6", (3.00, 15.00)),
        ("claude-haiku-4-5", (1.00, 5.00)),
        ("gpt-6-luna", (0.10, 0.50)),
        ("gemini-3.5-flash-lite", (0.30, 2.50)),
        # The old first-substring match priced these as their shorter siblings.
        ("gpt-5-mini", (0.25, 2.00)),
        ("gpt-4o-mini", (0.15, 0.60)),
        ("gemini-2.5-flash-lite", (0.10, 0.40)),
        # Dated snapshots and variants take the longest known prefix.
        ("gpt-5-mini-2025-08-07", (0.25, 2.00)),
        ("claude-haiku-4-5-20251001", (1.00, 5.00)),
        ("gpt-5.4-mini-2026-03-01", (0.75, 4.50)),
        # Case and provider prefixes are ignored.
        ("OpenAI/GPT-6-Luna", (0.10, 0.50)),
        ("models/gemini-2.5-pro", (1.25, 10.00)),
    ],
)
def test_lookup_pricing(model: str, expected: tuple[float, float]) -> None:
    assert lookup_pricing(model) == expected


@pytest.mark.parametrize(
    "model", ["gpt-5.6-luna-x", "gpt-5.9", "claude-3-5-sonnet-20241022", "llama3.1", ""]
)
def test_prefix_needs_a_separator_or_the_model_is_unknown(model: str) -> None:
    # gpt-5.9 must not be priced as gpt-5; retired Claude 3 models are no longer listed.
    if model == "gpt-5.6-luna-x":
        assert lookup_pricing(model) == MODEL_PRICING["gpt-5.6-luna"]
    else:
        assert lookup_pricing(model) is None


def test_unknown_model_warns_and_returns_none() -> None:
    with pytest.warns(UnknownModelPriceWarning, match="llama3.1"):
        assert calculate_llm_cost("llama3.1", 1000, 1000) is None
    with pytest.warns(UnknownModelPriceWarning):
        assert estimate_trace_cost({"calls": []}, model="my-model") is None


def test_explicit_pricing_overrides_the_table() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert calculate_llm_cost("my-model", 1_000_000, 1_000_000, pricing=(1.0, 2.0)) == 3.0


def test_cost_arithmetic() -> None:
    cost = calculate_llm_cost("claude-sonnet-5-5", input_tokens=2_000_000, output_tokens=500_000)
    assert cost == pytest.approx(2 * 2.00 + 0.5 * 10.00)


def test_prices_are_dated() -> None:
    assert PRICES_VERIFIED_ON == "2026-11-01"
