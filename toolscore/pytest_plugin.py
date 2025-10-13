"""Pytest plugin for Toolscore integration.

This plugin allows you to use Toolscore evaluations directly in your pytest test suite.

Example:
    def test_agent_performance(toolscore_eval):
        result = toolscore_eval("gold_calls.json", "trace.json")
        assert result.metrics['invocation_accuracy'] >= 0.9
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from toolscore.core import EvaluationResult, evaluate_trace


def pytest_addoption(parser: Any) -> None:
    """Add Toolscore-specific command line options to pytest.

    Args:
        parser: Pytest parser object
    """
    group = parser.getgroup("toolscore", "LLM tool usage evaluation")

    group.addoption(
        "--toolscore-gold-dir",
        action="store",
        default="tests/gold_standards",
        help="Directory containing gold standard files (default: tests/gold_standards)",
    )

    group.addoption(
        "--toolscore-trace-dir",
        action="store",
        default="tests/traces",
        help="Directory containing trace files (default: tests/traces)",
    )

    group.addoption(
        "--toolscore-min-accuracy",
        action="store",
        type=float,
        default=0.8,
        help="Minimum required accuracy for tests (default: 0.8)",
    )


def pytest_configure(config: Any) -> None:
    """Register Toolscore markers.

    Args:
        config: Pytest config object
    """
    config.addinivalue_line(
        "markers",
        "toolscore: mark test as a Toolscore evaluation test",
    )
    config.addinivalue_line(
        "markers",
        "min_accuracy(score): require minimum accuracy score for test",
    )


@pytest.fixture
def toolscore_gold_dir(request: Any) -> Path:
    """Get the gold standards directory from config.

    Args:
        request: Pytest request object

    Returns:
        Path to gold standards directory
    """
    return Path(request.config.getoption("--toolscore-gold-dir"))


@pytest.fixture
def toolscore_trace_dir(request: Any) -> Path:
    """Get the traces directory from config.

    Args:
        request: Pytest request object

    Returns:
        Path to traces directory
    """
    return Path(request.config.getoption("--toolscore-trace-dir"))


@pytest.fixture
def toolscore_min_accuracy(request: Any) -> float:
    """Get the minimum required accuracy from config.

    Args:
        request: Pytest request object

    Returns:
        Minimum accuracy threshold
    """
    return float(request.config.getoption("--toolscore-min-accuracy"))


@pytest.fixture
def toolscore_eval(
    toolscore_gold_dir: Path,
    toolscore_trace_dir: Path,
) -> Any:
    """Fixture for evaluating traces against gold standards.

    This fixture provides a convenient function for running evaluations
    in pytest tests. It automatically resolves file paths relative to
    the configured directories.

    Args:
        toolscore_gold_dir: Path to gold standards directory
        toolscore_trace_dir: Path to traces directory

    Returns:
        Function that evaluates a trace against a gold standard

    Example:
        def test_my_agent(toolscore_eval):
            result = toolscore_eval("my_gold.json", "my_trace.json")
            assert result.metrics['invocation_accuracy'] >= 0.9
    """

    def evaluate(
        gold_file: str | Path,
        trace_file: str | Path,
        format: str = "auto",
        validate_side_effects: bool = True,
    ) -> EvaluationResult:
        """Evaluate a trace against a gold standard.

        Args:
            gold_file: Gold standard filename or path
            trace_file: Trace filename or path
            format: Trace format (auto, openai, anthropic, custom)
            validate_side_effects: Whether to validate side effects

        Returns:
            EvaluationResult object with metrics

        Raises:
            FileNotFoundError: If files don't exist
            ValueError: If files are invalid
        """
        # Resolve paths
        gold_path = Path(gold_file)
        if not gold_path.is_absolute():
            gold_path = toolscore_gold_dir / gold_path

        trace_path = Path(trace_file)
        if not trace_path.is_absolute():
            trace_path = toolscore_trace_dir / trace_path

        # Run evaluation
        return evaluate_trace(
            gold_file=gold_path,
            trace_file=trace_path,
            format=format,
            validate_side_effects=validate_side_effects,
        )

    return evaluate


class ToolscoreAssertions:
    """Helper class for Toolscore-specific assertions."""

    @staticmethod
    def assert_invocation_accuracy(
        result: EvaluationResult,
        min_accuracy: float,
        msg: str | None = None,
    ) -> None:
        """Assert that invocation accuracy meets minimum threshold.

        Args:
            result: Evaluation result
            min_accuracy: Minimum required accuracy (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If accuracy is below threshold
        """
        accuracy = result.metrics["invocation_accuracy"]
        if msg is None:
            msg = f"Invocation accuracy {accuracy:.1%} below minimum {min_accuracy:.1%}"
        assert accuracy >= min_accuracy, msg

    @staticmethod
    def assert_selection_accuracy(
        result: EvaluationResult,
        min_accuracy: float,
        msg: str | None = None,
    ) -> None:
        """Assert that selection accuracy meets minimum threshold.

        Args:
            result: Evaluation result
            min_accuracy: Minimum required accuracy (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If accuracy is below threshold
        """
        accuracy = result.metrics["selection_accuracy"]
        if msg is None:
            msg = f"Selection accuracy {accuracy:.1%} below minimum {min_accuracy:.1%}"
        assert accuracy >= min_accuracy, msg

    @staticmethod
    def assert_sequence_accuracy(
        result: EvaluationResult,
        min_accuracy: float,
        msg: str | None = None,
    ) -> None:
        """Assert that sequence accuracy meets minimum threshold.

        Args:
            result: Evaluation result
            min_accuracy: Minimum required accuracy (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If accuracy is below threshold
        """
        accuracy = result.metrics["sequence_metrics"]["sequence_accuracy"]
        if msg is None:
            msg = f"Sequence accuracy {accuracy:.1%} below minimum {min_accuracy:.1%}"
        assert accuracy >= min_accuracy, msg

    @staticmethod
    def assert_argument_f1(
        result: EvaluationResult,
        min_f1: float,
        msg: str | None = None,
    ) -> None:
        """Assert that argument F1 score meets minimum threshold.

        Args:
            result: Evaluation result
            min_f1: Minimum required F1 score (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If F1 score is below threshold
        """
        f1 = result.metrics["argument_metrics"]["f1"]
        if msg is None:
            msg = f"Argument F1 score {f1:.1%} below minimum {min_f1:.1%}"
        assert f1 >= min_f1, msg

    @staticmethod
    def assert_redundancy_below(
        result: EvaluationResult,
        max_rate: float,
        msg: str | None = None,
    ) -> None:
        """Assert that redundant call rate is below maximum threshold.

        Args:
            result: Evaluation result
            max_rate: Maximum allowed redundancy rate (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If redundancy rate exceeds threshold
        """
        rate = result.metrics["efficiency_metrics"]["redundant_rate"]
        if msg is None:
            msg = f"Redundant call rate {rate:.1%} exceeds maximum {max_rate:.1%}"
        assert rate <= max_rate, msg

    @staticmethod
    def assert_all_metrics_above(
        result: EvaluationResult,
        min_accuracy: float,
        msg: str | None = None,
    ) -> None:
        """Assert that all core metrics meet minimum threshold.

        Args:
            result: Evaluation result
            min_accuracy: Minimum required accuracy (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If any metric is below threshold
        """
        metrics_to_check = [
            ("invocation_accuracy", result.metrics["invocation_accuracy"]),
            ("selection_accuracy", result.metrics["selection_accuracy"]),
            (
                "sequence_accuracy",
                result.metrics["sequence_metrics"]["sequence_accuracy"],
            ),
            ("argument_f1", result.metrics["argument_metrics"]["f1"]),
        ]

        failures = [
            (name, value)
            for name, value in metrics_to_check
            if value < min_accuracy
        ]

        if failures:
            if msg is None:
                failure_str = ", ".join(
                    f"{name}={value:.1%}" for name, value in failures
                )
                msg = f"Metrics below {min_accuracy:.1%}: {failure_str}"
            raise AssertionError(msg)


@pytest.fixture
def toolscore_assert() -> ToolscoreAssertions:
    """Fixture providing Toolscore-specific assertion helpers.

    Returns:
        ToolscoreAssertions instance

    Example:
        def test_agent(toolscore_eval, toolscore_assert):
            result = toolscore_eval("gold.json", "trace.json")
            toolscore_assert.assert_invocation_accuracy(result, 0.9)
            toolscore_assert.assert_selection_accuracy(result, 0.9)
    """
    return ToolscoreAssertions()
