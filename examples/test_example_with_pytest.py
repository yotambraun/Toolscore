"""Example tests using the Toolscore pytest plugin.

This file demonstrates how to use Toolscore's pytest integration
to test your LLM agent's tool usage behavior.

To run these tests:
    pytest examples/test_example_with_pytest.py
"""

import pytest


@pytest.mark.toolscore
def test_openai_agent_basic(toolscore_eval):
    """Test OpenAI agent meets basic accuracy requirements."""
    result = toolscore_eval(
        gold_file="../examples/gold_calls.json",
        trace_file="../examples/trace_openai.json",
        format="openai",
    )

    # Basic assertions
    assert result.metrics["invocation_accuracy"] >= 0.8
    assert result.metrics["selection_accuracy"] >= 0.8


@pytest.mark.toolscore
def test_openai_agent_with_assertions(toolscore_eval, toolscore_assert):
    """Test OpenAI agent using helper assertions."""
    result = toolscore_eval(
        gold_file="../examples/gold_calls.json",
        trace_file="../examples/trace_openai.json",
    )

    # Use helper assertions
    toolscore_assert.assert_invocation_accuracy(result, 0.9)
    toolscore_assert.assert_selection_accuracy(result, 0.9)
    toolscore_assert.assert_sequence_accuracy(result, 0.9)
    toolscore_assert.assert_argument_f1(result, 0.9)


@pytest.mark.toolscore
def test_anthropic_agent(toolscore_eval, toolscore_assert):
    """Test Anthropic agent performance."""
    result = toolscore_eval(
        gold_file="../examples/gold_calls.json",
        trace_file="../examples/trace_anthropic.json",
        format="anthropic",
    )

    # Assert all core metrics are above threshold
    toolscore_assert.assert_all_metrics_above(result, 0.85)


@pytest.mark.toolscore
def test_agent_efficiency(toolscore_eval, toolscore_assert):
    """Test agent doesn't make redundant calls."""
    result = toolscore_eval(
        gold_file="../examples/gold_calls.json",
        trace_file="../examples/trace_openai.json",
    )

    # Check redundancy is low
    toolscore_assert.assert_redundancy_below(result, 0.1)


@pytest.mark.toolscore
@pytest.mark.min_accuracy(0.95)
def test_high_precision_agent(toolscore_eval):
    """Test agent meets high precision requirements."""
    result = toolscore_eval(
        gold_file="../examples/gold_calls.json",
        trace_file="../examples/trace_openai.json",
    )

    # Verify high accuracy
    assert result.metrics["invocation_accuracy"] >= 0.95
    assert result.metrics["selection_accuracy"] >= 0.95


def test_custom_error_messages(toolscore_eval, toolscore_assert):
    """Demonstrate custom error messages in assertions."""
    result = toolscore_eval(
        gold_file="../examples/gold_calls.json",
        trace_file="../examples/trace_openai.json",
    )

    # Use custom error messages
    toolscore_assert.assert_invocation_accuracy(
        result,
        0.9,
        msg="Agent failed to invoke tools correctly - check prompt engineering",
    )


def test_detailed_metrics(toolscore_eval):
    """Test accessing detailed metrics from result."""
    result = toolscore_eval(
        gold_file="../examples/gold_calls.json",
        trace_file="../examples/trace_openai.json",
    )

    # Access all metrics
    metrics = result.metrics

    # Check individual metrics
    assert metrics["invocation_accuracy"] >= 0.8

    # Check sequence metrics
    seq_metrics = metrics["sequence_metrics"]
    assert seq_metrics["edit_distance"] <= 2
    assert seq_metrics["sequence_accuracy"] >= 0.7

    # Check argument metrics
    arg_metrics = metrics["argument_metrics"]
    assert arg_metrics["precision"] >= 0.8
    assert arg_metrics["recall"] >= 0.8
    assert arg_metrics["f1"] >= 0.8

    # Check efficiency metrics
    eff_metrics = metrics["efficiency_metrics"]
    assert eff_metrics["redundant_count"] <= 1
    assert eff_metrics["redundant_rate"] <= 0.2


@pytest.mark.parametrize(
    "trace_file,format_type",
    [
        ("../examples/trace_openai.json", "openai"),
        ("../examples/trace_anthropic.json", "anthropic"),
        ("../examples/trace_custom.json", "custom"),
    ],
)
def test_multiple_formats(toolscore_eval, trace_file, format_type):
    """Test agent performance across different trace formats."""
    result = toolscore_eval(
        gold_file="../examples/gold_calls.json",
        trace_file=trace_file,
        format=format_type,
    )

    # All formats should meet basic requirements
    assert result.metrics["invocation_accuracy"] >= 0.7
    assert result.metrics["selection_accuracy"] >= 0.7
