"""Command-line interface for Toolscore."""

import json
import os
import shlex
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from toolscore import __version__
from toolscore.baseline import (
    compare_to_baseline,
    load_baseline,
    print_comparison_result,
)
from toolscore.baseline import (
    save_baseline as save_baseline_file,
)
from toolscore.comparison import (
    compare_models,
    print_comparison_table,
    save_comparison_report,
)
from toolscore.core import evaluate_trace
from toolscore.debug import run_interactive_debug
from toolscore.generators import generate_from_openai_schema
from toolscore.generators.synthetic import save_gold_standard
from toolscore.metrics.llm_judge import JudgeConfig, Provider
from toolscore.reports import (
    generate_csv_report,
    generate_html_report,
    generate_json_report,
    generate_markdown_report,
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
    type=click.Choice(["auto", "openai", "anthropic", "gemini", "mcp", "langchain", "custom"]),
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
    "--csv",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Output CSV report file (for Excel/Google Sheets)",
)
@click.option(
    "--markdown",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Output Markdown report file (for GitHub/docs)",
)
@click.option(
    "--no-side-effects",
    is_flag=True,
    default=False,
    help="Disable side-effect validation",
)
@click.option(
    "--llm-judge",
    is_flag=True,
    default=False,
    help="Use LLM-as-a-judge for semantic evaluation (requires a provider API key)",
)
@click.option(
    "--llm-model",
    type=str,
    default="gpt-4o-mini",
    help=(
        "Model for the LLM judge (default: gpt-4o-mini). Provider is inferred "
        "from the name (claude-* -> Anthropic, gemini-* -> Gemini). "
        "For a local OpenAI-compatible server: "
        "--llm-model llama3.1 --llm-base-url http://localhost:11434/v1"
    ),
)
@click.option(
    "--llm-provider",
    type=click.Choice(["openai", "anthropic", "gemini", "openai_compatible"]),
    default=None,
    help="Force the LLM judge provider (default: inferred from --llm-model)",
)
@click.option(
    "--llm-base-url",
    type=str,
    default=None,
    help=(
        "Custom OpenAI-compatible endpoint for the LLM judge "
        "(e.g. Ollama: http://localhost:11434/v1). Forces openai_compatible."
    ),
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Verbose output",
)
@click.option(
    "--debug",
    "-d",
    is_flag=True,
    default=False,
    help="Interactive debug mode for failures",
)
@click.option(
    "--save-baseline",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Save evaluation as baseline for regression testing",
)
def eval(
    gold_file: Path,
    trace_file: Path,
    format: str,
    output: Path,
    html: Path | None,
    csv: Path | None,
    markdown: Path | None,
    no_side_effects: bool,
    llm_judge: bool,
    llm_model: str,
    llm_provider: str | None,
    llm_base_url: str | None,
    verbose: bool,
    debug: bool,
    save_baseline: Path | None,
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

        judge: JudgeConfig | bool
        if llm_judge:
            provider: Provider | None = None
            if llm_provider is not None:
                # Choice() restricts values to the Provider literals.
                provider = llm_provider  # type: ignore[assignment]
            judge = JudgeConfig(
                model=llm_model,
                provider=provider,
                base_url=llm_base_url,
            )
        else:
            judge = False

        result = evaluate_trace(
            gold_file,
            trace_file,
            format=format,
            validate_side_effects=not no_side_effects,
            judge=judge,
        )

        # Generate reports
        json_path = generate_json_report(result, output)
        if verbose:
            print_progress(f"JSON report saved to: {json_path}", console)

        if html:
            html_path = generate_html_report(result, html)
            if verbose:
                print_progress(f"HTML report saved to: {html_path}", console)

        if csv:
            csv_path = generate_csv_report(result, csv)
            if verbose:
                print_progress(f"CSV report saved to: {csv_path}", console)

        if markdown:
            md_path = generate_markdown_report(result, markdown)
            if verbose:
                print_progress(f"Markdown report saved to: {md_path}", console)

        # Print beautiful summary
        print_evaluation_summary(result, console=console, verbose=verbose)

        # Interactive debug mode for failures
        if debug:
            run_interactive_debug(result, console=console)

        # Save baseline if requested
        if save_baseline:
            baseline_path = save_baseline_file(result, save_baseline, gold_file)
            if verbose:
                print_progress(f"Baseline saved to: {baseline_path}", console)
            console.print(f"[dim]>[/dim] Baseline: [cyan]{baseline_path}[/cyan]")

        # Show file locations at the end
        console.print(f"[dim]>[/dim] JSON report: [cyan]{json_path}[/cyan]")
        if html:
            console.print(f"[dim]>[/dim] HTML report: [cyan]{html}[/cyan]")
        if csv:
            console.print(f"[dim]>[/dim] CSV report: [cyan]{csv}[/cyan]")
        if markdown:
            console.print(f"[dim]>[/dim] Markdown report: [cyan]{markdown}[/cyan]")
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
    type=click.Choice(["auto", "openai", "anthropic", "gemini", "mcp", "langchain", "custom"]),
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


_FRAMEWORK_LABELS = {
    "langgraph": "LangGraph",
    "pydantic_ai": "Pydantic AI",
    "openai_agents": "OpenAI Agents SDK",
    "crewai": "CrewAI",
    "claude_agent_sdk": "Claude Agent SDK",
    "openai": "OpenAI (raw SDK)",
    "anthropic": "Anthropic (raw SDK)",
    "generic": "Generic / any framework",
}


@main.command()
@click.option(
    "--framework",
    type=click.Choice(list(_FRAMEWORK_LABELS.keys())),
    default=None,
    help="Agent framework to scaffold for (skips auto-detection prompt).",
)
@click.option(
    "--dir",
    "directory",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Target project directory (default: current directory).",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Accept the detected framework without prompting (non-interactive).",
)
@click.option(
    "--no-ci",
    is_flag=True,
    default=False,
    help="Skip writing the GitHub Actions workflow.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing files instead of erroring.",
)
def init(
    framework: str | None,
    directory: Path | None,
    yes: bool,
    no_ci: bool,
    force: bool,
) -> None:
    """Scaffold a working Toolscore test suite for your agent.

    Detects your agent framework and writes a pytest suite that passes
    immediately, so you reach a green test (and your first recorded snapshot)
    in about 60 seconds.
    """
    from toolscore.scaffold import detect_frameworks, scaffold

    console = Console()
    output_dir = directory if directory is not None else Path.cwd()

    console.print("\n[bold cyan]Toolscore init[/bold cyan] - scaffolding a tool-call test suite\n")

    # --- resolve the framework -------------------------------------------------
    if framework is None:
        detected = detect_frameworks(output_dir)
        default = detected[0]
        if len(detected) == 1:
            console.print(
                f"Detected framework: [green]{_FRAMEWORK_LABELS[default]}[/green]"
                if default != "generic"
                else "No framework detected - using [green]generic[/green] (works anywhere)."
            )
        else:
            labels = ", ".join(_FRAMEWORK_LABELS[f] for f in detected)
            console.print(f"Detected frameworks: [green]{labels}[/green]")

        if yes or not sys.stdin.isatty():
            framework = default
        else:
            framework = Prompt.ask(
                "Scaffold for which framework?",
                choices=list(_FRAMEWORK_LABELS.keys()),
                default=default,
            )
    else:
        console.print(f"Framework: [green]{_FRAMEWORK_LABELS[framework]}[/green]")

    # --- scaffold --------------------------------------------------------------
    try:
        created = scaffold(
            framework,
            output_dir,
            with_ci=not no_ci,
            force=force,
        )
    except FileExistsError as exc:
        print_error(
            f"{exc} already exists. Re-run with [cyan]--force[/cyan] to overwrite it.",
            console,
        )
        sys.exit(1)
    except Exception as exc:
        print_error(f"Failed to scaffold project: {exc}", console)
        sys.exit(1)

    console.print()
    for path in created:
        try:
            shown = path.relative_to(output_dir)
        except ValueError:
            shown = path
        console.print(f"[green]created[/green] {shown}")

    # --- next steps: lead with an instant aha, then a hands-on one ------------
    console.print("\n[bold green]Done![/bold green] Next steps:\n")
    console.print(
        "  [bold]0.[/bold] See a full health-check right now, no setup: [cyan]toolscore demo[/cyan]"
    )
    console.print(
        "  [bold]1.[/bold] Run [cyan]pytest[/cyan] (records the sample agent's calls), then "
        "[cyan]toolscore approve --all[/cyan] to set the baseline."
    )
    console.print(
        "  [bold]2.[/bold] [bold]See drift caught:[/bold] change a value in "
        "[cyan]_fake_agent_response[/cyan] and run [cyan]pytest[/cyan] again - the test fails "
        "with a diff."
    )
    console.print(
        "  [bold]3.[/bold] Swap [cyan]_fake_agent_response[/cyan] for your real agent in "
        "[cyan]tests/test_agent_tools.py[/cyan]."
    )
    console.print()


@main.command()
@click.option(
    "--from-openai",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    required=True,
    help="Path to OpenAI function definitions JSON file",
)
@click.option(
    "--count",
    "-n",
    type=int,
    default=10,
    help="Number of test cases to generate per function (default: 10)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default="gold_calls.json",
    help="Output file path (default: gold_calls.json)",
)
@click.option(
    "--no-edge-cases",
    is_flag=True,
    default=False,
    help="Disable edge case and boundary value generation",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Verbose output",
)
def generate(
    from_openai: Path,
    count: int,
    output: Path,
    no_edge_cases: bool,
    verbose: bool,
) -> None:
    """Generate synthetic test cases from function schemas.

    Creates gold standard test cases from OpenAI-style function definitions.
    Automatically generates varied test cases including edge cases and
    boundary values.

    Example OpenAI schema format:

        [
          {
            "name": "get_weather",
            "description": "Get current weather",
            "parameters": {
              "type": "object",
              "properties": {
                "location": {"type": "string"},
                "unit": {"type": "string", "enum": ["C", "F"]}
              },
              "required": ["location"]
            }
          }
        ]
    """
    console = Console()

    try:
        if verbose:
            print_progress(f"Loading function schema from: {from_openai}", console)

        # Generate test cases
        gold_calls = generate_from_openai_schema(
            from_openai,
            count=count,
            include_edge_cases=not no_edge_cases,
        )

        if verbose:
            print_progress(f"Generated {len(gold_calls)} test cases", console)

        # Save to file
        output_path = save_gold_standard(gold_calls, output)

        console.print()
        console.print(
            Panel.fit(
                f"[green]OK[/green] Generated {len(gold_calls)} test cases",
                border_style="green",
            )
        )

        # Show summary
        info = Table(show_header=False, box=None, padding=(0, 1))
        info.add_column(style="dim")
        info.add_column()

        info.add_row("Output file:", str(output_path))
        info.add_row("Test cases:", str(len(gold_calls)))

        # Count unique tools
        unique_tools = {call["tool"] for call in gold_calls}
        info.add_row("Functions:", str(len(unique_tools)))

        if not no_edge_cases:
            info.add_row("Variations:", "Normal + Edge cases + Boundary values")
        else:
            info.add_row("Variations:", "Normal cases only")

        console.print(info)
        console.print()

        # Next steps
        console.print("[bold]Next steps:[/bold]")
        console.print(f"  1. Review generated test cases: [cyan]{output_path}[/cyan]")
        console.print("  2. Capture your agent's trace to [cyan]trace.json[/cyan]")
        console.print(f"  3. Run: [cyan]toolscore eval {output_path} trace.json[/cyan]")
        console.print()

    except FileNotFoundError as e:
        print_error(f"File not found: {e}", console)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON in schema file: {e}", console)
        sys.exit(1)
    except Exception as e:
        print_error(f"Failed to generate test cases: {e}", console)
        if verbose:
            raise
        sys.exit(1)


@main.command()
@click.argument("gold_file", type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.argument("trace_files", nargs=-1, type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.option(
    "--names",
    "-n",
    multiple=True,
    help="Model names (same order as trace files, e.g., -n gpt-4 -n claude-3)",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["auto", "openai", "anthropic", "gemini", "mcp", "langchain", "custom"]),
    default="auto",
    help="Trace format (auto-detect by default)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default="comparison.json",
    help="Output comparison report file",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Verbose output",
)
def compare(
    gold_file: Path,
    trace_files: tuple[Path, ...],
    names: tuple[str, ...],
    format: str,
    output: Path,
    verbose: bool,
) -> None:
    """Compare multiple model traces against gold standard.

    Evaluates multiple traces and displays a side-by-side comparison table
    showing which model performs best on each metric.

    GOLD_FILE: Path to gold standard specification

    TRACE_FILES: Paths to trace files from different models

    Example:

        toolscore compare gold.json gpt4_trace.json claude_trace.json \\
            -n gpt-4 -n claude-3 -o comparison.json
    """
    console = Console()

    if not trace_files:
        print_error("At least one trace file is required", console)
        sys.exit(1)

    # Generate model names if not provided
    if names:
        if len(names) != len(trace_files):
            print_error(
                f"Number of names ({len(names)}) must match number of trace files ({len(trace_files)})",
                console,
            )
            sys.exit(1)
        model_names = list(names)
    else:
        # Use file stems as model names
        model_names = [trace_file.stem for trace_file in trace_files]

    try:
        if verbose:
            print_progress(f"Loading gold standard from: {gold_file}", console)
            print_progress(f"Comparing {len(trace_files)} models", console)

        # Evaluate each trace
        model_results = {}
        for model_name, trace_file in zip(model_names, trace_files, strict=True):
            if verbose:
                print_progress(f"Evaluating {model_name}...", console)

            result = evaluate_trace(
                gold_file,
                trace_file,
                format=format,
                validate_side_effects=False,  # Skip side effects for comparison
                judge=False,  # Skip LLM judge for speed
            )
            model_results[model_name] = result

        # Generate comparison
        comparison = compare_models(model_results)

        # Print comparison table
        print_comparison_table(comparison, console=console)

        # Save comparison report
        report_path = save_comparison_report(comparison, output)
        if verbose:
            print_progress(f"Comparison report saved to: {report_path}", console)

        console.print(f"[dim]>[/dim] Comparison report: [cyan]{report_path}[/cyan]")
        console.print()

        # Show quick tips
        console.print("[bold]Next steps:[/bold]")
        console.print("  • Check the winner and see where other models fell short")
        console.print("  • Run individual evals with [cyan]--verbose[/cyan] for details")
        console.print("  • Use [cyan]--llm-judge[/cyan] if tool names differ semantically")
        console.print()

    except FileNotFoundError as e:
        print_error(f"File not found: {e}", console)
        sys.exit(1)
    except ValueError as e:
        print_error(f"Invalid data: {e}", console)
        sys.exit(1)
    except Exception as e:
        print_error(f"Comparison failed: {e}", console)
        if verbose:
            raise
        sys.exit(1)


@main.command()
@click.argument("baseline_file", type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.argument("trace_file", type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.option(
    "--gold-file",
    "-g",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    required=True,
    help="Path to gold standard specification (required)",
)
@click.option(
    "--threshold",
    "-t",
    type=float,
    default=0.05,
    help="Maximum allowed regression as decimal (default: 0.05 = 5%%)",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["auto", "openai", "anthropic", "gemini", "mcp", "langchain", "custom"]),
    default="auto",
    help="Trace format (auto-detect by default)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Output comparison report file (JSON)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Verbose output",
)
def regression(
    baseline_file: Path,
    trace_file: Path,
    gold_file: Path,
    threshold: float,
    format: str,
    output: Path | None,
    verbose: bool,
) -> None:
    """Compare agent trace against a saved baseline.

    Detects regressions by comparing current evaluation against a previously
    saved baseline. Returns exit code 0 for PASS, 1 for FAIL (regression detected).

    BASELINE_FILE: Path to baseline JSON file (created with --save-baseline)

    TRACE_FILE: Path to current agent trace file

    Example:

        # First, create a baseline:
        toolscore eval gold.json trace.json --save-baseline baseline.json

        # Then, run regression checks in CI:
        toolscore regression baseline.json new_trace.json --gold-file gold.json

        # With custom threshold (10%):
        toolscore regression baseline.json trace.json -g gold.json -t 0.10
    """
    console = Console()

    try:
        if verbose:
            print_progress(f"Loading baseline from: {baseline_file}", console)
            print_progress(f"Loading trace from: {trace_file}", console)
            print_progress(f"Threshold: {threshold:.0%}", console)

        # Load baseline
        baseline = load_baseline(baseline_file)

        # Evaluate current trace
        if verbose:
            print_progress("Evaluating current trace...", console)

        result = evaluate_trace(
            gold_file,
            trace_file,
            format=format,
            validate_side_effects=False,  # Skip for speed in CI
            judge=False,  # Skip for consistency
        )

        # Compare against baseline
        comparison = compare_to_baseline(result, baseline, threshold, gold_file)

        # Print comparison results
        print_comparison_result(comparison, console=console)

        # Save comparison report if requested
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("w", encoding="utf-8") as f:
                json.dump(comparison.to_dict(), f, indent=2)
            console.print(f"[dim]>[/dim] Comparison report: [cyan]{output}[/cyan]")
            console.print()

        # Exit with appropriate code
        if comparison.passed:
            sys.exit(0)
        else:
            sys.exit(1)

    except FileNotFoundError as e:
        print_error(f"File not found: {e}", console)
        sys.exit(2)
    except ValueError as e:
        print_error(f"Invalid data: {e}", console)
        sys.exit(2)
    except Exception as e:
        print_error(f"Regression check failed: {e}", console)
        if verbose:
            raise
        sys.exit(2)


def _resolve_mcp_command(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    console: Console,
) -> tuple[list[str], dict[str, str]]:
    """Resolve an MCP launch command from a positional string or a config file.

    Exactly one source must be supplied: either a single shell-quoted command
    string (positional argument) or a ``--config`` path. Supplying both or
    neither is an error.

    Args:
        command: The positional command tokens as Click parsed them (Click
            splits on whitespace, so this is re-joined and ``shlex``-split).
        config: Path to a Claude Desktop style config file, or ``None``.
        server: The server name to select from the config, or ``None``.
        console: Console for printing error output.

    Returns:
        A tuple of ``(command_vector, env_overrides)``.

    Raises:
        SystemExit: With code 2 if the inputs are ambiguous, missing, or the
            config cannot be loaded.
    """
    from toolscore.mcp import load_mcp_config

    positional = " ".join(command).strip()

    if positional and config is not None:
        print_error("Provide exactly one of a server command or --config, not both.", console)
        sys.exit(2)
    if not positional and config is None:
        print_error(
            "Provide an MCP server command (quoted) or --config PATH [--server NAME].",
            console,
        )
        sys.exit(2)

    if positional:
        return shlex.split(positional), {}

    assert config is not None  # narrowed by the checks above
    try:
        spec = load_mcp_config(config, server=server)
    except (FileNotFoundError, ValueError) as exc:
        print_error(f"Failed to load MCP config: {exc}", console)
        sys.exit(2)
    return spec.command, spec.env


@main.group()
def mcp() -> None:
    """Test, lint, and score MCP servers.

    Point these commands at any MCP server -- either by passing its launch
    command as a single quoted string, or via a Claude Desktop style config
    file with --config/--server.
    """


@mcp.command("list")
@click.argument("command", nargs=-1)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Claude Desktop style MCP config file (alternative to a command).",
)
@click.option("--server", default=None, help="Server name to select from --config.")
@click.option("--timeout", type=float, default=30.0, help="Per-call timeout in seconds.")
def mcp_list(
    command: tuple[str, ...], config: Path | None, server: str | None, timeout: float
) -> None:
    """List the tools advertised by an MCP server.

    COMMAND: the server launch command as a single quoted string,
    e.g. "python server.py" (omit when using --config).
    """
    from toolscore.mcp import MCPStdioClient

    console = Console()
    cmd, env = _resolve_mcp_command(command, config, server, console)

    try:
        with MCPStdioClient(cmd, env=env or None, timeout=timeout) as client:
            info = client.server_info
            tools = client.list_tools()
    except Exception as exc:  # surface any launch/protocol failure to the user
        print_error(f"Failed to query MCP server: {exc}", console)
        sys.exit(1)

    name = str(info.get("name", "unknown server"))
    version = str(info.get("version", ""))
    console.print(f"\n[bold]{name}[/bold] [dim]{version}[/dim]  ({len(tools)} tools)\n")

    table = Table(header_style="bold magenta")
    table.add_column("Tool", style="cyan")
    table.add_column("Params", justify="right")
    table.add_column("Description", style="dim")
    for tool in tools:
        params = (
            tool.input_schema.get("properties", {}) if isinstance(tool.input_schema, dict) else {}
        )
        description = tool.description or "[red](no description)[/red]"
        table.add_row(tool.name, str(len(params)), description)
    console.print(table)
    console.print()


@mcp.command("lint")
@click.argument("command", nargs=-1)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Claude Desktop style MCP config file (alternative to a command).",
)
@click.option("--server", default=None, help="Server name to select from --config.")
@click.option("--timeout", type=float, default=30.0, help="Per-call timeout in seconds.")
def mcp_lint(
    command: tuple[str, ...], config: Path | None, server: str | None, timeout: float
) -> None:
    """Statically lint an MCP server's tool schemas.

    Exits 1 if any error-severity issue is found.

    COMMAND: the server launch command as a single quoted string
    (omit when using --config).
    """
    from toolscore.mcp import MCPStdioClient, lint_tools

    console = Console()
    cmd, env = _resolve_mcp_command(command, config, server, console)

    try:
        with MCPStdioClient(cmd, env=env or None, timeout=timeout) as client:
            tools = client.list_tools()
    except Exception as exc:  # surface any launch/protocol failure to the user
        print_error(f"Failed to query MCP server: {exc}", console)
        sys.exit(1)

    issues = lint_tools(tools)
    errors = sum(1 for i in issues if i.severity == "error")
    warnings = sum(1 for i in issues if i.severity == "warning")

    if not issues:
        console.print(f"\n[green]OK[/green] No lint issues across {len(tools)} tools.\n")
        return

    console.print(f"\n[bold]Lint:[/bold] {errors} errors, {warnings} warnings\n")
    table = Table(header_style="bold magenta")
    table.add_column("Severity")
    table.add_column("Tool", style="cyan")
    table.add_column("Message")
    for issue in issues:
        color = "red" if issue.severity == "error" else "yellow"
        table.add_row(f"[{color}]{issue.severity}[/{color}]", issue.tool, issue.message)
    console.print(table)
    console.print()

    if errors:
        sys.exit(1)


@mcp.command("test")
@click.argument("command", nargs=-1)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Claude Desktop style MCP config file (alternative to a command).",
)
@click.option("--server", default=None, help="Server name to select from --config.")
@click.option("--cases", type=int, default=3, help="Happy-path scenarios per tool (default: 3).")
@click.option("--no-edge-cases", is_flag=True, default=False, help="Skip edge-case scenarios.")
@click.option("--timeout", type=float, default=30.0, help="Per-call timeout in seconds.")
@click.option(
    "--report",
    type=click.Choice(["md", "json"]),
    default=None,
    help="Write a Markdown or JSON report (in addition to the console summary).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Path for the --report file.",
)
@click.option(
    "--fail-under",
    default=None,
    help="Minimum acceptable grade (A-F); exit 1 if the scorecard grade is below it.",
)
@click.option(
    "--ci",
    is_flag=True,
    default=False,
    help=(
        "CI mode: write the scorecard to $GITHUB_STEP_SUMMARY and exit non-zero on blocking "
        "issues (a tool that fails on valid input, an edge crash, or a schema error)."
    ),
)
def mcp_test(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    cases: int,
    no_edge_cases: bool,
    timeout: float,
    report: str | None,
    output: Path | None,
    fail_under: str | None,
    ci: bool,
) -> None:
    """Run the full scorecard against an MCP server.

    Spins up the server, generates happy-path and edge-case scenarios from each
    tool's schema, executes them, lints the schemas, and prints an A-F
    scorecard.

    COMMAND: the server launch command as a single quoted string,
    e.g. "python server.py" (omit when using --config).
    """
    from toolscore.mcp import (
        MCPScorecard,
        MCPStdioClient,
        generate_scenarios,
        grade_meets,
        lint_tools,
        print_scorecard,
        run_scenarios,
        scorecard_to_json,
        scorecard_to_markdown,
    )

    console = Console()

    valid_grades = {"A", "B", "C", "D", "F"}
    if fail_under is not None and fail_under.upper() not in valid_grades:
        print_error(f"--fail-under must be one of A-F, got {fail_under!r}.", console)
        sys.exit(2)

    if report is not None and output is None:
        print_error("--report requires --output PATH.", console)
        sys.exit(2)

    cmd, env = _resolve_mcp_command(command, config, server, console)

    try:
        with MCPStdioClient(cmd, env=env or None, timeout=timeout) as client:
            tools = client.list_tools()
            scenarios = generate_scenarios(
                tools, cases_per_tool=cases, include_edge_cases=not no_edge_cases
            )
            results = run_scenarios(client, scenarios)
            server_info = client.server_info
    except Exception as exc:  # surface any launch/protocol failure to the user
        print_error(f"Failed to test MCP server: {exc}", console)
        sys.exit(1)

    card = MCPScorecard(
        server_info=server_info,
        tools=tools,
        results=results,
        lint=lint_tools(tools),
    )

    wrote_file = False
    if report is not None and output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        if report == "json":
            output.write_text(json.dumps(scorecard_to_json(card), indent=2), encoding="utf-8")
        else:
            output.write_text(scorecard_to_markdown(card), encoding="utf-8")
        name = str(server_info.get("name", "server"))
        console.print(
            f"[bold]{name}[/bold] -> Grade [bold]{card.grade}[/bold] "
            f"(score {card.score:.0%}). Report written to [cyan]{output}[/cyan]."
        )
        wrote_file = True

    # Always show the console scorecard unless a file report was the only output.
    if ci or not wrote_file:
        print_scorecard(card, console=console)

    if ci:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with Path(summary_path).open("a", encoding="utf-8") as handle:
                handle.write(scorecard_to_markdown(card) + "\n")
            console.print("[dim]Wrote the scorecard to the GitHub Actions job summary.[/dim]")

    if fail_under is not None and not grade_meets(card.grade, fail_under):
        console.print(f"[red]Grade {card.grade} is below the required {fail_under.upper()}.[/red]")
        sys.exit(1)

    if ci and fail_under is None:
        # Default CI gate: fail on real problems (a tool that breaks on valid
        # input, an edge-case crash, or a schema error) -- but not on warnings.
        has_blocking = card.lint_error_count > 0 or any(not r.ok for r in card.results)
        if has_blocking:
            console.print("[red]Blocking issues found (see 'Top issues to fix' above).[/red]")
            sys.exit(1)


