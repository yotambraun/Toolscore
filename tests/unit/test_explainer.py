"""Tests for self-explaining metrics module."""

import pytest

from toolscore.adapters.base import ToolCall
from toolscore.core import EvaluationResult
from toolscore.explainer import (
    Explanation,
    MetricExplanation,
    explain_argument_metrics,
    explain_efficiency_metrics,
    explain_selection_accuracy,
    explain_sequence_metrics,
    explain_tool_correctness,
    generate_explanations,
    get_all_tips,
    get_top_issues,
)


class TestExplanation:
    """Tests for Explanation dataclass."""

    def test_create_explanation(self) -> None:
        """Test creating an explanation."""
        exp = Explanation(
            category="missing",
            message="Expected tool 'search' was never called",
            severity="error",
        )
        assert exp.category == "missing"
        assert exp.severity == "error"
        assert "search" in exp.message

    def test_explanation_defaults(self) -> None:
        """Test explanation default values."""
        exp = Explanation(category="info", message="Test message")
        assert exp.severity == "info"
        assert exp.details == {}


class TestMetricExplanation:
    """Tests for MetricExplanation dataclass."""

    def test_create_metric_explanation(self) -> None:
        """Test creating a metric explanation."""
        exp = MetricExplanation(
            metric_name="Selection Accuracy",
            score=0.75,
            score_description="3 of 4 correct",
        )
        assert exp.metric_name == "Selection Accuracy"
        assert exp.score == 0.75
        assert exp.items == []
        assert exp.tips == []


class TestExplainSelectionAccuracy:
    """Tests for selection accuracy explanation."""

    def test_explain_perfect_match(self) -> None:
        """Test explanation for perfect metric match."""
        gold = [ToolCall(tool="search", args={"query": "test"})]
        trace = [ToolCall(tool="search", args={"query": "test"})]
        exp = explain_selection_accuracy(gold, trace, 1.0)
        assert exp.score == 1.0
        assert exp.items == []

    def test_explain_missing_tool(self) -> None:
        """Test explanation for missing tool call."""
        gold = [ToolCall(tool="search"), ToolCall(tool="calculate")]
        trace = [ToolCall(tool="search")]
        exp = explain_selection_accuracy(gold, trace, 0.5)
        assert any(item.category == "missing" for item in exp.items)
        assert any("calculate" in item.message for item in exp.items)

    def test_explain_extra_tool(self) -> None:
        """Test explanation for extra tool call."""
        gold = [ToolCall(tool="search")]
        trace = [ToolCall(tool="search"), ToolCall(tool="debug")]
        exp = explain_selection_accuracy(gold, trace, 0.5)
        assert any(item.category == "extra" for item in exp.items)

    def test_explain_tool_mismatch(self) -> None:
        """Test explanation for tool name mismatch."""
        gold = [ToolCall(tool="search_web")]
        trace = [ToolCall(tool="web_search")]
        exp = explain_selection_accuracy(gold, trace, 0.0)
        assert any(item.category == "mismatch" for item in exp.items)

    def test_detect_similar_names(self) -> None:
        """Test detection of similar tool names."""
        gold = [ToolCall(tool="summarize")]
        trace = [ToolCall(tool="summary")]
        exp = explain_selection_accuracy(gold, trace, 0.0)
        # Should suggest LLM judge for similar names
        assert any("llm-judge" in tip.lower() for tip in exp.tips)

    def test_explain_empty_traces(self) -> None:
        """Test explanation for empty traces."""
        exp = explain_selection_accuracy([], [], 0.0)
        assert exp.score_description == "N/A"


class TestExplainToolCorrectness:
    """Tests for tool correctness explanation."""

    def test_explain_perfect_correctness(self) -> None:
        """Test explanation when all expected tools are called."""
        metrics = {
            "tool_correctness": 1.0,
            "correct_count": 3,
            "total_expected": 3,
            "missing_tools": [],
            "extra_tools": [],
        }
        exp = explain_tool_correctness(metrics)
        assert exp.score == 1.0
        assert exp.items == []

    def test_explain_missing_tools(self) -> None:
        """Test explanation for missing tools."""
        metrics = {
            "tool_correctness": 0.5,
            "correct_count": 1,
            "total_expected": 2,
            "missing_tools": ["calculate"],
            "extra_tools": [],
        }
        exp = explain_tool_correctness(metrics)
        assert any(item.category == "missing" for item in exp.items)
        assert any("calculate" in item.message for item in exp.items)
        assert len(exp.tips) > 0

    def test_explain_extra_tools(self) -> None:
        """Test explanation for extra tools."""
        metrics = {
            "tool_correctness": 1.0,
            "correct_count": 2,
            "total_expected": 2,
            "missing_tools": [],
            "extra_tools": ["debug_log"],
        }
        exp = explain_tool_correctness(metrics)
        assert any(item.category == "extra" for item in exp.items)


