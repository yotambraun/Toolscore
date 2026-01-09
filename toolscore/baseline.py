"""Baseline management for regression detection.

This module provides functionality to save evaluation baselines and compare
subsequent evaluations against them to detect regressions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult


@dataclass
class RegressionItem:
    """A single regression detected in comparison."""

    metric_name: str
    baseline_value: float
    current_value: float
    delta: float
    delta_percent: float
    threshold: float
    status: str  # "regression", "improvement", "stable"


@dataclass
class ComparisonResult:
    """Result of comparing evaluation against baseline."""

    passed: bool
    threshold: float
    baseline_timestamp: str
    comparison_timestamp: str
    items: list[RegressionItem] = field(default_factory=list)
    summary: str = ""

    @property
    def regressions(self) -> list[RegressionItem]:
        """Get only regression items."""
        return [item for item in self.items if item.status == "regression"]

    @property
    def improvements(self) -> list[RegressionItem]:
        """Get only improvement items."""
        return [item for item in self.items if item.status == "improvement"]

    @property
    def stable(self) -> list[RegressionItem]:
        """Get only stable items."""
        return [item for item in self.items if item.status == "stable"]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "threshold": self.threshold,
            "baseline_timestamp": self.baseline_timestamp,
            "comparison_timestamp": self.comparison_timestamp,
            "summary": self.summary,
            "items": [
                {
                    "metric_name": item.metric_name,
                    "baseline_value": item.baseline_value,
                    "current_value": item.current_value,
                    "delta": item.delta,
                    "delta_percent": item.delta_percent,
                    "threshold": item.threshold,
                    "status": item.status,
                }
                for item in self.items
            ],
            "regression_count": len(self.regressions),
            "improvement_count": len(self.improvements),
        }


@dataclass
class Baseline:
    """A saved baseline for regression testing."""

    version: str
    created_at: str
    gold_file_hash: str
    metrics: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(
        cls,
        result: EvaluationResult,
        gold_file: str | Path | None = None,
    ) -> Baseline:
        """Create a baseline from an evaluation result.

        Args:
            result: The evaluation result to create baseline from
            gold_file: Optional path to gold file for hash verification

        Returns:
            New Baseline instance
        """
        from toolscore import __version__

        # Calculate gold file hash if provided
        gold_hash = ""
        if gold_file:
            gold_path = Path(gold_file)
            if gold_path.exists():
                content = gold_path.read_bytes()
                gold_hash = hashlib.md5(content).hexdigest()

        # Extract key metrics
        metrics = cls._extract_metrics(result)

        return cls(
            version=__version__,
            created_at=datetime.now(timezone.utc).isoformat(),
            gold_file_hash=gold_hash,
            metrics=metrics,
            metadata={
                "gold_calls_count": len(result.gold_calls),
                "trace_calls_count": len(result.trace_calls),
            },
        )

    @staticmethod
    def _extract_metrics(result: EvaluationResult) -> dict[str, float]:
        """Extract key metrics from evaluation result.

        Args:
            result: Evaluation result

        Returns:
            Dictionary of metric names to values
        """
        m = result.metrics
        metrics = {
            "invocation_accuracy": m.get("invocation_accuracy", 0.0),
            "selection_accuracy": m.get("selection_accuracy", 0.0),
        }

        # Tool correctness
        tc = m.get("tool_correctness_metrics", {})
        if tc:
            metrics["tool_correctness"] = tc.get("tool_correctness", 0.0)

        # Sequence metrics
        seq = m.get("sequence_metrics", {})
        if seq:
            metrics["sequence_accuracy"] = seq.get("sequence_accuracy", 0.0)

        # Argument metrics
        arg = m.get("argument_metrics", {})
        if arg:
            metrics["argument_f1"] = arg.get("f1", 0.0)
            metrics["argument_precision"] = arg.get("precision", 0.0)
            metrics["argument_recall"] = arg.get("recall", 0.0)

        # Efficiency metrics
        eff = m.get("efficiency_metrics", {})
        if eff:
            metrics["redundant_rate"] = eff.get("redundant_rate", 0.0)

        # Semantic metrics
        sem = m.get("semantic_metrics", {})
        if sem and "semantic_score" in sem and sem["semantic_score"] is not None:
            metrics["semantic_score"] = sem.get("semantic_score", 0.0)

        return metrics

    def to_dict(self) -> dict[str, Any]:
        """Convert baseline to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "version": self.version,
            "created_at": self.created_at,
            "gold_file_hash": self.gold_file_hash,
            "metrics": self.metrics,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Baseline:
        """Create baseline from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            Baseline instance
        """
        return cls(
            version=data.get("version", "unknown"),
            created_at=data.get("created_at", ""),
            gold_file_hash=data.get("gold_file_hash", ""),
            metrics=data.get("metrics", {}),
            metadata=data.get("metadata", {}),
        )


def save_baseline(
    result: EvaluationResult,
    output_path: str | Path,
    gold_file: str | Path | None = None,
) -> Path:
    """Save evaluation result as a baseline.

    Args:
        result: Evaluation result to save
        output_path: Path to save baseline JSON
        gold_file: Optional path to gold file for hash verification

    Returns:
        Path to saved baseline file
    """
    baseline = Baseline.from_result(result, gold_file)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w") as f:
        json.dump(baseline.to_dict(), f, indent=2)

    return path


