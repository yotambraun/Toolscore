"""Unit tests for trajectory evaluation metrics."""

import pytest

from toolscore.adapters.base import ToolCall
from toolscore.metrics.trajectory import (
    calculate_partial_trajectory_accuracy,
    calculate_trajectory_accuracy,
)


class TestTrajectoryAccuracy:
    """Tests for trajectory accuracy metric."""

    def test_perfect_trajectory_match(self) -> None:
        """Test trajectory with perfect step-by-step match."""
        gold = [
            ToolCall(tool="search", args={"query": "python"}),
            ToolCall(tool="summarize", args={"text": "results"}),
            ToolCall(tool="respond", args={"message": "summary"}),
        ]
        trace = [
            ToolCall(tool="search", args={"query": "python"}),
            ToolCall(tool="summarize", args={"text": "results"}),
            ToolCall(tool="respond", args={"message": "summary"}),
        ]

        result = calculate_trajectory_accuracy(gold, trace)

        assert result["trajectory_accuracy"] == 1.0
        assert result["step_match_rate"] == 1.0
        assert result["path_efficiency"] == 1.0
        assert result["correct_steps"] == 3
        assert result["total_expected_steps"] == 3
        assert len(result["trajectory_details"]) == 3
        assert all(detail["matches"] for detail in result["trajectory_details"])

    def test_wrong_trajectory_path(self) -> None:
        """Test trajectory with completely different path."""
        gold = [
            ToolCall(tool="search", args={"query": "python"}),
            ToolCall(tool="summarize", args={"text": "results"}),
        ]
        trace = [
            ToolCall(tool="calculate", args={"x": 5}),
            ToolCall(tool="format", args={"data": "result"}),
        ]

        result = calculate_trajectory_accuracy(gold, trace)

        assert result["trajectory_accuracy"] == 0.0
        assert result["step_match_rate"] == 0.0
        assert result["path_efficiency"] == 1.0  # Same length
        assert result["correct_steps"] == 0
        assert len(result["trajectory_details"]) == 2

    def test_trajectory_with_extra_steps(self) -> None:
        """Test trajectory where agent took extra unnecessary steps."""
        gold = [
            ToolCall(tool="search", args={"query": "python"}),
            ToolCall(tool="summarize", args={"text": "results"}),
        ]
        trace = [
            ToolCall(tool="search", args={"query": "python"}),
            ToolCall(tool="validate", args={"data": "search_results"}),  # Extra
            ToolCall(tool="summarize", args={"text": "results"}),
            ToolCall(tool="log", args={"message": "done"}),  # Extra
        ]

        result = calculate_trajectory_accuracy(gold, trace)

        # First step matches, second doesn't (validate instead of summarize)
        assert result["step_match_rate"] == 0.5  # 1 out of 2 gold steps
        assert result["path_efficiency"] == 0.5  # 2 expected / 4 actual = 0.5
        assert result["trajectory_accuracy"] == 0.25  # 0.5 * 0.5
        assert result["correct_steps"] == 1
        assert len(result["trajectory_details"]) == 4

    def test_trajectory_stopped_early(self) -> None:
        """Test trajectory where agent stopped before completing all steps."""
        gold = [
            ToolCall(tool="search", args={"query": "python"}),
            ToolCall(tool="summarize", args={"text": "results"}),
            ToolCall(tool="respond", args={"message": "summary"}),
        ]
        trace = [
            ToolCall(tool="search", args={"query": "python"}),
        ]

        result = calculate_trajectory_accuracy(gold, trace)

        assert result["step_match_rate"] == pytest.approx(1 / 3)
        assert result["path_efficiency"] == 1.0  # No extra steps
        assert result["trajectory_accuracy"] == pytest.approx(1 / 3)
        assert result["correct_steps"] == 1
        assert len(result["trajectory_details"]) == 3
        # Check that missing steps are marked
        assert result["trajectory_details"][1]["actual_tool"] is None
        assert result["trajectory_details"][2]["actual_tool"] is None

    def test_trajectory_with_argument_mismatch(self) -> None:
        """Test trajectory where tool names match but arguments differ."""
        gold = [
            ToolCall(tool="search", args={"query": "python", "limit": 10}),
        ]
        trace = [
            ToolCall(tool="search", args={"query": "python", "limit": 5}),  # Different limit
        ]

        result = calculate_trajectory_accuracy(gold, trace)

        assert result["correct_steps"] == 0  # Args must match exactly
        assert result["step_match_rate"] == 0.0

    def test_empty_gold_trajectory(self) -> None:
        """Test with empty gold standard."""
        gold: list[ToolCall] = []
        trace = [ToolCall(tool="search", args={})]

        result = calculate_trajectory_accuracy(gold, trace)

        assert result["trajectory_accuracy"] == 0.0
        assert result["step_match_rate"] == 0.0

    def test_empty_trace_trajectory(self) -> None:
        """Test with empty trace."""
        gold = [ToolCall(tool="search", args={})]
        trace: list[ToolCall] = []

        result = calculate_trajectory_accuracy(gold, trace)

        assert result["trajectory_accuracy"] == 0.0
        assert result["step_match_rate"] == 0.0
        assert result["path_efficiency"] == 0.0

    def test_both_empty(self) -> None:
        """Test with both gold and trace empty."""
        gold: list[ToolCall] = []
        trace: list[ToolCall] = []

        result = calculate_trajectory_accuracy(gold, trace)

        assert result["trajectory_accuracy"] == 1.0  # Vacuously true
        assert result["step_match_rate"] == 1.0

    def test_trajectory_details_structure(self) -> None:
        """Test that trajectory details have correct structure."""
        gold = [ToolCall(tool="search", args={"q": "test"})]
        trace = [ToolCall(tool="find", args={"query": "test"})]

        result = calculate_trajectory_accuracy(gold, trace)

        detail = result["trajectory_details"][0]
        assert "step" in detail
        assert "expected_tool" in detail
        assert "actual_tool" in detail
        assert "matches" in detail
        assert "expected_args" in detail
        assert "actual_args" in detail
        assert detail["step"] == 1
        assert detail["expected_tool"] == "search"
        assert detail["actual_tool"] == "find"
        assert detail["matches"] is False