class TestExplainArgumentMetrics:
    """Tests for argument metrics explanation."""

    def test_explain_perfect_arguments(self) -> None:
        """Test explanation for perfect argument match."""
        gold = [ToolCall(tool="search", args={"query": "test"})]
        trace = [ToolCall(tool="search", args={"query": "test"})]
        metrics = {"f1": 1.0, "precision": 1.0, "recall": 1.0}
        exp = explain_argument_metrics(gold, trace, metrics)
        assert exp.score == 1.0

    def test_explain_missing_arguments(self) -> None:
        """Test explanation for missing arguments."""
        gold = [ToolCall(tool="search", args={"query": "test", "limit": 10})]
        trace = [ToolCall(tool="search", args={"query": "test"})]
        metrics = {"f1": 0.67, "precision": 1.0, "recall": 0.5}
        exp = explain_argument_metrics(gold, trace, metrics)
        assert any(item.category == "missing" for item in exp.items)

    def test_explain_extra_arguments(self) -> None:
        """Test explanation for extra arguments."""
        gold = [ToolCall(tool="search", args={"query": "test"})]
        trace = [ToolCall(tool="search", args={"query": "test", "debug": True})]
        metrics = {"f1": 0.67, "precision": 0.5, "recall": 1.0}
        exp = explain_argument_metrics(gold, trace, metrics)
        assert any(item.category == "extra" for item in exp.items)

    def test_explain_wrong_value(self) -> None:
        """Test explanation for wrong argument value."""
        gold = [ToolCall(tool="search", args={"query": "python"})]
        trace = [ToolCall(tool="search", args={"query": "javascript"})]
        metrics = {"f1": 0.0, "precision": 0.0, "recall": 0.0}
        exp = explain_argument_metrics(gold, trace, metrics)
        assert any(item.category == "mismatch" for item in exp.items)

    def test_explain_type_mismatch(self) -> None:
        """Test explanation for argument type mismatch."""
        gold = [ToolCall(tool="search", args={"limit": "10"})]
        trace = [ToolCall(tool="search", args={"limit": 10})]
        metrics = {"f1": 0.0, "precision": 0.0, "recall": 0.0}
        exp = explain_argument_metrics(gold, trace, metrics)
        assert any(
            "Type mismatch" in item.message
            for item in exp.items
            if item.category == "mismatch"
        )


class TestExplainSequenceMetrics:
    """Tests for sequence metrics explanation."""

    def test_explain_perfect_sequence(self) -> None:
        """Test explanation for perfect sequence."""
        gold = [ToolCall(tool="a"), ToolCall(tool="b")]
        trace = [ToolCall(tool="a"), ToolCall(tool="b")]
        metrics = {"sequence_accuracy": 1.0, "edit_distance": 0}
        exp = explain_sequence_metrics(gold, trace, metrics)
        assert exp.score == 1.0
        assert exp.items == []

    def test_explain_wrong_order(self) -> None:
        """Test explanation for wrong order."""
        gold = [ToolCall(tool="a"), ToolCall(tool="b")]
        trace = [ToolCall(tool="b"), ToolCall(tool="a")]
        metrics = {"sequence_accuracy": 0.0, "edit_distance": 2}
        exp = explain_sequence_metrics(gold, trace, metrics)
        assert any(item.category == "info" for item in exp.items)

    def test_explain_extra_calls(self) -> None:
        """Test explanation for extra calls in sequence."""
        gold = [ToolCall(tool="a")]
        trace = [ToolCall(tool="a"), ToolCall(tool="b"), ToolCall(tool="c")]
        metrics = {"sequence_accuracy": 0.33, "edit_distance": 2}
        exp = explain_sequence_metrics(gold, trace, metrics)
        assert any(item.category == "extra" for item in exp.items)

    def test_explain_missing_calls(self) -> None:
        """Test explanation for missing calls in sequence."""
        gold = [ToolCall(tool="a"), ToolCall(tool="b"), ToolCall(tool="c")]
        trace = [ToolCall(tool="a")]
        metrics = {"sequence_accuracy": 0.33, "edit_distance": 2}
        exp = explain_sequence_metrics(gold, trace, metrics)
        assert any(item.category == "missing" for item in exp.items)


