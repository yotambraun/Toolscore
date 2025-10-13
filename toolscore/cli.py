"""Command-line interface for Toolscore."""

import sys
from pathlib import Path

import click
from rich.console import Console

from toolscore import __version__
from toolscore.core import evaluate_trace
from toolscore.reports import (
    generate_html_report,
    generate_json_report,
    print_error,
    print_evaluation_summary,
    print_progress,
    print_validation_result,
)


@click.group()
@click.version_option(version=__version__, prog_name="toolscore")
def main() -> None:
    """Toolscore: LLM Tool Usage Evaluation Package.

    Evaluate the tool-using behavior of LLM-based agents by comparing
    traces against gold-standard specifications.
    """
    pass


@main.command()
@click.argument("gold_file", type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.argument("trace_file", type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.option(
    "--format",
    "-f",
    type=click.Choice(["auto", "openai", "anthropic", "langchain", "custom"]),
    default="auto",
    help="Trace format (auto-detect by default)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default="toolscore.json",
    help="Output JSON report file",
)
@click.option(
    "--html",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Output HTML report file",
)
@click.option(
    "--no-side-effects",
    is_flag=True,
    default=False,
    help="Disable side-effect validation",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Verbose output",
)
def eval(
    gold_file: Path,
    trace_file: Path,
    format: str,
    output: Path,
    html: Path | None,
    no_side_effects: bool,
    verbose: bool,
) -> None:
    """Evaluate an agent trace against gold standard.

    GOLD_FILE: Path to gold standard specification (gold_calls.json)

    TRACE_FILE: Path to agent trace file (trace.json)
    """
    console = Console()

    try:
        # Show progress
        if verbose:
            print_progress(f"Loading gold standard from: {gold_file}", console)
            print_progress(f"Loading trace from: {trace_file}", console)
            print_progress(f"Format: {format}", console)

        result = evaluate_trace(
            gold_file,
            trace_file,
            format=format,
            validate_side_effects=not no_side_effects,
        )

        # Generate reports
        json_path = generate_json_report(result, output)
        if verbose:
            print_progress(f"JSON report saved to: {json_path}", console)

        if html:
            html_path = generate_html_report(result, html)
            if verbose:
                print_progress(f"HTML report saved to: {html_path}", console)

        # Print beautiful summary
        print_evaluation_summary(result, console=console, verbose=verbose)

        # Show file locations at the end
        console.print(f"[dim]>[/dim] JSON report: [cyan]{json_path}[/cyan]")
        if html:
            console.print(f"[dim]>[/dim] HTML report: [cyan]{html}[/cyan]")
        console.print()

    except FileNotFoundError as e:
        print_error(f"File not found: {e}", console)
        sys.exit(1)
    except ValueError as e:
        print_error(f"Invalid data: {e}", console)
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}", console)
        if verbose:
            raise
        sys.exit(1)


@main.command()
@click.argument("trace_file", type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.option(
    "--format",
    "-f",
    type=click.Choice(["auto", "openai", "anthropic", "langchain", "custom"]),
    default="auto",
    help="Trace format (auto-detect by default)",
)
def validate(trace_file: Path, format: str) -> None:
    """Validate trace file format.

    TRACE_FILE: Path to trace file to validate
    """
    console = Console()

    try:
        from toolscore.core import load_trace

        calls = load_trace(trace_file, format=format)

        first_call = calls[0] if calls else None
        print_validation_result(str(trace_file), len(calls), first_call, console)

    except Exception as e:
        print_error(f"Invalid trace file: {e}", console)
        sys.exit(1)


if __name__ == "__main__":
    main()
