"""Markdown report generation."""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult


def generate_markdown_report(
    result: "EvaluationResult",
    output_path: str | Path = "toolscore.md",
) -> Path:
    """Generate Markdown report from evaluation result.

    Creates a Markdown file perfect for embedding in GitHub issues, PRs,
    wikis, or documentation. Includes formatted tables and emoji indicators.

    Args:
        result: Evaluation result to report.
        output_path: Path to save the Markdown report.

    Returns:
        Path to the generated report file.
    """
    path = Path(output_path)

    # Build markdown content
    lines = []

    # Header
    lines.append("# Toolscore Evaluation Report")
    lines.append(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Summary
    lines.append("## 📊 Summary")
    lines.append("")
    lines.append(f"- **Gold Standard Calls:** {len(result.gold_calls)}")
    lines.append(f"- **Actual Trace Calls:** {len(result.trace_calls)}")
    lines.append("")

    # Key Metrics Table
    lines.append("## 🎯 Key Metrics")
    lines.append("")
    lines.append("| Metric | Value | Status |")
    lines.append("|--------|-------|--------|")

    # Helper function to get status emoji
    def get_status(value: float) -> str:
        if value >= 0.95:
            return "✅ Excellent"
        elif value >= 0.85:
            return "🟢 Good"
        elif value >= 0.70:
            return "🟡 Fair"
        else:
            return "🔴 Needs Improvement"

    # Add key metrics
    metrics = result.metrics
    if "invocation_accuracy" in metrics:
        value = metrics["invocation_accuracy"]
        lines.append(f"| Invocation Accuracy | {value * 100:.2f}% | {get_status(value)} |")

    if "selection_accuracy" in metrics:
        value = metrics["selection_accuracy"]
        lines.append(f"| Selection Accuracy | {value * 100:.2f}% | {get_status(value)} |")

    if "tool_correctness" in metrics:
        value = metrics["tool_correctness"]
        lines.append(f"| Tool Correctness | {value * 100:.2f}% | {get_status(value)} |")

    if "argument_metrics" in metrics:
        arg_metrics = metrics["argument_metrics"]
        if "f1" in arg_metrics:
            value = arg_metrics["f1"]
            lines.append(f"| Argument F1 Score | {value * 100:.2f}% | {get_status(value)} |")

    if "sequence_metrics" in metrics:
        seq_metrics = metrics["sequence_metrics"]
        if "sequence_accuracy" in seq_metrics:
            value = seq_metrics["sequence_accuracy"]
            lines.append(f"| Sequence Accuracy | {value * 100:.2f}% | {get_status(value)} |")

    lines.append("")

    # Efficiency Metrics
    if "efficiency_metrics" in metrics:
        lines.append("## ⚡ Efficiency Metrics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")

        eff_metrics = metrics["efficiency_metrics"]
        if "redundant_rate" in eff_metrics:
            value = eff_metrics["redundant_rate"]
            lines.append(f"| Redundant Call Rate | {value * 100:.2f}% |")

        if "missing_rate" in eff_metrics:
            value = eff_metrics["missing_rate"]
            lines.append(f"| Missing Call Rate | {value * 100:.2f}% |")

        if "extra_rate" in eff_metrics:
            value = eff_metrics["extra_rate"]
            lines.append(f"| Extra Call Rate | {value * 100:.2f}% |")

        lines.append("")

    # Semantic Evaluation
    if "semantic_metrics" in metrics:
        lines.append("## 🧠 Semantic Evaluation")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")

        sem_metrics = metrics["semantic_metrics"]
        if "semantic_score" in sem_metrics:
            value = sem_metrics["semantic_score"]
            lines.append(f"| Semantic Score | {value * 100:.2f}% |")

        if "semantic_matches" in sem_metrics:
            value = sem_metrics["semantic_matches"]
            lines.append(f"| Semantic Matches | {value} |")

        lines.append("")

    # Side Effects
    if "side_effect_metrics" in metrics:
        lines.append("## 🔄 Side Effects")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")

        se_metrics = metrics["side_effect_metrics"]
        if "success_rate" in se_metrics:
            value = se_metrics["success_rate"]
            lines.append(f"| Success Rate | {value * 100:.2f}% |")

        if "validated_count" in se_metrics:
            value = se_metrics["validated_count"]
            lines.append(f"| Validated Count | {value} |")

        lines.append("")

    # All Metrics Details
    lines.append("## 📋 All Metrics")
    lines.append("")
    lines.append("<details>")
    lines.append("<summary>Click to expand full metrics</summary>")
    lines.append("")
    lines.append("```json")

    import json
    lines.append(json.dumps(metrics, indent=2))

    lines.append("```")
    lines.append("</details>")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("*Generated with [Toolscore](https://github.com/yotambraun/toolscore)*")

    # Write to file
    content = "\n".join(lines)
    path.write_text(content, encoding="utf-8")

    return path
