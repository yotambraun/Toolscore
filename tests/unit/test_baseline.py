"""Tests for regression baseline comparison module."""

import json
from pathlib import Path

import pytest

from toolscore.adapters.base import ToolCall
from toolscore.baseline import (
    Baseline,
    ComparisonResult,
    RegressionItem,
    compare_to_baseline,
    load_baseline,
    save_baseline,
)
from toolscore.core import EvaluationResult


class TestRegressionItem:
    """Tests for RegressionItem dataclass."""

    def test_create_regression_item(self) -> None:
        """Test creating a regression item."""
        item = RegressionItem(
            metric_name="selection_accuracy",
            baseline_value=0.95,
            current_value=0.85,
            delta=-0.10,
            delta_percent=-10.5,
            threshold=0.05,
            status="regression",
        )
        assert item.metric_name == "selection_accuracy"
        assert item.status == "regression"
        assert item.delta == -0.10


class TestComparisonResult:
    """Tests for ComparisonResult dataclass."""

    def test_comparison_result_regressions(self) -> None:
        """Test regressions property."""
        result = ComparisonResult(
            passed=False,
            threshold=0.05,
            baseline_timestamp="2024-01-01T00:00:00Z",
            comparison_timestamp="2024-01-02T00:00:00Z",
            items=[
                RegressionItem("a", 0.9, 0.8, -0.1, -10, 0.05, "regression"),
                RegressionItem("b", 0.9, 0.95, 0.05, 5, 0.05, "improvement"),
                RegressionItem("c", 0.9, 0.89, -0.01, -1, 0.05, "stable"),
            ],
        )
        assert len(result.regressions) == 1
        assert result.regressions[0].metric_name == "a"

    def test_comparison_result_improvements(self) -> None:
        """Test improvements property."""
        result = ComparisonResult(
            passed=True,
            threshold=0.05,
            baseline_timestamp="2024-01-01T00:00:00Z",
            comparison_timestamp="2024-01-02T00:00:00Z",
            items=[
                RegressionItem("a", 0.9, 0.95, 0.05, 5, 0.05, "improvement"),
                RegressionItem("b", 0.9, 0.96, 0.06, 6, 0.05, "improvement"),
            ],
        )
        assert len(result.improvements) == 2

    def test_comparison_result_to_dict(self) -> None:
        """Test to_dict method."""
        result = ComparisonResult(
            passed=True,
            threshold=0.05,
            baseline_timestamp="2024-01-01T00:00:00Z",
            comparison_timestamp="2024-01-02T00:00:00Z",
            summary="PASS: No regressions",
        )
        d = result.to_dict()
        assert d["passed"] is True
        assert d["threshold"] == 0.05
        assert "summary" in d


class TestBaseline:
    """Tests for Baseline dataclass."""

    def test_baseline_to_dict(self) -> None:
        """Test baseline to_dict method."""
        baseline = Baseline(
            version="1.4.0",
            created_at="2024-01-01T00:00:00Z",
            gold_file_hash="abc123",
            metrics={"selection_accuracy": 0.95},
        )
        d = baseline.to_dict()
        assert d["version"] == "1.4.0"
        assert d["metrics"]["selection_accuracy"] == 0.95

    def test_baseline_from_dict(self) -> None:
        """Test baseline from_dict method."""
        data = {
            "version": "1.4.0",
            "created_at": "2024-01-01T00:00:00Z",
            "gold_file_hash": "abc123",
            "metrics": {"selection_accuracy": 0.95},
        }
        baseline = Baseline.from_dict(data)
        assert baseline.version == "1.4.0"
        assert baseline.metrics["selection_accuracy"] == 0.95

    def test_baseline_from_result(self) -> None:
        """Test creating baseline from evaluation result."""
        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="search")]
        result.trace_calls = [ToolCall(tool="search")]
        result.metrics = {
            "invocation_accuracy": 1.0,
            "selection_accuracy": 1.0,
            "argument_metrics": {"f1": 1.0, "precision": 1.0, "recall": 1.0},
        }

        baseline = Baseline.from_result(result)

        assert baseline.metrics["invocation_accuracy"] == 1.0
        assert baseline.metrics["selection_accuracy"] == 1.0
        assert "argument_f1" in baseline.metrics