@main.command("demo")
def demo() -> None:
    """Health-check a bundled sample MCP server -- zero setup, no API key.

    Launches a small sample MCP server that ships with toolscore (one with a few
    deliberate issues) and prints the same scorecard that ``toolscore mcp test``
    produces, so you can see the instant verdict in seconds.
    """
    from toolscore.mcp import (
        MCPScorecard,
        MCPStdioClient,
        generate_scenarios,
        lint_tools,
        print_scorecard,
        run_scenarios,
    )

    console = Console()
    sample_server = Path(__file__).resolve().parent / "mcp" / "sample_server.py"
    if not sample_server.is_file():
        print_error(f"Bundled sample server not found at {sample_server}.", console)
        sys.exit(1)

    console.print(
        "[bold]toolscore demo[/bold] - grading a bundled sample MCP server "
        "(no setup, no API key).\n"
    )

    try:
        with MCPStdioClient([sys.executable, str(sample_server)], timeout=30.0) as client:
            tools = client.list_tools()
            scenarios = generate_scenarios(tools, cases_per_tool=3, include_edge_cases=True)
            results = run_scenarios(client, scenarios)
            server_info = client.server_info
    except Exception as exc:  # surface any launch/protocol failure to the user
        print_error(f"Failed to run the sample server: {exc}", console)
        sys.exit(1)

    card = MCPScorecard(
        server_info=server_info,
        tools=tools,
        results=results,
        lint=lint_tools(tools),
    )
    print_scorecard(card, console=console)
    console.print(
        "\n[dim]That's the health-check. Now point it at your own server:[/dim] "
        '[bold]toolscore mcp test "python your_server.py"[/bold]'
    )


