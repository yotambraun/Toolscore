"""Unit tests for report generation."""

import json
from datetime import datetime

import pytest

from toolscore.adapters.base import ToolCall
from toolscore.core import EvaluationResult
from toolscore.reports.csv_report import generate_csv_report
from toolscore.reports.html_report import generate_html_report
from toolscore.reports.json_report import generate_json_report
from toolscore.reports.markdown_report import generate_markdown_report


@pytest.fixture
def sample_result():
    """Create sample evaluation result."""
    result = EvaluationResult()
    result.gold_calls = [
        ToolCall(tool="tool1", args={"x": 1}),
        ToolCall(tool="tool2", args={"y": 2}),
    ]
    result.trace_calls = [
        ToolCall(tool="tool1", args={"x": 1}),
        ToolCall(tool="tool2", args={"y": 2}),
        ToolCall(tool="tool3", args={"z": 3}),
    ]
    result.metrics = {
        "invocation_accuracy": 0.95,
        "selection_accuracy": 0.90,
        "sequence_metrics": {
            "edit_distance": 1,
            "sequence_accuracy": 0.85,
        },
        "argument_metrics": {
            "precision": 0.92,
            "recall": 0.88,
            "f1": 0.90,
        },
        "efficiency_metrics": {
            "redundant_count": 1,
            "redundant_rate": 0.33,
            "total_calls": 3,
        },
    }
    return result


@pytest.fixture
def result_with_side_effects(sample_result):
    """Create result with side effects."""
    sample_result.metrics["side_effect_metrics"] = {
        "success_rate": 0.75,
        "total_checks": 4,
        "successful_checks": 3,
    }
    return sample_result


@pytest.fixture
def result_with_performance(sample_result):
    """Create result with performance metrics."""
    sample_result.metrics["latency_metrics"] = {
        "total_duration": 2.5,
        "average_duration": 0.83,
        "max_duration": 1.2,
        "min_duration": 0.5,
    }
    sample_result.metrics["cost_metrics"] = {
        "total_cost": 0.0025,
        "average_cost": 0.00083,
        "cost_by_tool": {
            "tool1": 0.001,
            "tool2": 0.0015,
        },
    }
    return sample_result


class TestJSONReport:
    """Tests for JSON report generation."""

    def test_generate_basic_json_report(self, tmp_path, sample_result):
        """Test generating basic JSON report."""
        output_path = tmp_path / "report.json"
        result_path = generate_json_report(sample_result, output_path)

        assert result_path.exists()
        assert result_path == output_path

        # Load and verify contents
        with output_path.open() as f:
            report = json.load(f)

        assert "timestamp" in report
        assert "summary" in report
        assert "metrics" in report
        assert "gold_calls" in report
        assert "trace_calls" in report

    def test_json_report_summary(self, tmp_path, sample_result):
        """Test JSON report summary section."""
        output_path = tmp_path / "report.json"
        generate_json_report(sample_result, output_path)

        with output_path.open() as f:
            report = json.load(f)

        assert report["summary"]["gold_calls_count"] == 2
        assert report["summary"]["trace_calls_count"] == 3

    def test_json_report_metrics(self, tmp_path, sample_result):
        """Test JSON report metrics section."""
        output_path = tmp_path / "report.json"
        generate_json_report(sample_result, output_path)

        with output_path.open() as f:
            report = json.load(f)

        assert report["metrics"]["invocation_accuracy"] == 0.95
        assert report["metrics"]["selection_accuracy"] == 0.90
        assert report["metrics"]["sequence_metrics"]["edit_distance"] == 1

    def test_json_report_calls(self, tmp_path, sample_result):
        """Test JSON report calls section."""
        output_path = tmp_path / "report.json"
        generate_json_report(sample_result, output_path)

        with output_path.open() as f:
            report = json.load(f)

        assert len(report["gold_calls"]) == 2
        assert len(report["trace_calls"]) == 3
        assert report["gold_calls"][0]["tool"] == "tool1"
        assert report["gold_calls"][0]["args"] == {"x": 1}

    def test_json_report_timestamp(self, tmp_path, sample_result):
        """Test JSON report has valid timestamp."""
        output_path = tmp_path / "report.json"
        generate_json_report(sample_result, output_path)

        with output_path.open() as f:
            report = json.load(f)

        # Verify timestamp is valid ISO format
        timestamp = datetime.fromisoformat(report["timestamp"])
        assert isinstance(timestamp, datetime)

    def test_json_report_default_path(self, sample_result, tmp_path, monkeypatch):
        """Test JSON report with default output path."""
        # Change to tmp directory
        monkeypatch.chdir(tmp_path)

        result_path = generate_json_report(sample_result)

        assert result_path.name == "toolscore.json"
        assert result_path.exists()


