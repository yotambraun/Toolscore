"""Tests for the in-memory evaluate() API and EvaluationResult properties."""

import pytest

from toolscore.core import (
    EvaluationResult,
    ToolScoreAssertionError,
    assert_tools,
    evaluate,
)


class TestEvaluate:
    """Tests for the evaluate() function."""

    def test_perfect_match(self):
        """Perfect match should score ~1.0."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[{"tool": "search", "args": {"q": "test"}}],
        )
        assert result.score >= 0.99
        assert result.selection_accuracy == 1.0
        assert result.argument_f1 == 1.0
        assert result.sequence_accuracy == 1.0

    def test_tool_name_mismatch(self):
        """Different tool names should lower selection accuracy."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[{"tool": "lookup", "args": {"q": "test"}}],
        )
        assert result.selection_accuracy == 0.0
        assert result.score < 1.0

    def test_argument_mismatch(self):
        """Different args should lower argument F1."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "hello"}}],
            actual=[{"tool": "search", "args": {"q": "world"}}],
        )
        assert result.selection_accuracy == 1.0
        assert result.argument_f1 < 1.0

    def test_multiple_calls(self):
        """Multiple calls should be evaluated correctly."""
        result = evaluate(
            expected=[
                {"tool": "get_weather", "args": {"city": "NYC"}},
                {"tool": "send_email", "args": {"to": "user@example.com"}},
            ],
            actual=[
                {"tool": "get_weather", "args": {"city": "NYC"}},
                {"tool": "send_email", "args": {"to": "user@example.com"}},
            ],
        )
        assert result.score >= 0.99

    def test_empty_calls(self):
        """Empty lists should work."""
        result = evaluate(expected=[], actual=[])
        assert result.selection_accuracy == 1.0

    def test_no_args_defaults_to_empty(self):
        """Missing args should default to empty dict."""
        result = evaluate(
            expected=[{"tool": "ping"}],
            actual=[{"tool": "ping"}],
        )
        assert result.selection_accuracy == 1.0
        assert result.sequence_accuracy == 1.0
        # Score may not be 1.0 because argument F1 is 0 when there are no args
        assert result.score >= 0.6

    def test_extra_calls_lower_score(self):
        """Extra actual calls should impact score."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[
                {"tool": "search", "args": {"q": "test"}},
                {"tool": "search", "args": {"q": "test"}},
            ],
        )
        assert result.score < 1.0

    def test_missing_calls_lower_score(self):
        """Missing actual calls should impact score."""
        result = evaluate(
            expected=[
                {"tool": "a", "args": {}},
                {"tool": "b", "args": {}},
            ],
            actual=[{"tool": "a", "args": {}}],
        )
        assert result.score < 1.0

    def test_evaluate_expected_not_list(self):
        """Non-list expected should raise TypeError."""
        with pytest.raises(TypeError, match="expected must be a list"):
            evaluate(expected="not a list", actual=[])  # type: ignore[arg-type]

    def test_evaluate_actual_not_list(self):
        """Non-list actual should raise TypeError."""
        with pytest.raises(TypeError, match="actual must be a list"):
            evaluate(expected=[], actual="not a list")  # type: ignore[arg-type]

    def test_evaluate_invalid_weight_key(self):
        """Unknown weight key should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown weight keys"):
            evaluate(
                expected=[{"tool": "a"}],
                actual=[{"tool": "a"}],
                weights={"bad_key": 0.5},
            )

    def test_evaluate_negative_weight(self):
        """Negative weight value should raise ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            evaluate(
                expected=[{"tool": "a"}],
                actual=[{"tool": "a"}],
                weights={"selection_accuracy": -0.1},
            )

    def test_invalid_item_missing_tool(self):
        """Item without tool key should raise ValueError."""
        with pytest.raises(ValueError, match="missing 'tool' key"):
            evaluate(expected=[{"args": {"q": "test"}}], actual=[])

    def test_invalid_item_not_dict(self):
        """Non-dict item should raise ValueError."""
        with pytest.raises(ValueError, match="not a dict"):
            evaluate(expected=["not a dict"], actual=[])  # type: ignore[list-item]

    def test_custom_weights(self):
        """Custom weights should affect the composite score."""
        # With no args, argument_f1 is 0, so default weights give < 1.0
        result_default = evaluate(
            expected=[{"tool": "a"}],
            actual=[{"tool": "a"}],
        )
        # Weight only selection_accuracy, which is 1.0
        result_custom = evaluate(
            expected=[{"tool": "a"}],
            actual=[{"tool": "a"}],
            weights={"selection_accuracy": 1.0, "argument_f1": 0.0, "sequence_accuracy": 0.0, "redundant_rate": 0.0},
        )
        assert result_default.score < result_custom.score
        assert result_custom.score == 1.0

    def test_metrics_populated(self):
        """evaluate() should populate all core metrics."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[{"tool": "search", "args": {"q": "test"}}],
        )
        assert "invocation_accuracy" in result.metrics
        assert "selection_accuracy" in result.metrics
        assert "argument_metrics" in result.metrics
        assert "sequence_metrics" in result.metrics
        assert "efficiency_metrics" in result.metrics
        assert "tool_correctness_metrics" in result.metrics
        assert "trajectory_metrics" in result.metrics


class TestEvaluationResultProperties:
    """Tests for EvaluationResult convenience properties."""

    def test_score_with_empty_metrics(self):
        """Score with no metrics defaults to 0.1 (redundant_rate inverted)."""
        result = EvaluationResult()
        # With all zeros except redundant_rate weight * (1 - 0) = 0.1
        assert result.score == pytest.approx(0.1)

    def test_selection_accuracy_property(self):
        """selection_accuracy property should read from metrics."""
        result = EvaluationResult()
        result.metrics["selection_accuracy"] = 0.75
        assert result.selection_accuracy == 0.75

    def test_argument_f1_property(self):
        """argument_f1 property should read from nested metrics."""
        result = EvaluationResult()
        result.metrics["argument_metrics"] = {"f1": 0.8, "precision": 0.9, "recall": 0.7}
        assert result.argument_f1 == 0.8

    def test_sequence_accuracy_property(self):
        """sequence_accuracy property should read from nested metrics."""
        result = EvaluationResult()
        result.metrics["sequence_metrics"] = {"sequence_accuracy": 0.6, "edit_distance": 2}
        assert result.sequence_accuracy == 0.6

    def test_to_dict_includes_score(self):
        """to_dict should include the composite score."""
        result = EvaluationResult()
        d = result.to_dict()
        assert "score" in d


class TestAssertTools:
    """Tests for the assert_tools helper."""

    def test_passing_assertion(self):
        """Passing assertion should return result."""
        result = assert_tools(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[{"tool": "search", "args": {"q": "test"}}],
            min_score=0.9,
        )
        assert result.score >= 0.9

    def test_failing_assertion(self):
        """Failing assertion should raise ToolScoreAssertionError."""
        with pytest.raises(ToolScoreAssertionError, match="below minimum"):
            assert_tools(
                expected=[{"tool": "search", "args": {"q": "test"}}],
                actual=[{"tool": "wrong_tool", "args": {"q": "other"}}],
                min_score=0.9,
            )

    def test_assert_tools_min_score_too_high(self):
        """min_score above 1.0 should raise ValueError."""
        with pytest.raises(ValueError, match=r"between 0\.0 and 1\.0"):
            assert_tools(
                expected=[{"tool": "a"}],
                actual=[{"tool": "a"}],
                min_score=1.5,
            )

    def test_assert_tools_min_score_negative(self):
        """Negative min_score should raise ValueError."""
        with pytest.raises(ValueError, match=r"between 0\.0 and 1\.0"):
            assert_tools(
                expected=[{"tool": "a"}],
                actual=[{"tool": "a"}],
                min_score=-0.1,
            )

    def test_custom_weights(self):
        """assert_tools should pass weights through to evaluate."""
        # This should pass since we weight only selection_accuracy
        result = assert_tools(
            expected=[{"tool": "search"}],
            actual=[{"tool": "search"}],
            min_score=0.9,
            weights={"selection_accuracy": 1.0, "argument_f1": 0.0, "sequence_accuracy": 0.0, "redundant_rate": 0.0},
        )
        assert result.score >= 0.9
