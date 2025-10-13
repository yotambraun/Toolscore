"""Unit tests for CLI commands."""

import json

import pytest
from click.testing import CliRunner

from toolscore.cli import main


@pytest.fixture
def runner():
    """Create CLI runner."""
    return CliRunner()


@pytest.fixture
def temp_files(tmp_path):
    """Create temporary test files."""
    # Create gold standard file
    gold_file = tmp_path / "gold.json"
    gold_data = [
        {
            "tool": "test_tool",
            "args": {"x": 1, "y": 2},
            "description": "Test tool call",
        }
    ]
    with gold_file.open("w") as f:
        json.dump(gold_data, f)

    # Create trace file (OpenAI format)
    trace_file = tmp_path / "trace.json"
    trace_data = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "type": "function",
                    "id": "call_123",
                    "function": {
                        "name": "test_tool",
                        "arguments": '{"x": 1, "y": 2}',
                    },
                }
            ],
        }
    ]
    with trace_file.open("w") as f:
        json.dump(trace_data, f)

    return {"gold": gold_file, "trace": trace_file, "dir": tmp_path}


class TestEvalCommand:
    """Tests for eval command."""

    def test_eval_basic(self, runner, temp_files):
        """Test basic evaluation."""
        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--format",
                "openai",
            ],
        )

        assert result.exit_code == 0
        assert "Invocation Accuracy" in result.output
        assert "Selection Accuracy" in result.output

    def test_eval_with_html_output(self, runner, temp_files):
        """Test evaluation with HTML output."""
        html_file = temp_files["dir"] / "report.html"

        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--html",
                str(html_file),
            ],
        )

        assert result.exit_code == 0
        assert html_file.exists()
        assert "HTML report:" in result.output

    def test_eval_with_json_output(self, runner, temp_files):
        """Test evaluation with custom JSON output path."""
        json_file = temp_files["dir"] / "custom_report.json"

        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--output",
                str(json_file),
            ],
        )

        assert result.exit_code == 0
        assert json_file.exists()
        assert "JSON report:" in result.output

    def test_eval_verbose(self, runner, temp_files):
        """Test evaluation with verbose output."""
        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--verbose",
            ],
        )

        assert result.exit_code == 0
        assert "Loading gold standard from" in result.output
        assert "Loading trace from" in result.output

    def test_eval_no_side_effects(self, runner, temp_files):
        """Test evaluation with side effects disabled."""
        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--no-side-effects",
            ],
        )

        assert result.exit_code == 0
        # Should not have side-effect metrics in output
        assert "Side-Effect" not in result.output

    def test_eval_missing_gold_file(self, runner, temp_files):
        """Test evaluation with missing gold file."""
        result = runner.invoke(
            main,
            [
                "eval",
                "/nonexistent/gold.json",
                str(temp_files["trace"]),
            ],
        )

        assert result.exit_code == 2  # Click file validation error
        assert "does not exist" in result.output.lower() or "error" in result.output.lower()

    def test_eval_missing_trace_file(self, runner, temp_files):
        """Test evaluation with missing trace file."""
        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                "/nonexistent/trace.json",
            ],
        )

        assert result.exit_code == 2  # Click file validation error
        assert "does not exist" in result.output.lower() or "error" in result.output.lower()

    def test_eval_auto_format_detection(self, runner, temp_files):
        """Test auto format detection."""
        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--format",
                "auto",
            ],
        )

        assert result.exit_code == 0
        assert "Invocation Accuracy" in result.output


class TestValidateCommand:
    """Tests for validate command."""

    def test_validate_valid_trace(self, runner, temp_files):
        """Test validation of valid trace file."""
        result = runner.invoke(
            main,
            ["validate", str(temp_files["trace"]), "--format", "openai"],
        )

        assert result.exit_code == 0
        assert "Valid trace file" in result.output
        assert "Total calls:" in result.output

    def test_validate_with_details(self, runner, temp_files):
        """Test validation shows first call details."""
        result = runner.invoke(
            main,
            ["validate", str(temp_files["trace"])],
        )

        assert result.exit_code == 0
        assert "Total calls:" in result.output
        assert "First tool:" in result.output
        assert "First args:" in result.output

    def test_validate_invalid_file(self, runner, tmp_path):
        """Test validation of invalid trace file."""
        invalid_file = tmp_path / "invalid.json"
        with invalid_file.open("w") as f:
            f.write("not valid json{")

        result = runner.invoke(
            main,
            ["validate", str(invalid_file)],
        )

        assert result.exit_code == 1
        assert "Invalid trace file" in result.output

    def test_validate_missing_file(self, runner):
        """Test validation of missing file."""
        result = runner.invoke(
            main,
            ["validate", "/nonexistent/trace.json"],
        )

        assert result.exit_code == 2  # Click error for missing file


class TestMainCommand:
    """Tests for main command group."""

    def test_version_option(self, runner):
        """Test --version option."""
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "toolscore" in result.output.lower()

    def test_help_option(self, runner):
        """Test --help option."""
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "Toolscore" in result.output
        assert "eval" in result.output
        assert "validate" in result.output

    def test_eval_help(self, runner):
        """Test eval command help."""
        result = runner.invoke(main, ["eval", "--help"])

        assert result.exit_code == 0
        assert "GOLD_FILE" in result.output
        assert "TRACE_FILE" in result.output
        assert "--format" in result.output
        assert "--html" in result.output
