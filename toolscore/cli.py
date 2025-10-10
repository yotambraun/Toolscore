"""Command-line interface for Toolscore."""

import sys
from pathlib import Path

import click

from toolscore import __version__
from toolscore.core import evaluate_trace
from toolscore.reports import generate_html_report, generate_json_report


@click.group()
@click.version_option(version=__version__, prog_name="toolscore")
def main() -> None:
    """Toolscore: LLM Tool Usage Evaluation Package.

    Evaluate the tool-using behavior of LLM-based agents by comparing
    traces against gold-standard specifications.
    """
    pass


@main.command()
@click.argument("gold_file", type=click.Path(exists=True, path_type=Path))
@click.argument("trace_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "-f",
    type=click.Choice(["auto", "openai", "anthropic", "custom"]),
    default="auto",
    help="Trace format (auto-detect by default)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default="toolscore.json",
    help="Output JSON report file",
)
@click.option(
    "--html",
    type=click.Path(path_type=Path),
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
    format: str,  # noqa: A002
    output: Path,
    html: Path | None,
    no_side_effects: bool,
    verbose: bool,
) -> None:
    """Evaluate an agent trace against gold standard.

    GOLD_FILE: Path to gold standard specification (gold_calls.json)

    TRACE_FILE: Path to agent trace file (trace.json)
    """
    try:
        # Run evaluation
        if verbose:
            click.echo(f"Loading gold standard from: {gold_file}")
            click.echo(f"Loading trace from: {trace_file}")
            click.echo(f"Format: {format}")

        result = evaluate_trace(
            gold_file,
            trace_file,
            format=format,
            validate_side_effects=not no_side_effects,
        )

        if verbose:
            click.echo(f"\nEvaluated {len(result.trace_calls)} tool calls")
            click.echo(f"Expected {len(result.gold_calls)} tool calls")

        # Generate JSON report
        json_path = generate_json_report(result, output)
        click.echo(f"\nJSON report saved to: {json_path}")

        # Generate HTML report if requested
        if html:
            html_path = generate_html_report(result, html)
            click.echo(f"HTML report saved to: {html_path}")

        # Print summary
        click.echo("\n=== Summary ===")
        metrics = result.metrics

        click.echo(f"Invocation Accuracy: {metrics['invocation_accuracy']:.2%}")
        click.echo(f"Selection Accuracy: {metrics['selection_accuracy']:.2%}")

        seq_metrics = metrics.get("sequence_metrics", {})
        click.echo(f"Sequence Accuracy: {seq_metrics.get('sequence_accuracy', 0):.2%}")

        arg_metrics = metrics.get("argument_metrics", {})
        click.echo(f"Argument F1 Score: {arg_metrics.get('f1', 0):.2%}")

        eff_metrics = metrics.get("efficiency_metrics", {})
        click.echo(f"Redundant Call Rate: {eff_metrics.get('redundant_rate', 0):.2%}")

        if not no_side_effects:
            se_metrics = metrics.get("side_effect_metrics", {})
            click.echo(f"Side-Effect Success Rate: {se_metrics.get('success_rate', 0):.2%}")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        if verbose:
            raise
        sys.exit(1)


@main.command()
@click.argument("trace_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "-f",
    type=click.Choice(["auto", "openai", "anthropic", "custom"]),
    default="auto",
    help="Trace format (auto-detect by default)",
)
def validate(trace_file: Path, format: str) -> None:  # noqa: A002
    """Validate trace file format.

    TRACE_FILE: Path to trace file to validate
    """
    try:
        from toolscore.core import load_trace

        calls = load_trace(trace_file, format=format)
        click.echo(f"✓ Valid trace file with {len(calls)} tool calls")

        if calls:
            click.echo("\nFirst call:")
            call = calls[0]
            click.echo(f"  Tool: {call.tool}")
            click.echo(f"  Args: {call.args}")

    except Exception as e:
        click.echo(f"✗ Invalid trace file: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