class TestSaveBaseline:
    """Tests for saving baseline files."""

    def test_save_baseline_creates_file(self, tmp_path: Path) -> None:
        """Test that save_baseline creates a JSON file."""
        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="search")]
        result.trace_calls = [ToolCall(tool="search")]
        result.metrics = {"selection_accuracy": 0.95, "invocation_accuracy": 0.92}

        baseline_file = tmp_path / "baseline.json"
        save_baseline(result, baseline_file)

        assert baseline_file.exists()

    def test_save_baseline_includes_metadata(self, tmp_path: Path) -> None:
        """Test that saved baseline includes version and timestamp."""
        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="search")]
        result.trace_calls = [ToolCall(tool="search")]
        result.metrics = {"selection_accuracy": 0.95}

        baseline_file = tmp_path / "baseline.json"
        save_baseline(result, baseline_file)

        with baseline_file.open() as f:
            data = json.load(f)
        assert "version" in data
        assert "created_at" in data
        assert "metrics" in data

    def test_save_baseline_preserves_values(self, tmp_path: Path) -> None:
        """Test that metric values are preserved accurately."""
        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="search")]
        result.trace_calls = [ToolCall(tool="search")]
        result.metrics = {"selection_accuracy": 0.9567}

        baseline_file = tmp_path / "baseline.json"
        save_baseline(result, baseline_file)

        with baseline_file.open() as f:
            data = json.load(f)
        assert data["metrics"]["selection_accuracy"] == 0.9567

    def test_save_baseline_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test that parent directories are created."""
        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="search")]
        result.trace_calls = [ToolCall(tool="search")]
        result.metrics = {"selection_accuracy": 0.95}

        baseline_file = tmp_path / "nested" / "dir" / "baseline.json"
        save_baseline(result, baseline_file)

        assert baseline_file.exists()


class TestLoadBaseline:
    """Tests for loading baseline files."""

    def test_load_valid_baseline(self, tmp_path: Path) -> None:
        """Test loading a valid baseline file."""
        baseline_file = tmp_path / "baseline.json"
        baseline_file.write_text(
            json.dumps(
                {
                    "version": "1.4.0",
                    "created_at": "2024-01-01T00:00:00Z",
                    "gold_file_hash": "",
                    "metrics": {"selection_accuracy": 0.95},
                }
            )
        )

        baseline = load_baseline(baseline_file)

        assert baseline.metrics["selection_accuracy"] == 0.95

    def test_load_missing_file_raises(self) -> None:
        """Test that loading missing file raises error."""
        with pytest.raises(FileNotFoundError):
            load_baseline(Path("nonexistent.json"))

    def test_load_invalid_json_raises(self, tmp_path: Path) -> None:
        """Test that loading invalid JSON raises error."""
        baseline_file = tmp_path / "invalid.json"
        baseline_file.write_text("not valid json")

        with pytest.raises(json.JSONDecodeError):
            load_baseline(baseline_file)

    def test_load_invalid_format_raises(self, tmp_path: Path) -> None:
        """Test that loading invalid format raises error."""
        baseline_file = tmp_path / "invalid.json"
        baseline_file.write_text(json.dumps({"wrong": "format"}))

        with pytest.raises(ValueError, match="Invalid baseline"):
            load_baseline(baseline_file)


class TestCompareToBaseline:
    """Tests for baseline comparison logic."""

    def _create_result(
        self, selection: float = 0.95, invocation: float = 0.95
    ) -> EvaluationResult:
        """Helper to create evaluation result."""
        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="search")]
        result.trace_calls = [ToolCall(tool="search")]
        result.metrics = {
            "selection_accuracy": selection,
            "invocation_accuracy": invocation,
        }
        return result

    def _create_baseline(
        self, selection: float = 0.95, invocation: float = 0.95
    ) -> Baseline:
        """Helper to create baseline."""
        return Baseline(
            version="1.4.0",
            created_at="2024-01-01T00:00:00Z",
            gold_file_hash="",
            metrics={
                "selection_accuracy": selection,
                "invocation_accuracy": invocation,
            },
        )

    def test_no_regression_within_threshold(self) -> None:
        """Test passing when metrics are within threshold."""
        baseline = self._create_baseline(selection=0.95)
        result = self._create_result(selection=0.94)

        comparison = compare_to_baseline(result, baseline, threshold=0.05)

        assert comparison.passed is True
        assert len(comparison.regressions) == 0

    def test_regression_detected_beyond_threshold(self) -> None:
        """Test failure when regression exceeds threshold."""
        baseline = self._create_baseline(selection=0.95)
        result = self._create_result(selection=0.85)

        comparison = compare_to_baseline(result, baseline, threshold=0.05)

        assert comparison.passed is False
        assert len(comparison.regressions) > 0

    def test_improvement_detected(self) -> None:
        """Test that improvements are tracked."""
        baseline = self._create_baseline(selection=0.85)
        result = self._create_result(selection=0.95)

        comparison = compare_to_baseline(result, baseline, threshold=0.05)

        assert comparison.passed is True
        assert len(comparison.improvements) > 0

    def test_comparison_with_multiple_metrics(self) -> None:
        """Test comparison with multiple metrics."""
        baseline = Baseline(
            version="1.4.0",
            created_at="2024-01-01T00:00:00Z",
            gold_file_hash="",
            metrics={
                "selection_accuracy": 0.95,
                "invocation_accuracy": 0.90,
            },
        )

        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="search")]
        result.trace_calls = [ToolCall(tool="search")]
        result.metrics = {
            "selection_accuracy": 0.94,  # OK
            "invocation_accuracy": 0.80,  # Regression
        }

        comparison = compare_to_baseline(result, baseline, threshold=0.05)

        assert comparison.passed is False
        assert len(comparison.regressions) == 1
        assert comparison.regressions[0].metric_name == "invocation_accuracy"

    def test_delta_calculation(self) -> None:
        """Test that deltas are calculated correctly."""
        baseline = self._create_baseline(selection=0.90)
        result = self._create_result(selection=0.85)

        comparison = compare_to_baseline(result, baseline, threshold=0.05)

        selection_item = next(
            item for item in comparison.items if item.metric_name == "selection_accuracy"
        )
        assert selection_item.delta == pytest.approx(-0.05, abs=0.001)

    def test_stable_metrics(self) -> None:
        """Test stable metrics are tracked."""
        baseline = self._create_baseline(selection=0.95)
        result = self._create_result(selection=0.95)

        comparison = compare_to_baseline(result, baseline, threshold=0.05)

        assert comparison.passed is True
        assert len(comparison.stable) > 0

    def test_summary_generation_pass(self) -> None:
        """Test summary generation for passing result."""
        baseline = self._create_baseline(selection=0.95)
        result = self._create_result(selection=0.94)

        comparison = compare_to_baseline(result, baseline, threshold=0.05)

        assert "PASS" in comparison.summary

    def test_summary_generation_fail(self) -> None:
        """Test summary generation for failing result."""
        baseline = self._create_baseline(selection=0.95)
        result = self._create_result(selection=0.80)

        comparison = compare_to_baseline(result, baseline, threshold=0.05)

        assert "FAIL" in comparison.summary
        assert "regression" in comparison.summary.lower()

    def test_lower_is_better_metric(self) -> None:
        """Test handling of metrics where lower is better (redundant_rate)."""
        baseline = Baseline(
            version="1.4.0",
            created_at="2024-01-01T00:00:00Z",
            gold_file_hash="",
            metrics={"redundant_rate": 0.05},  # 5% redundant
        )

        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="search")]
        result.trace_calls = [ToolCall(tool="search")]
        result.metrics = {
            "efficiency_metrics": {"redundant_rate": 0.20},  # 20% redundant - worse!
        }

        comparison = compare_to_baseline(result, baseline, threshold=0.05)

        # Higher redundant_rate is a regression
        # Find the redundant_rate item and check its status
        redundant_item = next(
            (item for item in comparison.items if item.metric_name == "redundant_rate"),
            None,
        )
        assert redundant_item is not None
        assert redundant_item.delta > 0  # Increased (worse)
        assert redundant_item.status == "regression"