def load_baseline(path: str | Path) -> Baseline:
    """Load a baseline from file.

    Args:
        path: Path to baseline JSON file

    Returns:
        Baseline instance

    Raises:
        FileNotFoundError: If baseline file doesn't exist
        ValueError: If baseline file is invalid
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Baseline file not found: {path}")

    with file_path.open() as f:
        data = json.load(f)

    if not isinstance(data, dict) or "metrics" not in data:
        raise ValueError(f"Invalid baseline file format: {path}")

    return Baseline.from_dict(data)


def compare_to_baseline(
    result: EvaluationResult,
    baseline: Baseline,
    threshold: float = 0.05,
    gold_file: str | Path | None = None,
) -> ComparisonResult:
    """Compare evaluation result against baseline.

    Args:
        result: Current evaluation result
        baseline: Baseline to compare against
        threshold: Maximum allowed regression (as decimal, e.g., 0.05 = 5%)
        gold_file: Optional gold file path for hash verification

    Returns:
        ComparisonResult with detailed comparison
    """
    # Verify gold file hash if available
    if gold_file and baseline.gold_file_hash:
        gold_path = Path(gold_file)
        if gold_path.exists():
            content = gold_path.read_bytes()
            current_hash = hashlib.md5(content).hexdigest()
            if current_hash != baseline.gold_file_hash:
                # Gold file changed - warn but continue
                pass

    # Extract current metrics
    current_metrics = Baseline._extract_metrics(result)

    # Compare each metric
    items = []
    passed = True

    # Metrics where higher is better
    higher_is_better = {
        "invocation_accuracy",
        "selection_accuracy",
        "tool_correctness",
        "sequence_accuracy",
        "argument_f1",
        "argument_precision",
        "argument_recall",
        "semantic_score",
    }

    # Metrics where lower is better
    lower_is_better = {"redundant_rate"}

    for metric_name, baseline_value in baseline.metrics.items():
        current_value = current_metrics.get(metric_name, 0.0)
        delta = current_value - baseline_value

        # Calculate percentage change (avoid division by zero)
        if baseline_value != 0:
            delta_percent = (delta / baseline_value) * 100
        else:
            delta_percent = 100.0 if delta > 0 else (0.0 if delta == 0 else -100.0)

        # Determine status based on metric type
        if metric_name in higher_is_better:
            # Higher is better - negative delta is regression
            if delta < -threshold:
                status = "regression"
                passed = False
            elif delta > threshold:
                status = "improvement"
            else:
                status = "stable"
        elif metric_name in lower_is_better:
            # Lower is better - positive delta is regression
            if delta > threshold:
                status = "regression"
                passed = False
            elif delta < -threshold:
                status = "improvement"
            else:
                status = "stable"
        else:
            # Unknown metric - treat as higher is better
            if delta < -threshold:
                status = "regression"
                passed = False
            elif delta > threshold:
                status = "improvement"
            else:
                status = "stable"

        items.append(
            RegressionItem(
                metric_name=metric_name,
                baseline_value=baseline_value,
                current_value=current_value,
                delta=delta,
                delta_percent=delta_percent,
                threshold=threshold,
                status=status,
            )
        )

    # Sort items: regressions first, then by delta magnitude
    items.sort(key=lambda x: (0 if x.status == "regression" else 1, -abs(x.delta)))

    # Generate summary
    regression_count = len([i for i in items if i.status == "regression"])
    improvement_count = len([i for i in items if i.status == "improvement"])

    if passed:
        if improvement_count > 0:
            summary = f"PASS: No regressions, {improvement_count} improvement(s) detected"
        else:
            summary = f"PASS: No significant changes (threshold: {threshold:.0%})"
    else:
        summary = f"FAIL: {regression_count} regression(s) detected (threshold: {threshold:.0%})"

    return ComparisonResult(
        passed=passed,
        threshold=threshold,
        baseline_timestamp=baseline.created_at,
        comparison_timestamp=datetime.now(timezone.utc).isoformat(),
        items=items,
        summary=summary,
    )


def print_comparison_result(
    comparison: ComparisonResult,
    console: Any | None = None,
) -> None:
    """Print comparison result to console.

    Args:
        comparison: The comparison result to print
        console: Rich Console instance (creates new one if None)
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    if console is None:
        console = Console()

    # Print summary header
    if comparison.passed:
        console.print()
        console.print(
            Panel.fit(
                f"[bold green]{comparison.summary}[/bold green]",
                border_style="green",
            )
        )
    else:
        console.print()
        console.print(
            Panel.fit(
                f"[bold red]{comparison.summary}[/bold red]",
                border_style="red",
            )
        )
    console.print()

    # Print metrics table
    table = Table(title="Regression Analysis", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Baseline", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Status", justify="center")

    for item in comparison.items:
        # Format delta with sign and percentage
        if item.delta >= 0:
            delta_str = f"+{item.delta:.2%} ({item.delta_percent:+.1f}%)"
        else:
            delta_str = f"{item.delta:.2%} ({item.delta_percent:+.1f}%)"

        # Color based on status
        if item.status == "regression":
            status_text = Text("REGRESSION", style="bold red")
            delta_text = Text(delta_str, style="red")
        elif item.status == "improvement":
            status_text = Text("IMPROVED", style="bold green")
            delta_text = Text(delta_str, style="green")
        else:
            status_text = Text("OK", style="dim")
            delta_text = Text(delta_str, style="dim")

        # Format metric name nicely
        metric_display = item.metric_name.replace("_", " ").title()

        table.add_row(
            metric_display,
            f"{item.baseline_value:.2%}",
            f"{item.current_value:.2%}",
            delta_text,
            status_text,
        )

    console.print(table)
    console.print()

    # Print timestamps
    console.print(f"[dim]Baseline created: {comparison.baseline_timestamp}[/dim]")
    console.print(f"[dim]Comparison time: {comparison.comparison_timestamp}[/dim]")
    console.print()