class TestPartialTrajectoryAccuracy:
    """Tests for partial trajectory accuracy (flexible matching)."""

    def test_partial_accuracy_correct_tools_wrong_order(self) -> None:
        """Test partial accuracy when tools are correct but in wrong order."""
        gold = [
            ToolCall(tool="search", args={"query": "python"}),
            ToolCall(tool="summarize", args={"text": "results"}),
            ToolCall(tool="respond", args={"message": "summary"}),
        ]
        trace = [
            ToolCall(tool="respond", args={"message": "summary"}),  # Out of order
            ToolCall(tool="search", args={"query": "python"}),
            ToolCall(tool="summarize", args={"text": "results"}),
        ]

        result = calculate_partial_trajectory_accuracy(gold, trace)

        # All expected tools were called, just in different order
        assert result["partial_trajectory_accuracy"] == 1.0

    def test_partial_accuracy_missing_tools(self) -> None:
        """Test partial accuracy when some tools are missing."""
        gold = [
            ToolCall(tool="search", args={"query": "python"}),
            ToolCall(tool="summarize", args={"text": "results"}),
            ToolCall(tool="respond", args={"message": "summary"}),
        ]
        trace = [
            ToolCall(tool="search", args={"query": "python"}),
            # Missing summarize
            ToolCall(tool="respond", args={"message": "summary"}),
        ]

        result = calculate_partial_trajectory_accuracy(gold, trace)

        assert result["partial_trajectory_accuracy"] == pytest.approx(2 / 3)

    def test_partial_accuracy_with_tool_name_variations(self) -> None:
        """Test partial accuracy with flexible tool name matching."""
        gold = [
            ToolCall(tool="web_search", args={"query": "python"}),
            ToolCall(tool="text_summarize", args={"text": "results"}),
        ]
        trace = [
            ToolCall(tool="websearch", args={"query": "python"}),  # No underscore
            ToolCall(tool="textsummarize", args={"text": "results"}),
        ]

        result = calculate_partial_trajectory_accuracy(gold, trace, allow_tool_name_variations=True)

        # With normalization, these should match
        assert result["partial_trajectory_accuracy"] == 1.0

    def test_partial_accuracy_without_variations(self) -> None:
        """Test that strict matching doesn't allow variations."""
        gold = [ToolCall(tool="web_search", args={})]
        trace = [ToolCall(tool="websearch", args={})]

        result = calculate_partial_trajectory_accuracy(gold, trace, allow_tool_name_variations=False)

        assert result["partial_trajectory_accuracy"] == 0.0

    def test_partial_accuracy_empty_gold(self) -> None:
        """Test partial accuracy with empty gold."""
        gold: list[ToolCall] = []
        trace = [ToolCall(tool="search", args={})]

        result = calculate_partial_trajectory_accuracy(gold, trace)

        assert result["partial_trajectory_accuracy"] == 0.0

    def test_partial_accuracy_empty_trace(self) -> None:
        """Test partial accuracy with empty trace."""
        gold = [ToolCall(tool="search", args={})]
        trace: list[ToolCall] = []

        result = calculate_partial_trajectory_accuracy(gold, trace)

        assert result["partial_trajectory_accuracy"] == 0.0

    def test_partial_accuracy_duplicate_tools_in_trace(self) -> None:
        """Test partial accuracy when trace has duplicate tools."""
        gold = [ToolCall(tool="search", args={"query": "python"})]
        trace = [
            ToolCall(tool="search", args={"query": "python"}),
            ToolCall(tool="search", args={"query": "python"}),  # Duplicate
        ]

        result = calculate_partial_trajectory_accuracy(gold, trace)

        # Should only match once
        assert result["partial_trajectory_accuracy"] == 1.0
