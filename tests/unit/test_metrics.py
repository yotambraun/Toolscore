"""Unit tests for metrics calculations."""

from toolscore.adapters.base import ToolCall
from toolscore.metrics import (
    calculate_argument_f1,
    calculate_edit_distance,
    calculate_invocation_accuracy,
    calculate_redundant_call_rate,
    calculate_selection_accuracy,
)
from toolscore.metrics.arguments import _compare_values


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


class TestStrictArgumentComparison:
    """Tests for strict=True in _compare_values and calculate_argument_f1."""

    # --- _compare_values unit tests ---

    def test_int_float_lenient_by_default(self) -> None:
        """Default (strict=False) treats int 1 == float 1.0."""
        assert _compare_values(1, 1.0) is True

    def test_int_float_strict_not_equal(self) -> None:
        """strict=True: int 1 != float 1.0 (different types)."""
        assert _compare_values(1, 1.0, strict=True) is False

    def test_string_strip_lenient_by_default(self) -> None:
        """Default (strict=False) strips whitespace from strings."""
        assert _compare_values("a ", "a") is True

    def test_string_strip_strict_not_equal(self) -> None:
        """strict=True: 'a ' != 'a' (no stripping)."""
        assert _compare_values("a ", "a", strict=True) is False

    def test_equal_values_always_match(self) -> None:
        """Identical values match in both modes."""
        assert _compare_values("hello", "hello", strict=True) is True
        assert _compare_values(42, 42, strict=True) is True

    # --- calculate_argument_f1 with strict ---

    def test_argument_f1_strict_int_float_mismatch(self) -> None:
        """calculate_argument_f1 strict=True: int vs float counts as wrong."""
        gold = [ToolCall(tool="t", args={"x": 1})]
        trace = [ToolCall(tool="t", args={"x": 1.0})]

        lenient = calculate_argument_f1(gold, trace, strict=False)
        strict = calculate_argument_f1(gold, trace, strict=True)

        assert lenient["f1"] == 1.0
        assert strict["f1"] < 1.0

    def test_argument_f1_strict_string_strip_mismatch(self) -> None:
        """calculate_argument_f1 strict=True: trailing space counts as wrong."""
        gold = [ToolCall(tool="t", args={"q": "hello "})]
        trace = [ToolCall(tool="t", args={"q": "hello"})]

        lenient = calculate_argument_f1(gold, trace, strict=False)
        strict = calculate_argument_f1(gold, trace, strict=True)

        assert lenient["f1"] == 1.0
        assert strict["f1"] < 1.0

    # --- evaluate() with strict ---

    def test_evaluate_strict_via_core(self) -> None:
        """evaluate(strict=True) propagates to argument comparison."""
        from toolscore.core import evaluate

        result_lenient = evaluate(
            expected=[{"tool": "t", "args": {"x": 1}}],
            actual=[{"tool": "t", "args": {"x": 1.0}}],
            strict=False,
        )
        result_strict = evaluate(
            expected=[{"tool": "t", "args": {"x": 1}}],
            actual=[{"tool": "t", "args": {"x": 1.0}}],
            strict=True,
        )
        assert result_lenient.argument_f1 == 1.0
        assert result_strict.argument_f1 < 1.0


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
