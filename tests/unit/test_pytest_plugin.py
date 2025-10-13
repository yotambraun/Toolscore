"""Unit tests for pytest plugin assertion helpers."""

import pytest

from toolscore.adapters.base import ToolCall
from toolscore.core import EvaluationResult
from toolscore.pytest_plugin import ToolscoreAssertions


@pytest.fixture
def mock_result():
    """Create a mock evaluation result for testing."""
    gold_calls = [
        ToolCall(tool="test_tool", args={"x": 1}),
    ]
    trace_calls = [
        ToolCall(tool="test_tool", args={"x": 1}),
    ]

    metrics = {
        "invocation_accuracy": 0.95,
        "selection_accuracy": 0.90,
        "sequence_metrics": {
            "edit_distance": 0.0,
            "normalized_distance": 0.0,
            "sequence_accuracy": 1.0,
        },
        "argument_metrics": {
            "precision": 0.88,
            "recall": 0.92,
            "f1": 0.90,
        },
        "efficiency_metrics": {
            "redundant_count": 0,
            "total_calls": 1,
            "redundant_rate": 0.0,
        },
        "side_effect_metrics": {
            "total_checks": 0,
            "passed_checks": 0,
            "success_rate": 1.0,
            "details": [],
        },
    }

    result = EvaluationResult()
    result.gold_calls = gold_calls
    result.trace_calls = trace_calls
    result.metrics = metrics

    return result


class TestToolscoreAssertions:
    """Tests for ToolscoreAssertions helper class."""

    def test_assert_invocation_accuracy_pass(self, mock_result):
        """Test invocation accuracy assertion passes."""
        assertions = ToolscoreAssertions()
        # Should not raise
        assertions.assert_invocation_accuracy(mock_result, 0.9)

    def test_assert_invocation_accuracy_fail(self, mock_result):
        """Test invocation accuracy assertion fails."""
        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Invocation accuracy"):
            assertions.assert_invocation_accuracy(mock_result, 0.99)

    def test_assert_invocation_accuracy_custom_msg(self, mock_result):
        """Test invocation accuracy assertion with custom message."""
        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Custom error"):
            assertions.assert_invocation_accuracy(
                mock_result, 0.99, msg="Custom error"
            )

    def test_assert_selection_accuracy_pass(self, mock_result):
        """Test selection accuracy assertion passes."""
        assertions = ToolscoreAssertions()
        assertions.assert_selection_accuracy(mock_result, 0.85)

    def test_assert_selection_accuracy_fail(self, mock_result):
        """Test selection accuracy assertion fails."""
        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Selection accuracy"):
            assertions.assert_selection_accuracy(mock_result, 0.95)

    def test_assert_sequence_accuracy_pass(self, mock_result):
        """Test sequence accuracy assertion passes."""
        assertions = ToolscoreAssertions()
        assertions.assert_sequence_accuracy(mock_result, 0.95)

    def test_assert_sequence_accuracy_fail(self, mock_result):
        """Test sequence accuracy assertion fails."""
        # Modify result to have lower sequence accuracy
        mock_result.metrics["sequence_metrics"]["sequence_accuracy"] = 0.5

        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Sequence accuracy"):
            assertions.assert_sequence_accuracy(mock_result, 0.8)

    def test_assert_argument_f1_pass(self, mock_result):
        """Test argument F1 assertion passes."""
        assertions = ToolscoreAssertions()
        assertions.assert_argument_f1(mock_result, 0.85)

    def test_assert_argument_f1_fail(self, mock_result):
        """Test argument F1 assertion fails."""
        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Argument F1"):
            assertions.assert_argument_f1(mock_result, 0.95)

    def test_assert_redundancy_below_pass(self, mock_result):
        """Test redundancy assertion passes."""
        assertions = ToolscoreAssertions()
        assertions.assert_redundancy_below(mock_result, 0.1)

    def test_assert_redundancy_below_fail(self, mock_result):
        """Test redundancy assertion fails."""
        # Modify result to have high redundancy
        mock_result.metrics["efficiency_metrics"]["redundant_rate"] = 0.5

        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Redundant call rate"):
            assertions.assert_redundancy_below(mock_result, 0.2)

    def test_assert_all_metrics_above_pass(self, mock_result):
        """Test all metrics assertion passes."""
        assertions = ToolscoreAssertions()
        assertions.assert_all_metrics_above(mock_result, 0.85)

    def test_assert_all_metrics_above_fail(self, mock_result):
        """Test all metrics assertion fails when one metric is low."""
        # Modify one metric to be below threshold
        mock_result.metrics["selection_accuracy"] = 0.5

        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="selection_accuracy"):
            assertions.assert_all_metrics_above(mock_result, 0.8)

    def test_assert_all_metrics_above_multiple_failures(self, mock_result):
        """Test all metrics assertion shows all failing metrics."""
        # Modify multiple metrics to be below threshold
        mock_result.metrics["invocation_accuracy"] = 0.5
        mock_result.metrics["selection_accuracy"] = 0.6

        assertions = ToolscoreAssertions()
        with pytest.raises(
            AssertionError,
            match=r"invocation_accuracy.*selection_accuracy",
        ):
            assertions.assert_all_metrics_above(mock_result, 0.8)
