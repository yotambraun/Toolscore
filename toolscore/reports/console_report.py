"""Rich-based console reporting for Toolscore evaluation results."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult


def _get_metric_color(value: float, thresholds: tuple[float, float] = (0.7, 0.9)) -> str:
    """Get color for metric value based on thresholds.

    Args:
        value: Metric value (0.0 to 1.0)
        thresholds: Tuple of (poor_threshold, good_threshold)

    Returns:
        Color string for rich display
    """
    poor_threshold, good_threshold = thresholds
    if value >= good_threshold:
        return "green"
    elif value >= poor_threshold:
        return "yellow"
    else:
        return "red"


def _format_percentage(value: float) -> Text:
    """Format a percentage value with color coding.

    Args:
        value: Value between 0.0 and 1.0

    Returns:
        Rich Text object with formatted percentage
    """
    color = _get_metric_color(value)
    return Text(f"{value:.1%}", style=f"bold {color}")


def print_evaluation_summary(
    result: EvaluationResult,
    console: Console | None = None,
    verbose: bool = False,
) -> None:
    """Print a beautiful console summary of evaluation results.

    Args:
        result: Evaluation result to display
        console: Rich Console instance (creates new one if None)
        verbose: Whether to show detailed information
    """
    if console is None:
        console = Console()

    metrics = result.metrics

    # Print header
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]Toolscore Evaluation Results[/bold cyan]",
            border_style="cyan",
        )
    )
    console.print()

    # Basic info
    if verbose:
        info_table = Table(show_header=False, box=None, padding=(0, 1))
        info_table.add_column(style="dim")
        info_table.add_column()

        info_table.add_row("Expected calls:", str(len(result.gold_calls)))
        info_table.add_row("Actual calls:", str(len(result.trace_calls)))

        console.print(info_table)
        console.print()

    # Core metrics table
    metrics_table = Table(title="Core Metrics", show_header=True, header_style="bold magenta")
    metrics_table.add_column("Metric", style="cyan", no_wrap=True)
    metrics_table.add_column("Score", justify="right")
    metrics_table.add_column("Description", style="dim")

    # Invocation Accuracy
    inv_acc = metrics.get("invocation_accuracy", 0.0)
    metrics_table.add_row(
        "Invocation Accuracy",
        _format_percentage(inv_acc),
        "Did agent invoke tools when needed?",
    )

    # Selection Accuracy
    sel_acc = metrics.get("selection_accuracy", 0.0)
    metrics_table.add_row(
        "Selection Accuracy", _format_percentage(sel_acc), "Did agent choose correct tools?"
    )

    # Tool Correctness
    tool_correctness_metrics = metrics.get("tool_correctness_metrics", {})
    tool_correctness = tool_correctness_metrics.get("tool_correctness", 0.0)
    correct_count = tool_correctness_metrics.get("correct_count", 0)
    total_expected = tool_correctness_metrics.get("total_expected", 0)
    metrics_table.add_row(
        "Tool Correctness",
        _format_percentage(tool_correctness),
        f"All expected tools called? ({correct_count}/{total_expected})",
    )

    # Sequence Accuracy
    seq_metrics = metrics.get("sequence_metrics", {})
    seq_acc = seq_metrics.get("sequence_accuracy", 0.0)
    edit_dist = seq_metrics.get("edit_distance", 0)
    metrics_table.add_row(
        "Sequence Accuracy",
        _format_percentage(seq_acc),
        f"Did agent call tools in order? (distance: {edit_dist})",
    )

    # Argument F1
    arg_metrics = metrics.get("argument_metrics", {})
    arg_f1 = arg_metrics.get("f1", 0.0)
    arg_precision = arg_metrics.get("precision", 0.0)
    arg_recall = arg_metrics.get("recall", 0.0)
    metrics_table.add_row(
        "Argument F1",
        _format_percentage(arg_f1),
        f"How well arguments matched? (P:{arg_precision:.1%} R:{arg_recall:.1%})",
    )

    # Redundant Call Rate
    eff_metrics = metrics.get("efficiency_metrics", {})
    red_rate = eff_metrics.get("redundant_rate", 0.0)
    red_count = eff_metrics.get("redundant_count", 0)
    total_calls = eff_metrics.get("total_calls", 0)
    # Lower is better for redundancy, so invert color
    red_color = "green" if red_rate < 0.1 else "yellow" if red_rate < 0.3 else "red"
    metrics_table.add_row(
        "Redundant Call Rate",
        Text(f"{red_rate:.1%}", style=f"bold {red_color}"),
        f"Unnecessary calls? ({red_count}/{total_calls})",
    )

    console.print(metrics_table)
    console.print()

    # Show missing/extra tools in verbose mode
    if verbose and tool_correctness_metrics:
        missing_tools = tool_correctness_metrics.get("missing_tools", [])
        extra_tools = tool_correctness_metrics.get("extra_tools", [])

        if missing_tools or extra_tools:
            tools_table = Table(
                title="Tool Coverage Details", show_header=True, header_style="bold magenta"
            )
            tools_table.add_column("Category", style="cyan", no_wrap=True)
            tools_table.add_column("Tools", justify="left")

            if missing_tools:
                tools_table.add_row("Missing", Text(", ".join(missing_tools), style="red"))
            if extra_tools:
                tools_table.add_row("Extra", Text(", ".join(extra_tools), style="yellow"))

            console.print(tools_table)
            console.print()

    # Schema validation metrics if available
    schema_metrics = metrics.get("schema_metrics")
    if schema_metrics:
        schema_table = Table(
            title="Schema Validation", show_header=True, header_style="bold magenta"
        )
        schema_table.add_column("Metric", style="cyan", no_wrap=True)
        schema_table.add_column("Value", justify="right")
        schema_table.add_column("Description", style="dim")

        compliance_rate = schema_metrics.get("schema_compliance_rate", 0.0)
        total_validated = schema_metrics.get("total_validated", 0)
        failed_count = schema_metrics.get("failed_count", 0)
        total_errors = schema_metrics.get("total_errors", 0)

        schema_table.add_row(
            "Compliance Rate",
            _format_percentage(compliance_rate),
            "Arguments match schema requirements",
        )
        schema_table.add_row(
            "Validated Calls", str(total_validated), "Calls with schema definitions"
        )
        if failed_count > 0:
            schema_table.add_row(
                "Failed Calls", Text(str(failed_count), style="bold red"), "Validation failures"
            )
            schema_table.add_row(
                "Total Errors", Text(str(total_errors), style="bold red"), "Schema violations"
            )

        console.print(schema_table)
        console.print()

        # Show detailed errors in verbose mode
        if verbose and total_errors > 0:
            error_details = schema_metrics.get("error_details", [])
            if error_details:
                console.print("[bold red]Schema Validation Errors:[/bold red]")
                for error in error_details[:10]:  # Limit to first 10 errors
                    console.print(f"  • [red]{error}[/red]")
                if len(error_details) > 10:
                    console.print(f"  [dim]... and {len(error_details) - 10} more[/dim]")
                console.print()

    # LLM Judge metrics if available
    semantic_metrics = metrics.get("semantic_metrics")
    if semantic_metrics:
        sem_table = Table(
            title="LLM-as-a-Judge Evaluation", show_header=True, header_style="bold magenta"
        )
        sem_table.add_column("Metric", style="cyan", no_wrap=True)
        sem_table.add_column("Value", justify="right")
        sem_table.add_column("Description", style="dim")

        if "error" in semantic_metrics:
            sem_table.add_row(
                "Status", Text("Error", style="bold red"), semantic_metrics["error"]
            )
        else:
            sem_score = semantic_metrics.get("semantic_score", 0.0)
            model_used = semantic_metrics.get("model_used", "unknown")
            gold_count = semantic_metrics.get("gold_count", 0)
            trace_count = semantic_metrics.get("trace_count", 0)

            sem_table.add_row(
                "Semantic Score",
                _format_percentage(sem_score),
                "Semantic equivalence beyond exact matching",
            )
            sem_table.add_row("Model Used", model_used, "LLM judge model")
            if verbose:
                sem_table.add_row("Evaluated Calls", f"{min(gold_count, trace_count)}", "")

        console.print(sem_table)
        console.print()

    # Side-effect metrics if available
    se_metrics = metrics.get("side_effect_metrics")
    if se_metrics:
        se_table = Table(
            title="Side-Effect Validation", show_header=True, header_style="bold magenta"
        )
        se_table.add_column("Metric", style="cyan", no_wrap=True)
        se_table.add_column("Value", justify="right")

        success_rate = se_metrics.get("success_rate", 0.0)
        validated = se_metrics.get("validated_count", 0)
        total = se_metrics.get("total_with_side_effects", 0)
        failed = se_metrics.get("failed_count", 0)

        se_table.add_row("Success Rate", _format_percentage(success_rate))
        se_table.add_row("Validated", f"{validated}/{total}")
        if failed > 0:
            se_table.add_row("Failed", Text(str(failed), style="bold red"))

        console.print(se_table)
        console.print()

    # Performance metrics if available
    lat_metrics = metrics.get("latency_metrics")
    if lat_metrics and verbose:
        perf_table = Table(
            title="Performance Metrics", show_header=True, header_style="bold magenta"
        )
        perf_table.add_column("Metric", style="cyan", no_wrap=True)
        perf_table.add_column("Value", justify="right")

        perf_table.add_row("Total Duration", f"{lat_metrics.get('total_duration', 0):.3f}s")
        perf_table.add_row("Average Duration", f"{lat_metrics.get('average_duration', 0):.3f}s")
        perf_table.add_row("Max Duration", f"{lat_metrics.get('max_duration', 0):.3f}s")
        perf_table.add_row("Min Duration", f"{lat_metrics.get('min_duration', 0):.3f}s")

        console.print(perf_table)
        console.print()

    # Actionable suggestions based on failures
    suggestions = []

    if sel_acc < 0.5:
        # Check if there are tool name mismatches
        gold_tools = {call.tool for call in result.gold_calls}
        trace_tools = {call.tool for call in result.trace_calls}

        if gold_tools != trace_tools:
            different_tools = trace_tools - gold_tools
            if different_tools:
                suggestions.append(
                    f"! Tool name mismatch detected: Agent used {list(different_tools)[:3]} "
                    f"but expected {list(gold_tools)[:3]}"
                )
                suggestions.append(
                    "* Try: Add [cyan]--llm-judge[/cyan] flag to check semantic equivalence "
                    "(e.g., 'web_search' vs 'search')"
                )

    if arg_f1 < 0.5:
        suggestions.append(
            "! Argument mismatch detected: Tool arguments don't match expected values"
        )
        suggestions.append(
            "* Check: Argument names, types, and values in your trace"
        )
        if schema_metrics and schema_metrics.get("total_errors", 0) > 0:
            suggestions.append(
                "* Tip: Schema validation found type errors - run with [cyan]--verbose[/cyan] "
                "to see details"
            )

    if seq_acc < 0.8:
        suggestions.append(
            "! Sequence mismatch: Tools called in wrong order"
        )
        suggestions.append(
            "* Review: Agent's planning logic and tool dependencies"
        )

    tool_correctness = tool_correctness_metrics.get("tool_correctness", 1.0)
    if tool_correctness < 1.0:
        missing = tool_correctness_metrics.get("missing_tools", [])
        if missing:
            suggestions.append(
                f"! Missing tools: Agent didn't call {missing}"
            )
            suggestions.append(
                "* Check: Agent's tool selection logic and available tools"
            )

    # Display suggestions if any
    if suggestions:
        console.print()
        console.print("[bold yellow]Suggestions for Improvement:[/bold yellow]")
        for suggestion in suggestions:
            console.print(f"   {suggestion}")
        console.print()

    # Overall assessment
    avg_score = (inv_acc + sel_acc + seq_acc + arg_f1) / 4
    assessment_color = _get_metric_color(avg_score)

    if avg_score >= 0.9:
        assessment = "Excellent! Agent is performing very well."
    elif avg_score >= 0.7:
        assessment = "Good performance with room for improvement."
    elif avg_score >= 0.5:
        assessment = "Moderate performance. Consider reviewing prompts and tool definitions."
    else:
        assessment = "Poor performance. Significant improvements needed."

    console.print(
        Panel(
            Text(assessment, style=f"bold {assessment_color}"),
            title=f"Overall Assessment: {avg_score:.1%}",
            border_style=assessment_color,
        )
    )
    console.print()


def print_validation_result(
    trace_file: str,
    call_count: int,
    first_call: Any | None = None,
    console: Console | None = None,
) -> None:
    """Print trace validation results.

    Args:
        trace_file: Path to validated trace file
        call_count: Number of calls found
        first_call: First call details (optional)
        console: Rich Console instance (creates new one if None)
    """
    if console is None:
        console = Console()

    console.print()
    console.print(
        Panel.fit(
            f"[green]OK[/green] Valid trace file: [cyan]{trace_file}[/cyan]",
            border_style="green",
        )
    )

    info = Table(show_header=False, box=None, padding=(0, 1))
    info.add_column(style="dim")
    info.add_column()
    info.add_row("Total calls:", str(call_count))

    if first_call:
        info.add_row("First tool:", str(first_call.tool))
        info.add_row("First args:", str(first_call.args))

    console.print(info)
    console.print()


def print_error(message: str, console: Console | None = None) -> None:
    """Print an error message.

    Args:
        message: Error message to display
        console: Rich Console instance (creates new one if None)
    """
    if console is None:
        console = Console()

    console.print()
    console.print(Panel.fit(f"[red]ERROR[/red] {message}", border_style="red"))
    console.print()


def print_progress(message: str, console: Console | None = None) -> None:
    """Print a progress message.

    Args:
        message: Progress message to display
        console: Rich Console instance (creates new one if None)
    """
    if console is None:
        console = Console()

    console.print(f"[dim]>[/dim] {message}")
