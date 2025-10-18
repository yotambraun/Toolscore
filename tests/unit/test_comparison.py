"""Tests for multi-model comparison functionality."""

import json
from pathlib import Path

from toolscore.comparison import compare_models, save_comparison_report
from toolscore.core import EvaluationResult


def create_mock_result(
    inv_acc=1.0,
    sel_acc=1.0,
    tool_correct=1.0,
    seq_acc=1.0,
    arg_f1=1.0,
    red_rate=0.0,
):
    """Create a mock EvaluationResult for testing."""
    result = EvaluationResult()
    result.gold_calls = []
    result.trace_calls = []
    result.metrics = {
        "invocation_accuracy": inv_acc,
        "selection_accuracy": sel_acc,
        "tool_correctness_metrics": {
            "tool_correctness": tool_correct,
            "expected_tools": [],
            "called_tools": [],
            "missing_tools": [],
            "extra_tools": [],
        },
        "sequence_metrics": {"sequence_accuracy": seq_acc, "edit_distance": 0},
        "argument_metrics": {"f1": arg_f1, "precision": arg_f1, "recall": arg_f1},
        "efficiency_metrics": {"redundant_rate": red_rate, "total_calls": 10},
    }
    return result


def test_compare_models_basic():
    """Test basic model comparison."""
    model_results = {
        "model1": create_mock_result(inv_acc=1.0, sel_acc=1.0),
        "model2": create_mock_result(inv_acc=0.8, sel_acc=0.9),
    }

    comparison = compare_models(model_results)

    assert "models" in comparison
    assert comparison["models"] == ["model1", "model2"]
    assert "metrics" in comparison
    assert "rankings" in comparison
    assert "best_model" in comparison


def test_compare_models_metrics_extraction():
    """Test that metrics are correctly extracted."""
    model_results = {
        "model1": create_mock_result(inv_acc=0.9, sel_acc=0.95, arg_f1=0.85),
        "model2": create_mock_result(inv_acc=0.85, sel_acc=0.9, arg_f1=0.8),
    }

    comparison = compare_models(model_results)

    # Check invocation accuracy
    assert comparison["metrics"]["invocation_accuracy"]["model1"] == 0.9
    assert comparison["metrics"]["invocation_accuracy"]["model2"] == 0.85

    # Check selection accuracy
    assert comparison["metrics"]["selection_accuracy"]["model1"] == 0.95
    assert comparison["metrics"]["selection_accuracy"]["model2"] == 0.9

    # Check argument F1
    assert comparison["metrics"]["argument_f1"]["model1"] == 0.85
    assert comparison["metrics"]["argument_f1"]["model2"] == 0.8


def test_compare_models_rankings():
    """Test that models are ranked correctly."""
    model_results = {
        "model1": create_mock_result(inv_acc=1.0),
        "model2": create_mock_result(inv_acc=0.8),
        "model3": create_mock_result(inv_acc=0.9),
    }

    comparison = compare_models(model_results)

    # Rankings should be highest to lowest
    assert comparison["rankings"]["invocation_accuracy"] == [
        "model1",
        "model3",
        "model2",
    ]


def test_compare_models_redundant_rate_ranking():
    """Test that redundant rate is ranked correctly (lower is better)."""
    model_results = {
        "model1": create_mock_result(red_rate=0.0),  # Best
        "model2": create_mock_result(red_rate=0.3),  # Worst
        "model3": create_mock_result(red_rate=0.1),  # Middle
    }

    comparison = compare_models(model_results)

    # For redundant rate, lower is better
    assert comparison["rankings"]["redundant_rate"] == [
        "model1",  # 0.0
        "model3",  # 0.1
        "model2",  # 0.3
    ]


def test_compare_models_best_model():
    """Test that best model is determined correctly."""
    model_results = {
        "perfect": create_mock_result(
            inv_acc=1.0, sel_acc=1.0, arg_f1=1.0, seq_acc=1.0, red_rate=0.0
        ),
        "good": create_mock_result(inv_acc=0.9, sel_acc=0.9, arg_f1=0.9, seq_acc=0.9, red_rate=0.1),
        "poor": create_mock_result(inv_acc=0.5, sel_acc=0.5, arg_f1=0.5, seq_acc=0.5, red_rate=0.5),
    }

    comparison = compare_models(model_results)

    assert comparison["best_model"]["name"] == "perfect"
    assert comparison["best_model"]["average_score"] == 1.0


