"""Unit tests for metrics calculations."""


from toolscore.adapters.base import ToolCall
from toolscore.metrics import (
    calculate_argument_f1,
    calculate_edit_distance,
    calculate_invocation_accuracy,
    calculate_redundant_call_rate,
    calculate_selection_accuracy,
)


class TestInvocationAccuracy:
    """Tests for invocation accuracy metric."""

    def test_perfect_match(self) -> None:
        """Test perfect invocation accuracy."""
        gold = [ToolCall(tool="tool1"), ToolCall(tool="tool2")]
        trace = [ToolCall(tool="tool1"), ToolCall(tool="tool2")]

        accuracy = calculate_invocation_accuracy(gold, trace)
        assert accuracy == 1.0

    def test_no_tools_used(self) -> None:
        """Test when no tools are expected or used."""
        accuracy = calculate_invocation_accuracy([], [])
        assert accuracy == 1.0

    def test_missing_invocations(self) -> None:
        """Test when expected tools are missing."""
        gold = [ToolCall(tool="tool1"), ToolCall(tool="tool2")]
        trace = [ToolCall(tool="tool1")]

        accuracy = calculate_invocation_accuracy(gold, trace)
        assert accuracy < 1.0


class TestSelectionAccuracy:
    """Tests for selection accuracy metric."""

    def test_perfect_selection(self) -> None:
        """Test perfect tool selection."""
        gold = [ToolCall(tool="tool1")]
        trace = [ToolCall(tool="tool1")]

        accuracy = calculate_selection_accuracy(gold, trace)
        assert accuracy == 1.0

    def test_wrong_tools(self) -> None:
        """Test when wrong tools are selected."""
        gold = [ToolCall(tool="tool1")]
        trace = [ToolCall(tool="tool2")]

        accuracy = calculate_selection_accuracy(gold, trace)
        assert accuracy == 0.0


class TestEditDistance:
    """Tests for sequence edit distance metric."""

    def test_perfect_sequence(self) -> None:
        """Test perfect sequence match."""
        gold = [ToolCall(tool="A"), ToolCall(tool="B"), ToolCall(tool="C")]
        trace = [ToolCall(tool="A"), ToolCall(tool="B"), ToolCall(tool="C")]

        result = calculate_edit_distance(gold, trace)
        assert result["edit_distance"] == 0
        assert result["sequence_accuracy"] == 1.0

    def test_different_order(self) -> None:
        """Test different order."""
        gold = [ToolCall(tool="A"), ToolCall(tool="B"), ToolCall(tool="C")]
        trace = [ToolCall(tool="B"), ToolCall(tool="A"), ToolCall(tool="C")]

        result = calculate_edit_distance(gold, trace)
        assert result["edit_distance"] > 0
        assert result["sequence_accuracy"] < 1.0


class TestArgumentF1:
    """Tests for argument F1 score metric."""

    def test_perfect_arguments(self) -> None:
        """Test perfect argument match."""
        gold = [ToolCall(tool="tool1", args={"x": 1, "y": 2})]
        trace = [ToolCall(tool="tool1", args={"x": 1, "y": 2})]

        result = calculate_argument_f1(gold, trace)
        assert result["f1"] == 1.0

    def test_missing_arguments(self) -> None:
        """Test missing arguments."""
        gold = [ToolCall(tool="tool1", args={"x": 1, "y": 2})]
        trace = [ToolCall(tool="tool1", args={"x": 1})]

        result = calculate_argument_f1(gold, trace)
        assert result["f1"] < 1.0


class TestRedundantCallRate:
    """Tests for redundant call rate metric."""

    def test_no_redundant_calls(self) -> None:
        """Test when no redundant calls are made."""
        gold = [ToolCall(tool="tool1")]
        trace = [ToolCall(tool="tool1")]

        result = calculate_redundant_call_rate(gold, trace)
        assert result["redundant_rate"] == 0.0

    def test_extra_calls(self) -> None:
        """Test when extra calls are made."""
        gold = [ToolCall(tool="tool1")]
        trace = [
            ToolCall(tool="tool1"),
            ToolCall(tool="tool2"),
            ToolCall(tool="tool3"),
        ]

        result = calculate_redundant_call_rate(gold, trace)
        assert result["redundant_count"] == 2
        assert result["redundant_rate"] > 0.0