class TestHTMLReport:
    """Tests for HTML report generation."""

    def test_generate_basic_html_report(self, tmp_path, sample_result):
        """Test generating basic HTML report."""
        output_path = tmp_path / "report.html"
        result_path = generate_html_report(sample_result, output_path)

        assert result_path.exists()
        assert result_path == output_path

        # Verify it's valid HTML
        content = output_path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content

    def test_html_report_title(self, tmp_path, sample_result):
        """Test HTML report has title."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_result, output_path)

        content = output_path.read_text()
        assert "Toolscore Evaluation Report" in content

    def test_html_report_summary(self, tmp_path, sample_result):
        """Test HTML report summary section."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_result, output_path)

        content = output_path.read_text()
        assert "Summary" in content
        assert "Expected Calls" in content
        assert "Actual Calls" in content

    def test_html_report_core_metrics(self, tmp_path, sample_result):
        """Test HTML report core metrics."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_result, output_path)

        content = output_path.read_text()
        assert "Core Metrics" in content
        assert "Invocation Accuracy" in content
        assert "Selection Accuracy" in content
        assert "Sequence Accuracy" in content
        assert "Argument F1 Score" in content
        assert "Redundant Call Rate" in content

    def test_html_report_with_side_effects(self, tmp_path, result_with_side_effects):
        """Test HTML report with side effects."""
        output_path = tmp_path / "report.html"
        generate_html_report(result_with_side_effects, output_path)

        content = output_path.read_text()
        assert "Side-Effect Success" in content

    def test_html_report_with_performance(self, tmp_path, result_with_performance):
        """Test HTML report with performance metrics."""
        output_path = tmp_path / "report.html"
        generate_html_report(result_with_performance, output_path)

        content = output_path.read_text()
        assert "Performance Metrics" in content
        assert "Total Duration" in content
        assert "Total Cost" in content

    def test_html_report_timestamp(self, tmp_path, sample_result):
        """Test HTML report has timestamp."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_result, output_path)

        content = output_path.read_text()
        assert "Generated:" in content

    def test_html_report_metric_values(self, tmp_path, sample_result):
        """Test HTML report shows metric values."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_result, output_path)

        content = output_path.read_text()
        assert "95.0%" in content  # invocation_accuracy
        assert "90.0%" in content  # selection_accuracy
        assert "85.0%" in content  # sequence_accuracy

    def test_html_report_color_coding_good(self, tmp_path):
        """Test HTML report color codes good metrics."""
        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="tool1")]
        result.trace_calls = [ToolCall(tool="tool1")]
        result.metrics = {
            "invocation_accuracy": 0.95,
            "selection_accuracy": 0.90,
            "sequence_metrics": {"sequence_accuracy": 0.85},
            "argument_metrics": {"f1": 0.82},
            "efficiency_metrics": {"redundant_rate": 0.15},
        }

        output_path = tmp_path / "report.html"
        generate_html_report(result, output_path)

        content = output_path.read_text()
        assert "good" in content

    def test_html_report_color_coding_warning(self, tmp_path):
        """Test HTML report color codes warning metrics."""
        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="tool1")]
        result.trace_calls = [ToolCall(tool="tool1")]
        result.metrics = {
            "invocation_accuracy": 0.65,
            "selection_accuracy": 0.60,
            "sequence_metrics": {"sequence_accuracy": 0.55},
            "argument_metrics": {"f1": 0.62},
            "efficiency_metrics": {"redundant_rate": 0.35},
        }

        output_path = tmp_path / "report.html"
        generate_html_report(result, output_path)

        content = output_path.read_text()
        assert "warning" in content

    def test_html_report_color_coding_bad(self, tmp_path):
        """Test HTML report color codes bad metrics."""
        result = EvaluationResult()
        result.gold_calls = [ToolCall(tool="tool1")]
        result.trace_calls = [ToolCall(tool="tool1")]
        result.metrics = {
            "invocation_accuracy": 0.25,
            "selection_accuracy": 0.30,
            "sequence_metrics": {"sequence_accuracy": 0.20},
            "argument_metrics": {"f1": 0.15},
            "efficiency_metrics": {"redundant_rate": 0.75},
        }

        output_path = tmp_path / "report.html"
        generate_html_report(result, output_path)

        content = output_path.read_text()
        assert "bad" in content

    def test_html_report_default_path(self, sample_result, tmp_path, monkeypatch):
        """Test HTML report with default output path."""
        monkeypatch.chdir(tmp_path)

        result_path = generate_html_report(sample_result)

        assert result_path.name == "toolscore.html"
        assert result_path.exists()

    def test_html_report_css_styling(self, tmp_path, sample_result):
        """Test HTML report includes CSS styling."""
        output_path = tmp_path / "report.html"
        generate_html_report(sample_result, output_path)

        content = output_path.read_text()
        assert "<style>" in content
        assert "</style>" in content
        assert "font-family" in content
        assert "color" in content


class TestCSVReport:
    """Tests for CSV report generation."""

    def test_generate_basic_csv_report(self, sample_result, tmp_path):
        """Test generating a basic CSV report."""
        output_path = tmp_path / "report.csv"
        result_path = generate_csv_report(sample_result, output_path)

        assert result_path == output_path
        assert output_path.exists()

    def test_csv_report_header(self, sample_result, tmp_path):
        """Test CSV report contains proper headers."""
        output_path = tmp_path / "report.csv"
        generate_csv_report(sample_result, output_path)

        content = output_path.read_text()
        assert "Category,Metric,Value" in content

    def test_csv_report_summary_data(self, sample_result, tmp_path):
        """Test CSV report includes summary data."""
        output_path = tmp_path / "report.csv"
        generate_csv_report(sample_result, output_path)

        content = output_path.read_text()
        assert "Summary,Gold Calls Count,2" in content
        assert "Summary,Trace Calls Count,3" in content

    def test_csv_report_metrics(self, sample_result, tmp_path):
        """Test CSV report includes metrics."""
        output_path = tmp_path / "report.csv"
        generate_csv_report(sample_result, output_path)

        content = output_path.read_text()
        # Should include accuracy metrics formatted as percentages
        assert "invocation_accuracy" in content
        assert "selection_accuracy" in content
        assert "95.00%" in content or "90.00%" in content

    def test_csv_report_nested_metrics(self, sample_result, tmp_path):
        """Test CSV report flattens nested metrics."""
        output_path = tmp_path / "report.csv"
        generate_csv_report(sample_result, output_path)

        content = output_path.read_text()
        # Check that nested metrics are included
        assert "sequence_metrics" in content or "edit_distance" in content
        assert "argument_metrics" in content or "precision" in content

    def test_csv_report_percentage_formatting(self, sample_result, tmp_path):
        """Test CSV report formats percentages correctly."""
        output_path = tmp_path / "report.csv"
        generate_csv_report(sample_result, output_path)

        content = output_path.read_text()
        # Accuracy metrics should be formatted as percentages
        lines = content.split("\n")
        percentage_lines = [l for l in lines if "%" in l]
        assert len(percentage_lines) > 0

    def test_csv_report_default_path(self, sample_result, tmp_path, monkeypatch):
        """Test CSV report with default output path."""
        monkeypatch.chdir(tmp_path)

        result_path = generate_csv_report(sample_result)

        assert result_path.name == "toolscore.csv"
        assert result_path.exists()

    def test_csv_report_readable_format(self, sample_result, tmp_path):
        """Test CSV report is properly formatted for Excel/Sheets."""
        output_path = tmp_path / "report.csv"
        generate_csv_report(sample_result, output_path)

        # Verify it's valid CSV by reading it
        import csv

        with output_path.open("r") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Should have multiple rows
        assert len(rows) > 5
        # First row should be header
        assert rows[0] == ["Category", "Metric", "Value"]


class TestMarkdownReport:
    """Tests for Markdown report generation."""

    def test_generate_basic_markdown_report(self, sample_result, tmp_path):
        """Test generating a basic Markdown report."""
        output_path = tmp_path / "report.md"
        result_path = generate_markdown_report(sample_result, output_path)

        assert result_path == output_path
        assert output_path.exists()

    def test_markdown_report_title(self, sample_result, tmp_path):
        """Test Markdown report includes title."""
        output_path = tmp_path / "report.md"
        generate_markdown_report(sample_result, output_path)

        content = output_path.read_text()
        assert "# Toolscore Evaluation Report" in content

    def test_markdown_report_summary(self, sample_result, tmp_path):
        """Test Markdown report includes summary section."""
        output_path = tmp_path / "report.md"
        generate_markdown_report(sample_result, output_path)

        content = output_path.read_text()
        assert "Summary" in content
        assert "Gold Standard Calls:** 2" in content
        assert "Actual Trace Calls:** 3" in content

    def test_markdown_report_metrics_table(self, sample_result, tmp_path):
        """Test Markdown report includes metrics table."""
        output_path = tmp_path / "report.md"
        generate_markdown_report(sample_result, output_path)

        content = output_path.read_text()
        assert "Key Metrics" in content
        assert "| Metric | Value | Status |" in content
        assert "|--------|-------|--------|" in content

    def test_markdown_report_status_indicators(self, sample_result, tmp_path):
        """Test Markdown report includes status indicators."""
        output_path = tmp_path / "report.md"
        generate_markdown_report(sample_result, output_path)

        content = output_path.read_text()
        # Should include status text
        assert "Excellent" in content or "Good" in content or "Fair" in content

    def test_markdown_report_efficiency_metrics(self, sample_result, tmp_path):
        """Test Markdown report includes efficiency metrics."""
        output_path = tmp_path / "report.md"
        generate_markdown_report(sample_result, output_path)

        content = output_path.read_text()
        assert "Efficiency Metrics" in content
        assert "Redundant Call Rate" in content

    def test_markdown_report_collapsible_details(self, sample_result, tmp_path):
        """Test Markdown report includes collapsible details section."""
        output_path = tmp_path / "report.md"
        generate_markdown_report(sample_result, output_path)

        content = output_path.read_text()
        assert "<details>" in content
        assert "</details>" in content
        assert "Click to expand" in content

    def test_markdown_report_footer(self, sample_result, tmp_path):
        """Test Markdown report includes footer."""
        output_path = tmp_path / "report.md"
        generate_markdown_report(sample_result, output_path)

        content = output_path.read_text()
        assert "Generated with [Toolscore]" in content

    def test_markdown_report_timestamp(self, sample_result, tmp_path):
        """Test Markdown report includes timestamp."""
        output_path = tmp_path / "report.md"
        generate_markdown_report(sample_result, output_path)

        content = output_path.read_text()
        assert "**Generated:**" in content
        # Should contain current year
        assert str(datetime.now().year) in content

    def test_markdown_report_default_path(self, sample_result, tmp_path, monkeypatch):
        """Test Markdown report with default output path."""
        monkeypatch.chdir(tmp_path)

        result_path = generate_markdown_report(sample_result)

        assert result_path.name == "toolscore.md"
        assert result_path.exists()

    def test_markdown_report_with_semantic_metrics(self, sample_result, tmp_path):
        """Test Markdown report with semantic metrics."""
        sample_result.metrics["semantic_metrics"] = {
            "semantic_score": 0.92,
            "semantic_matches": 5,
        }

        output_path = tmp_path / "report.md"
        generate_markdown_report(sample_result, output_path)

        content = output_path.read_text()
        assert "Semantic Evaluation" in content
        assert "Semantic Score" in content

    def test_markdown_report_with_side_effects(self, result_with_side_effects, tmp_path):
        """Test Markdown report with side effect metrics."""
        result_with_side_effects.metrics["side_effect_metrics"] = {
            "success_rate": 1.0,
            "validated_count": 3,
        }

        output_path = tmp_path / "report.md"
        generate_markdown_report(result_with_side_effects, output_path)

        content = output_path.read_text()
        assert "Side Effects" in content
        assert "Success Rate" in content

    def test_markdown_report_percentage_formatting(self, sample_result, tmp_path):
        """Test Markdown report formats percentages correctly."""
        output_path = tmp_path / "report.md"
        generate_markdown_report(sample_result, output_path)

        content = output_path.read_text()
        # Should have percentages with 2 decimal places
        assert "95.00%" in content or "90.00%" in content or "85.00%" in content
