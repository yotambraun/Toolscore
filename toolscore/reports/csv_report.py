"""CSV report generation."""

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult


def generate_csv_report(
    result: "EvaluationResult",
    output_path: str | Path = "toolscore.csv",
) -> Path:
    """Generate CSV report from evaluation result.

    Creates a CSV file with metrics that can be opened in Excel or Google Sheets.
    Perfect for sharing results with non-technical stakeholders.

    Args:
        result: Evaluation result to report.
        output_path: Path to save the CSV report.

    Returns:
        Path to the generated report file.
    """
    path = Path(output_path)

    # Flatten metrics dictionary for CSV
    rows: list[list[str]] = []

    # Add summary metrics
    rows.append(["Category", "Metric", "Value"])
    rows.append(["Summary", "Gold Calls Count", str(len(result.gold_calls))])
    rows.append(["Summary", "Trace Calls Count", str(len(result.trace_calls))])
    rows.append(["", "", ""])  # Empty row for separation

    # Add all metrics
    rows.append(["Category", "Metric", "Value"])

    def flatten_metrics(metrics: dict[str, Any], prefix: str = "") -> None:
        """Recursively flatten nested metrics dictionary."""
        for key, value in metrics.items():
            if isinstance(value, dict):
                flatten_metrics(value, f"{prefix}{key}.")
            elif isinstance(value, (list, tuple)):
                # Convert lists to comma-separated strings
                rows.append([prefix.rstrip("."), key, ", ".join(map(str, value))])
            else:
                # Format percentages and numbers
                if isinstance(value, float):
                    if key.endswith("_accuracy") or key.endswith("_rate") or "score" in key:
                        # Format as percentage
                        rows.append([prefix.rstrip("."), key, f"{value * 100:.2f}%"])
                    else:
                        # Format as number with 4 decimal places
                        rows.append([prefix.rstrip("."), key, f"{value:.4f}"])
                else:
                    rows.append([prefix.rstrip("."), key, str(value)])

    flatten_metrics(result.metrics)

    # Write CSV file
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    return path