# ---------------------------------------------------------------------------
# record command
# ---------------------------------------------------------------------------

_DEFAULT_SNAP_DIR = ".toolscore/snapshots"


@main.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.option(
    "--update",
    is_flag=True,
    default=False,
    help="Overwrite an existing snapshot and approve it.",
)
@click.option(
    "--from-trace",
    "from_trace",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Load calls from a trace file instead of running a subprocess.",
)
@click.option(
    "--name",
    default=None,
    help="Snapshot name (required with --from-trace).",
)
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["auto", "openai", "anthropic", "gemini", "mcp", "langchain", "custom"]),
    default="auto",
    help="Trace format (auto-detect by default); only used with --from-trace.",
)
@click.option(
    "--dir",
    "snap_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=_DEFAULT_SNAP_DIR,
    help=f"Snapshot store directory (default: {_DEFAULT_SNAP_DIR}).",
)
@click.argument("cmd", nargs=-1, type=click.UNPROCESSED)
def record(
    update: bool,
    from_trace: Path | None,
    name: str | None,
    fmt: str,
    snap_dir: Path,
    cmd: tuple[str, ...],
) -> None:
    """Record tool-call snapshots.

    Two modes:

    \b
    Subprocess mode — run pytest (or any command) and capture snapshots:
      toolscore record [--update] -- pytest tests/ -k my_test

    \b
    Trace mode — load calls from an existing trace file:
      toolscore record --from-trace trace.json --name my_snap [--format auto]

    After recording, approve snapshots with `toolscore approve`.
    """
    import os
    import subprocess

    from toolscore.snapshots import Snapshot, SnapshotStore

    console = Console()

    # --- validate mutual exclusivity ---
    if from_trace is not None and cmd:
        print_error(
            "--from-trace and a trailing command are mutually exclusive; use one or the other.",
            console,
        )
        sys.exit(2)

    if from_trace is None and not cmd:
        print_error(
            "Provide either --from-trace FILE or a command after --.",
            console,
        )
        sys.exit(2)

    if from_trace is not None and not name:
        print_error("--name is required when using --from-trace.", console)
        sys.exit(2)

    # --- trace mode ---
    if from_trace is not None:
        assert name is not None  # checked above
        from toolscore.core import load_trace

        store = SnapshotStore(snap_dir)
        try:
            tool_calls = load_trace(from_trace, format=fmt)
        except (FileNotFoundError, ValueError) as exc:
            print_error(f"Failed to load trace: {exc}", console)
            sys.exit(1)

        calls = [{"tool": tc.tool, "args": tc.args or {}} for tc in tool_calls]

        existing = store.load(name)
        if existing is not None and not update:
            print_error(
                f"Snapshot {name!r} already exists. Use --update to overwrite and approve it.",
                console,
            )
            sys.exit(1)

        if existing is not None and update:
            existing.calls = calls
            existing.approved = True
            existing.source = "trace"
            store.save(existing)
            console.print(
                f"[green]Updated[/green] snapshot [cyan]{name!r}[/cyan] "
                f"({len(calls)} calls) — approved."
            )
        else:
            snap = Snapshot(name=name, calls=calls, approved=False, source="trace")
            store.save(snap)
            console.print(
                f"[green]Recorded[/green] snapshot [cyan]{name!r}[/cyan] "
                f"({len(calls)} calls) — pending approval."
            )
            console.print(f"[dim]Run [cyan]toolscore approve {name}[/cyan] to approve it.[/dim]")
        return

    # --- subprocess mode ---
    cmd_list = list(cmd)
    console.print(f"[dim]Recording snapshots via:[/dim] {' '.join(cmd_list)}")

    env = {**os.environ, "TOOLSCORE_RECORD": "1"}
    if update:
        env["TOOLSCORE_RECORD_UPDATE"] = "1"

    completed = subprocess.run(cmd_list, env=env)

    if completed.returncode == 0:
        console.print(
            "[green]Done.[/green] Run [cyan]toolscore approve --all[/cyan] "
            "to approve any new snapshots."
        )
    else:
        console.print(
            f"[yellow]Command exited with code {completed.returncode}.[/yellow] "
            "Run [cyan]toolscore approve --all[/cyan] to approve any recorded snapshots."
        )

    sys.exit(completed.returncode)