def test_compare_models_average_scores():
    """Test that average scores are calculated correctly."""
    model_results = {
        "model1": create_mock_result(
            inv_acc=1.0, sel_acc=1.0, tool_correct=1.0, seq_acc=1.0, arg_f1=1.0, red_rate=0.0
        ),
    }

    comparison = compare_models(model_results)

    # Average of 1.0, 1.0, 1.0, 1.0, 1.0, (1.0 - 0.0) = 6.0 / 6 = 1.0
    assert comparison["summary"]["average_scores"]["model1"] == 1.0


def test_compare_models_empty():
    """Test comparison with no models."""
    comparison = compare_models({})

    assert comparison == {}


def test_compare_models_single_model():
    """Test comparison with a single model."""
    model_results = {
        "model1": create_mock_result(inv_acc=0.9),
    }

    comparison = compare_models(model_results)

    assert comparison["models"] == ["model1"]
    assert comparison["best_model"]["name"] == "model1"
    assert len(comparison["rankings"]["invocation_accuracy"]) == 1


def test_save_comparison_report(tmp_path):
    """Test saving comparison report to file."""
    comparison = {
        "models": ["model1", "model2"],
        "metrics": {"invocation_accuracy": {"model1": 1.0, "model2": 0.8}},
        "rankings": {"invocation_accuracy": ["model1", "model2"]},
        "best_model": {"name": "model1", "average_score": 1.0},
        "summary": {"total_models": 2},
    }

    output_file = tmp_path / "comparison.json"
    result_path = save_comparison_report(comparison, output_file)

    assert result_path == output_file
    assert output_file.exists()

    # Verify content
    with output_file.open() as f:
        saved_comparison = json.load(f)

    assert saved_comparison["models"] == ["model1", "model2"]
    assert saved_comparison["best_model"]["name"] == "model1"


def test_save_comparison_report_creates_parent_dirs(tmp_path):
    """Test that parent directories are created if needed."""
    output_file = tmp_path / "nested" / "dir" / "comparison.json"
    comparison = {"models": [], "metrics": {}}

    result_path = save_comparison_report(comparison, output_file)

    assert result_path.exists()
    assert result_path.parent.exists()


def test_compare_models_all_metrics():
    """Test that all expected metrics are compared."""
    model_results = {
        "model1": create_mock_result(
            inv_acc=0.9,
            sel_acc=0.95,
            tool_correct=0.85,
            seq_acc=0.92,
            arg_f1=0.88,
            red_rate=0.05,
        ),
    }

    comparison = compare_models(model_results)

    expected_metrics = [
        "invocation_accuracy",
        "selection_accuracy",
        "tool_correctness",
        "sequence_accuracy",
        "argument_f1",
        "redundant_rate",
    ]

    for metric in expected_metrics:
        assert metric in comparison["metrics"]
        assert "model1" in comparison["metrics"][metric]
        assert metric in comparison["rankings"]


def test_compare_models_tie_scenario():
    """Test comparison when models have identical scores."""
    model_results = {
        "model1": create_mock_result(inv_acc=0.9),
        "model2": create_mock_result(inv_acc=0.9),
    }

    comparison = compare_models(model_results)

    # Both should be in rankings
    assert len(comparison["rankings"]["invocation_accuracy"]) == 2
    # One of them should be best
    assert comparison["best_model"]["name"] in ["model1", "model2"]


def test_compare_models_extreme_values():
    """Test comparison with extreme metric values."""
    model_results = {
        "zero": create_mock_result(inv_acc=0.0, sel_acc=0.0, arg_f1=0.0),
        "perfect": create_mock_result(inv_acc=1.0, sel_acc=1.0, arg_f1=1.0),
    }

    comparison = compare_models(model_results)

    assert comparison["best_model"]["name"] == "perfect"
    assert comparison["rankings"]["invocation_accuracy"] == ["perfect", "zero"]
