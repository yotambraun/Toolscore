"""Multi-model comparison utilities for Toolscore."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console, RenderableType
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult


def compare_models(
    model_results: dict[str, EvaluationResult],
) -> dict[str, Any]:
    """Compare evaluation results across multiple models.

    Args:
        model_results: Dictionary mapping model names to their evaluation results

    Returns:
        Comparison summary with rankings and statistics
    """
    if not model_results:
        return {}

    comparison: dict[str, Any] = {
        "models": list(model_results.keys()),
        "metrics": {},
        "rankings": {},
        "best_model": {},
        "summary": {},
    }

    # Extract key metrics for each model
    metrics_to_compare = [
        "invocation_accuracy",
        "selection_accuracy",
        "tool_correctness",
        "sequence_accuracy",
        "argument_f1",
        "redundant_rate",
    ]

    for metric in metrics_to_compare:
        comparison["metrics"][metric] = {}

        for model_name, result in model_results.items():
            if metric == "tool_correctness":
                value = result.metrics.get("tool_correctness_metrics", {}).get(
                    "tool_correctness", 0.0
                )
            elif metric == "sequence_accuracy":
                value = result.metrics.get("sequence_metrics", {}).get("sequence_accuracy", 0.0)
            elif metric == "argument_f1":
                value = result.metrics.get("argument_metrics", {}).get("f1", 0.0)
            elif metric == "redundant_rate":
                value = result.metrics.get("efficiency_metrics", {}).get("redundant_rate", 0.0)
            else:
                value = result.metrics.get(metric, 0.0)

            comparison["metrics"][metric][model_name] = value

    # Calculate rankings (lower is better for redundant_rate, higher for others)
    for metric in metrics_to_compare:
        values = comparison["metrics"][metric]
        if metric == "redundant_rate":
            # Lower is better
            sorted_models = sorted(values.items(), key=lambda x: x[1])
        else:
            # Higher is better
            sorted_models = sorted(values.items(), key=lambda x: x[1], reverse=True)

        comparison["rankings"][metric] = [model for model, _ in sorted_models]

    # Calculate average score per model (excluding redundant_rate as it's inverse)
    avg_scores = {}
    for model_name in model_results:
        scores = []
        for metric in metrics_to_compare:
            if metric == "redundant_rate":
                # Invert redundant rate (0 is best, 1 is worst)
                scores.append(1.0 - comparison["metrics"][metric][model_name])
            else:
                scores.append(comparison["metrics"][metric][model_name])

        avg_scores[model_name] = sum(scores) / len(scores) if scores else 0.0

    # Determine best model overall
    best_model_name = max(avg_scores.items(), key=lambda x: x[1])[0]
    comparison["best_model"] = {
        "name": best_model_name,
        "average_score": avg_scores[best_model_name],
    }

    # Add summary statistics
    comparison["summary"] = {
        "total_models": len(model_results),
        "average_scores": avg_scores,
    }

    return comparison


def print_comparison_table(
    comparison: dict[str, Any],
    console: Console | None = None,
) -> None:
    """Print a beautiful comparison table.

    Args:
        comparison: Comparison results from compare_models()
        console: Rich Console instance (creates new one if None)
    """
    if console is None:
        console = Console()

    models = comparison.get("models", [])
    if not models:
        console.print("[yellow]No models to compare[/yellow]")
        return

    # Header
    console.print()
    console.print("[bold cyan]Model Comparison Results[/bold cyan]")
    console.print()

    # Create comparison table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", no_wrap=True)

    for model in models:
        table.add_column(model, justify="right")

    # Add Best column
    table.add_column("Best", style="bold green", justify="center")

    # Metrics to display
    metric_display = {
        "invocation_accuracy": "Invocation Acc",
        "selection_accuracy": "Selection Acc",
        "tool_correctness": "Tool Correctness",
        "sequence_accuracy": "Sequence Acc",
        "argument_f1": "Argument F1",
        "redundant_rate": "Redundant Rate",
    }

    for metric_key, metric_name in metric_display.items():
        values = comparison["metrics"].get(metric_key, {})
        if not values:
            continue

        row: list[RenderableType] = [metric_name]

        # Get best model for this metric
        best_model = comparison["rankings"][metric_key][0]

        # Add values for each model
        for model in models:
            value = values.get(model, 0.0)

            # Color code based on performance
            if metric_key == "redundant_rate":
                # Lower is better
                color = "green" if value < 0.1 else "yellow" if value < 0.3 else "red"
            else:
                # Higher is better
                color = "green" if value >= 0.9 else "yellow" if value >= 0.7 else "red"

            # Bold if best
            if model == best_model:
                row.append(Text(f"{value:.1%}", style=f"bold {color}"))
            else:
                row.append(Text(f"{value:.1%}", style=color))

        # Add best model indicator
        row.append(best_model)

        table.add_row(*row)

    console.print(table)
    console.print()

    # Overall winner
    best = comparison.get("best_model", {})
    if best:
        console.print(
            f"[bold green]Overall Winner:[/bold green] {best['name']} "
            f"(avg score: {best['average_score']:.1%})"
        )
        console.print()


def save_comparison_report(
    comparison: dict[str, Any],
    output_file: str | Path,
) -> Path:
    """Save comparison report to JSON file.

    Args:
        comparison: Comparison results from compare_models()
        output_file: Output file path

    Returns:
        Path to saved file
    """
    import json

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        json.dump(comparison, f, indent=2)

    return output_path