# ---------------------------------------------------------------------------
# approve command
# ---------------------------------------------------------------------------


@main.command()
@click.argument("names", nargs=-1)
@click.option(
    "--all", "approve_all", is_flag=True, default=False, help="Approve all pending snapshots."
)
@click.option(
    "--dir",
    "snap_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=_DEFAULT_SNAP_DIR,
    help=f"Snapshot store directory (default: {_DEFAULT_SNAP_DIR}).",
)
def approve(names: tuple[str, ...], approve_all: bool, snap_dir: Path) -> None:
    """Approve one or more snapshots for use as a baseline.

    \b
    Examples:
      toolscore approve my_test         # approve a single snapshot by name
      toolscore approve --all           # approve every pending snapshot
    """
    from datetime import timezone

    from toolscore.snapshots import SnapshotStore

    console = Console()
    store = SnapshotStore(snap_dir)

    if not names and not approve_all:
        print_error("Provide snapshot NAME(s) or --all.", console)
        sys.exit(2)

    # --- collect snapshots to approve ---
    to_approve = []
    if approve_all:
        pending = store.pending()
        if not pending:
            console.print("[dim]No pending snapshots found — nothing to approve.[/dim]")
            return
        to_approve = pending
    else:
        for n in names:
            snap = store.load(n)
            if snap is None:
                print_error(f"Snapshot {n!r} does not exist.", console)
                sys.exit(1)
            to_approve.append(snap)

    # --- approve them ---
    approved = []
    for snap in to_approve:
        snap = store.approve(snap.name)
        approved.append(snap)

    # --- rich table ---
    from datetime import datetime

    table = Table(header_style="bold magenta")
    table.add_column("Name", style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Age", style="dim")

    for snap in approved:
        try:
            dt = datetime.fromisoformat(snap.created_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = now - dt
            days = delta.days
            if days == 0:
                age = "today"
            elif days == 1:
                age = "1 day ago"
            else:
                age = f"{days} days ago"
        except (ValueError, TypeError):
            age = snap.created_at or "unknown"

        table.add_row(snap.name, str(len(snap.calls)), age)

    console.print()
    console.print(table)
    console.print(f"\n[green]Approved {len(approved)} snapshot(s).[/green]")


# ---------------------------------------------------------------------------
# snapshots sub-group
# ---------------------------------------------------------------------------


@main.group()
def snapshots() -> None:
    """List, inspect, and manage recorded snapshots."""


@snapshots.command("list")
@click.option(
    "--pending", is_flag=True, default=False, help="Show only pending (unapproved) snapshots."
)
@click.option(
    "--dir",
    "snap_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=_DEFAULT_SNAP_DIR,
    help=f"Snapshot store directory (default: {_DEFAULT_SNAP_DIR}).",
)
def snapshots_list(pending: bool, snap_dir: Path) -> None:
    """List all recorded snapshots."""
    from toolscore.snapshots import SnapshotStore

    console = Console()
    store = SnapshotStore(snap_dir)

    all_snaps = store.list()
    if pending:
        all_snaps = [s for s in all_snaps if not s.approved]

    if not all_snaps:
        console.print("[dim]No snapshots found.[/dim]")
        return

    table = Table(header_style="bold magenta")
    table.add_column("Status", justify="center", width=6)
    table.add_column("Name", style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Updated", style="dim")
    table.add_column("Source", style="dim")

    for snap in all_snaps:
        icon = "[green]v[/green]" if snap.approved else "[yellow]o[/yellow]"
        table.add_row(icon, snap.name, str(len(snap.calls)), snap.updated_at[:19], snap.source)

    console.print()
    console.print(table)
    console.print()


@snapshots.command("show")
@click.argument("name")
@click.option(
    "--dir",
    "snap_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=_DEFAULT_SNAP_DIR,
    help=f"Snapshot store directory (default: {_DEFAULT_SNAP_DIR}).",
)
def snapshots_show(name: str, snap_dir: Path) -> None:
    """Show the tool calls and metadata for a snapshot."""
    from toolscore.snapshots import SnapshotStore

    console = Console()
    store = SnapshotStore(snap_dir)

    snap = store.load(name)
    if snap is None:
        print_error(f"Snapshot {name!r} not found.", console)
        sys.exit(1)

    status = "[green]approved[/green]" if snap.approved else "[yellow]pending[/yellow]"
    console.print(f"\n[bold]Snapshot:[/bold] [cyan]{snap.name}[/cyan]  {status}")
    console.print(f"[dim]Source:[/dim]  {snap.source}")
    console.print(f"[dim]Created:[/dim] {snap.created_at}")
    console.print(f"[dim]Updated:[/dim] {snap.updated_at}")
    console.print(f"[dim]Calls:[/dim]   {len(snap.calls)}")
    console.print()

    for i, call in enumerate(snap.calls, 1):
        console.print(f"[bold]Call {i}[/bold] — [cyan]{call.get('tool', '?')}[/cyan]")
        console.print(json.dumps(call.get("args", {}), indent=2))
        console.print()


@snapshots.command("rm")
@click.argument("name")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.option(
    "--dir",
    "snap_dir",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=_DEFAULT_SNAP_DIR,
    help=f"Snapshot store directory (default: {_DEFAULT_SNAP_DIR}).",
)
def snapshots_rm(name: str, yes: bool, snap_dir: Path) -> None:
    """Delete a snapshot by name."""
    from toolscore.snapshots import SnapshotStore

    console = Console()
    store = SnapshotStore(snap_dir)

    snap = store.load(name)
    if snap is None:
        print_error(f"Snapshot {name!r} not found.", console)
        sys.exit(1)

    if not yes:
        answer = Prompt.ask(
            f"Delete snapshot [cyan]{name!r}[/cyan]? [y/N]",
            default="n",
        )
        if answer.lower() not in ("y", "yes"):
            console.print("[dim]Aborted.[/dim]")
            return

    store.delete(name)
    console.print(f"[green]Deleted[/green] snapshot [cyan]{name!r}[/cyan].")


if __name__ == "__main__":
    main()