class TestExplainEfficiencyMetrics:
    """Tests for efficiency metrics explanation."""

    def test_explain_no_redundancy(self) -> None:
        """Test explanation for no redundant calls."""
        metrics = {"redundant_rate": 0.0, "redundant_count": 0, "total_calls": 3}
        exp = explain_efficiency_metrics(metrics)
        assert exp.score == 1.0
        assert exp.items == []

    def test_explain_with_redundancy(self) -> None:
        """Test explanation for redundant calls."""
        metrics = {"redundant_rate": 0.5, "redundant_count": 2, "total_calls": 4}
        exp = explain_efficiency_metrics(metrics)
        assert any(item.category == "warning" for item in exp.items)
        assert len(exp.tips) > 0


class TestGenerateExplanations:
    """Tests for generate_explanations function."""

    def test_generate_all_explanations(self) -> None:
        """Test generating explanations for all metrics."""
        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="search", args={"query": "test"})]
        result.trace_calls = [ToolCall(tool="search", args={"query": "test"})]
        result.metrics = {
            "selection_accuracy": 1.0,
            "invocation_accuracy": 1.0,
            "tool_correctness_metrics": {
                "tool_correctness": 1.0,
                "correct_count": 1,
                "total_expected": 1,
                "missing_tools": [],
                "extra_tools": [],
            },
            "argument_metrics": {"f1": 1.0, "precision": 1.0, "recall": 1.0},
            "sequence_metrics": {"sequence_accuracy": 1.0, "edit_distance": 0},
            "efficiency_metrics": {"redundant_rate": 0.0, "redundant_count": 0, "total_calls": 1},
        }

        explanations = generate_explanations(result)

        assert "selection_accuracy" in explanations
        assert "tool_correctness" in explanations
        assert "argument_metrics" in explanations
        assert "sequence_metrics" in explanations
        assert "efficiency_metrics" in explanations


class TestGetTopIssues:
    """Tests for get_top_issues function."""

    def test_get_top_issues_sorted_by_severity(self) -> None:
        """Test that issues are sorted by severity."""
        explanations = {
            "test": MetricExplanation(
                metric_name="Test",
                score=0.5,
                score_description="test",
                items=[
                    Explanation(category="info", message="Info message", severity="info"),
                    Explanation(category="error", message="Error message", severity="error"),
                    Explanation(category="warning", message="Warning message", severity="warning"),
                ],
            )
        }

        issues = get_top_issues(explanations, max_issues=3)

        assert issues[0].severity == "error"
        assert issues[1].severity == "warning"
        assert issues[2].severity == "info"

    def test_get_top_issues_respects_limit(self) -> None:
        """Test that max_issues limit is respected."""
        explanations = {
            "test": MetricExplanation(
                metric_name="Test",
                score=0.5,
                score_description="test",
                items=[
                    Explanation(category="error", message=f"Error {i}", severity="error")
                    for i in range(10)
                ],
            )
        }

        issues = get_top_issues(explanations, max_issues=5)

        assert len(issues) == 5


class TestGetAllTips:
    """Tests for get_all_tips function."""

    def test_get_all_tips_unique(self) -> None:
        """Test that duplicate tips are removed."""
        explanations = {
            "test1": MetricExplanation(
                metric_name="Test1",
                score=0.5,
                score_description="test",
                tips=["Tip A", "Tip B"],
            ),
            "test2": MetricExplanation(
                metric_name="Test2",
                score=0.5,
                score_description="test",
                tips=["Tip B", "Tip C"],  # Tip B is duplicate
            ),
        }

        tips = get_all_tips(explanations)

        assert len(tips) == 3
        assert "Tip A" in tips
        assert "Tip B" in tips
        assert "Tip C" in tips

    def test_get_all_tips_empty(self) -> None:
        """Test with no tips."""
        explanations = {
            "test": MetricExplanation(
                metric_name="Test",
                score=1.0,
                score_description="test",
            )
        }

        tips = get_all_tips(explanations)

        assert tips == []
