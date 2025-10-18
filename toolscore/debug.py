"""Interactive debugging utilities for Toolscore evaluation failures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult


def _find_mismatches(result: EvaluationResult) -> list[dict[str, Any]]:
    """Find all mismatches between gold and trace calls.

    Args:
        result: Evaluation result to analyze

    Returns:
        List of mismatch details
    """
    mismatches = []

    # Check for missing tools
    tool_correctness = result.metrics.get("tool_correctness_metrics", {})
    missing_tools = tool_correctness.get("missing_tools", [])
    extra_tools = tool_correctness.get("extra_tools", [])

    if missing_tools:
        for tool in missing_tools:
            mismatches.append(
                {
                    "type": "missing_tool",
                    "tool": tool,
                    "message": f"Expected tool '{tool}' was never called",
                }
            )

    if extra_tools:
        for tool in extra_tools:
            mismatches.append(
                {
                    "type": "extra_tool",
                    "tool": tool,
                    "message": f"Unexpected tool '{tool}' was called",
                }
            )

    # Check for argument mismatches
    gold_calls = result.gold_calls
    trace_calls = result.trace_calls

    for i, gold_call in enumerate(gold_calls):
        if i >= len(trace_calls):
            mismatches.append(
                {
                    "type": "missing_call",
                    "index": i,
                    "gold_call": gold_call,
                    "message": f"Expected call #{i+1} to '{gold_call.tool}' but trace ended",
                }
            )
            continue

        trace_call = trace_calls[i]

        # Tool name mismatch
        if gold_call.tool != trace_call.tool:
            mismatches.append(
                {
                    "type": "tool_mismatch",
                    "index": i,
                    "gold_call": gold_call,
                    "trace_call": trace_call,
                    "message": f"Call #{i+1}: Expected '{gold_call.tool}' but got '{trace_call.tool}'",
                }
            )
            continue

        # Argument mismatch
        gold_args = gold_call.args or {}
        trace_args = trace_call.args or {}

        if gold_args != trace_args:
            # Find specific arg differences
            arg_diffs = []
            all_keys = set(gold_args.keys()) | set(trace_args.keys())

            for key in all_keys:
                gold_val = gold_args.get(key)
                trace_val = trace_args.get(key)

                if gold_val != trace_val:
                    arg_diffs.append(
                        {
                            "arg": key,
                            "expected": gold_val,
                            "actual": trace_val,
                        }
                    )

            if arg_diffs:
                mismatches.append(
                    {
                        "type": "argument_mismatch",
                        "index": i,
                        "gold_call": gold_call,
                        "trace_call": trace_call,
                        "arg_diffs": arg_diffs,
                        "message": f"Call #{i+1} to '{gold_call.tool}': Arguments don't match",
                    }
                )

    # Check for extra calls
    if len(trace_calls) > len(gold_calls):
        for i in range(len(gold_calls), len(trace_calls)):
            trace_call = trace_calls[i]
            mismatches.append(
                {
                    "type": "extra_call",
                    "index": i,
                    "trace_call": trace_call,
                    "message": f"Unexpected call #{i+1} to '{trace_call.tool}'",
                }
            )

    return mismatches


def _format_value(value: Any) -> str:
    """Format a value for display.

    Args:
        value: Value to format

    Returns:
        Formatted string
    """
    if value is None:
        return "[dim]<missing>[/dim]"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, (list, dict)):
        import json

        return json.dumps(value, indent=2)
    return str(value)


def _show_mismatch_detail(
    mismatch: dict[str, Any],
    console: Console,
) -> None:
    """Show detailed view of a single mismatch.

    Args:
        mismatch: Mismatch details
        console: Rich Console instance
    """
    mismatch_type = mismatch["type"]

    console.print()
    console.print(Panel(f"[yellow]{mismatch['message']}[/yellow]", border_style="yellow"))

    if mismatch_type == "missing_tool":
        console.print()
        console.print("[bold]Expected tool:[/bold]", mismatch["tool"])
        console.print("[dim]This tool was never called in the trace[/dim]")
        console.print()
        console.print("[cyan]Suggestion:[/cyan] Check if:")
        console.print("  • Agent has access to this tool")
        console.print("  • Tool name matches exactly")
        console.print("  • Agent's logic includes calling this tool")

    elif mismatch_type == "extra_tool":
        console.print()
        console.print("[bold]Unexpected tool:[/bold]", mismatch["tool"])
        console.print("[dim]This tool was called but not expected[/dim]")
        console.print()
        console.print("[cyan]Suggestion:[/cyan]")
        console.print("  • This might be fine - check if semantically equivalent")
        console.print("  • Try --llm-judge flag for semantic matching")
        console.print("  • Or update gold standard if this is valid")

    elif mismatch_type == "tool_mismatch":
        gold_call = mismatch["gold_call"]
        trace_call = mismatch["trace_call"]

        table = Table(show_header=True, header_style="bold magenta", box=None)
        table.add_column("", style="dim")
        table.add_column("Expected", style="green")
        table.add_column("Actual", style="red")

        table.add_row("Tool", gold_call.tool, trace_call.tool)

        console.print()
        console.print(table)
        console.print()
        console.print("[cyan]Suggestion:[/cyan]")
        console.print("  • Check if tools are semantically equivalent (e.g., 'search' vs 'web_search')")
        console.print("  • Try --llm-judge flag to check semantic equivalence")
        console.print("  • Verify agent is selecting correct tool")

    elif mismatch_type == "argument_mismatch":
        gold_call = mismatch["gold_call"]
        trace_call = mismatch["trace_call"]
        arg_diffs = mismatch["arg_diffs"]

        console.print()
        console.print(f"[bold]Tool:[/bold] {gold_call.tool}")
        console.print()

        table = Table(show_header=True, header_style="bold magenta", box=None)
        table.add_column("Argument", style="cyan")
        table.add_column("Expected", style="green")
        table.add_column("Actual", style="red")

        for diff in arg_diffs:
            expected_str = _format_value(diff["expected"])
            actual_str = _format_value(diff["actual"])
            table.add_row(diff["arg"], expected_str, actual_str)

        console.print(table)
        console.print()
        console.print("[cyan]Suggestion:[/cyan]")
        console.print("  • Check argument names match exactly")
        console.print("  • Verify argument types and values")
        console.print("  • Review schema validation with --verbose flag")

    elif mismatch_type == "missing_call":
        gold_call = mismatch["gold_call"]

        console.print()
        console.print("[bold]Expected call:[/bold]")
        console.print(f"  Tool: {gold_call.tool}")
        if gold_call.args:
            console.print(f"  Args: {gold_call.args}")
        console.print()
        console.print("[dim]Trace ended before this call[/dim]")
        console.print()
        console.print("[cyan]Suggestion:[/cyan]")
        console.print("  • Agent may have stopped early")
        console.print("  • Check if agent encountered an error")
        console.print("  • Verify agent completes full workflow")

    elif mismatch_type == "extra_call":
        trace_call = mismatch["trace_call"]

        console.print()
        console.print("[bold]Unexpected call:[/bold]")
        console.print(f"  Tool: {trace_call.tool}")
        if trace_call.args:
            console.print(f"  Args: {trace_call.args}")
        console.print()
        console.print("[dim]This call was not expected[/dim]")
        console.print()
        console.print("[cyan]Suggestion:[/cyan]")
        console.print("  • Check if agent made redundant calls")
        console.print("  • Verify agent's stopping condition")
        console.print("  • Or update gold standard if this is valid")

    console.print()


def run_interactive_debug(
    result: EvaluationResult,
    console: Console | None = None,
) -> None:
    """Run interactive debug session for evaluation failures.

    Args:
        result: Evaluation result to debug
        console: Rich Console instance (creates new one if None)
    """
    if console is None:
        console = Console()

    # Find all mismatches
    mismatches = _find_mismatches(result)

    if not mismatches:
        console.print()
        console.print("[green]No mismatches found! Evaluation passed.[/green]")
        console.print()
        return

    # Show header
    console.print()
    console.print(Panel.fit("[bold cyan]Interactive Debug Mode[/bold cyan]", border_style="cyan"))
    console.print()
    console.print(f"Found [yellow]{len(mismatches)}[/yellow] mismatches to debug")
    console.print()

    # Interactive loop
    current_index = 0

    while True:
        mismatch = mismatches[current_index]

        # Show navigation info
        console.print(
            f"[dim]Showing mismatch {current_index + 1} of {len(mismatches)}[/dim]"
        )

        # Show mismatch detail
        _show_mismatch_detail(mismatch, console)

        # Show navigation options
        options = []
        if current_index > 0:
            options.append("[n]ext")
            options.append("[p]revious")
        elif current_index == 0 and len(mismatches) > 1:
            options.append("[n]ext")

        options.append("[q]uit")

        console.print(f"[dim]Commands: {', '.join(options)}[/dim]")

        # Get user input
        choice = Prompt.ask("", choices=["n", "p", "q"], default="n", show_choices=False)

        if choice == "q":
            console.print()
            console.print("[dim]Exiting debug mode[/dim]")
            console.print()
            break
        elif choice == "n":
            if current_index < len(mismatches) - 1:
                current_index += 1
            else:
                console.print()
                console.print("[yellow]Already at last mismatch[/yellow]")
        elif choice == "p":
            if current_index > 0:
                current_index -= 1
            else:
                console.print()
                console.print("[yellow]Already at first mismatch[/yellow]")
