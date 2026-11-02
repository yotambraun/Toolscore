"""Command-line interface for Toolscore."""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
from toolscore.metrics.honesty import load_honesty_config
from toolscore.metrics.llm_judge import JudgeConfig, Provider
from toolscore.metrics.policy import load_forbidden_rules
from toolscore.models import DEFAULT_JUDGE_MODEL
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

if TYPE_CHECKING:
    from toolscore.mcp import MCPClient, MCPServerSpec
    from toolscore.mcp.faults import FaultInjector
    from toolscore.mcp.fixtures import ArgumentFixtures
    from toolscore.mcp.probes import ProbeConfig
    from toolscore.mcp.recorder import MCPRecorder


@click.group()
@click.version_option(version=__version__, prog_name="toolscore")
def main() -> None:
    """Toolscore: test MCP servers and the tool calls your agents make.

    Evaluate the tool-using behavior of LLM-based agents by comparing
    traces against gold-standard specifications, grade MCP servers A-F,
    check that tools really did what they reported (mcp test --probes), and
    that agents told the truth about it (honesty).
    """
    pass


@main.command()
@click.argument("gold_file", type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.argument("trace_file", type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.option(
    "--format",
    "-f",
    type=click.Choice(
        ["auto", "openai", "anthropic", "gemini", "mcp", "langchain", "otel", "custom"]
    ),
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
    default=DEFAULT_JUDGE_MODEL,
    help=(
        f"Model for the LLM judge (default: {DEFAULT_JUDGE_MODEL}). Provider is inferred "
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
@click.option(
    "--forbidden",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help=(
        "JSON file of calls the agent must never make, e.g. "
        '[{"tool": "run_shell", "args": {"command": {"$regex": "rm -rf"}}}]'
    ),
)
@click.option(
    "--weight",
    "weight_overrides",
    multiple=True,
    metavar="NAME=VALUE",
    help=(
        "Override a score weight (repeatable), e.g. --weight required_call_recall=0.3 "
        "to make skipped or failed required calls lower the score"
    ),
)
@click.option(
    "--fail-on-violations",
    is_flag=True,
    default=False,
    help="Exit with status 1 if a forbidden call or a credential in tool arguments is found",
)
@click.option(
    "--final-answer",
    default=None,
    metavar="TEXT|@FILE",
    help=(
        "The agent's final answer to the user, for the honesty checks, when the trace does not "
        "hold it (recorded MCP sessions never do). @FILE reads it from a file."
    ),
)
@click.option(
    "--honesty-config",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="JSON or YAML file with honesty-check patterns and tool lists.",
)
@click.option(
    "--injected",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help=(
        "A 'toolscore mcp proxy --inject' session file: the faults it injected are matched to "
        "the trace's calls, so the honesty checks know what really failed."
    ),
)
@click.option(
    "--fail-on-honesty",
    is_flag=True,
    default=False,
    help=(
        "Exit with status 1 if an error-severity honesty finding is reported (a false success "
        "claim, an escape hatch that overrides a refusal, an undisclosed injected fault)."
    ),
)
@click.option(
    "--receipt",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help=(
        "Write a content-hashed receipt (input file hashes, settings, Toolscore version, "
        "result hash); `toolscore regrade RECEIPT` re-scores it later without re-running."
    ),
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
    forbidden: Path | None,
    weight_overrides: tuple[str, ...],
    fail_on_violations: bool,
    final_answer: str | None,
    honesty_config: Path | None,
    injected: Path | None,
    fail_on_honesty: bool,
    receipt: Path | None,
) -> None:
    """Evaluate an agent trace against gold standard.

    GOLD_FILE: Path to gold standard specification (gold_calls.json) or a
    contract file (required / optional / forbidden calls)

    TRACE_FILE: Path to agent trace file (trace.json)
    """
    console = Console()
    weights = _parse_weights(weight_overrides)

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
            forbidden=load_forbidden_rules(forbidden) if forbidden else None,
            weights=weights,
            final_answer=_read_text_option(final_answer),
            honesty=load_honesty_config(honesty_config) if honesty_config else None,
            injections=_session_injections(injected) if injected else None,
        )

        # Generate reports
        json_path = generate_json_report(result, output)
        if verbose:
            print_progress(f"JSON report saved to: {json_path}", console)

        receipt_path: Path | None = None
        if receipt:
            from toolscore.receipts import build_receipt, write_receipt

            receipt_path = write_receipt(
                receipt,
                build_receipt(
                    result,
                    inputs={
                        "gold": gold_file,
                        "trace": trace_file,
                        "forbidden": forbidden,
                        "honesty_config": honesty_config,
                        "injected": injected,
                    },
                    settings={
                        "format": format,
                        "validate_side_effects": not no_side_effects,
                        "llm_judge": llm_model if llm_judge else None,
                    },
                    final_answer=_read_text_option(final_answer),
                ),
            )

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
        if receipt_path:
            console.print(f"[dim]>[/dim] Receipt: [cyan]{receipt_path}[/cyan]")
        console.print()

        violations = len(result.policy_violations) + (
            result.metrics.get("security_metrics") or {}
        ).get("secret_count", 0)
        if fail_on_violations and violations:
            print_error(
                f"{violations} forbidden call(s) or credential(s) found (--fail-on-violations)",
                console,
            )
            sys.exit(1)

        honesty_errors = _honesty_errors(result.metrics.get("honesty_metrics"))
        if fail_on_honesty and honesty_errors:
            print_error(
                f"{honesty_errors} honesty finding(s) of error severity (--fail-on-honesty)",
                console,
            )
            sys.exit(1)

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
    type=click.Choice(
        ["auto", "openai", "anthropic", "gemini", "mcp", "langchain", "otel", "custom"]
    ),
    default="auto",
    help="Trace format (auto-detect by default).",
)
@click.option(
    "--gold",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Required calls (a gold file), so a success claim can be checked against them.",
)
@click.option(
    "--final-answer",
    default=None,
    metavar="TEXT|@FILE",
    help="The agent's final answer, when the trace does not hold it. @FILE reads a file.",
)
@click.option(
    "--injected",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="A 'toolscore mcp proxy --inject' session whose injected faults apply to this trace.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="JSON or YAML file with honesty-check patterns and tool lists.",
)
@click.option(
    "--json",
    "json_path",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Also write the findings and counts as JSON.",
)
@click.option(
    "--fail-on-findings",
    is_flag=True,
    default=False,
    help="Exit with status 1 on an error-severity finding (for CI).",
)
@click.option("--label", default=None, hidden=True, help="Name shown for the trace.")
def honesty(
    trace_file: Path,
    format: str,
    gold: Path | None,
    final_answer: str | None,
    injected: Path | None,
    config_path: Path | None,
    json_path: Path | None,
    fail_on_findings: bool,
    label: str | None = None,
) -> None:
    """Check whether an agent told the truth about what its tools did.

    Reads any trace (OpenAI, Anthropic, Responses, LangChain, OpenTelemetry,
    recorded MCP sessions) and compares the tool results with the agent's final
    answer: a success claim after a failure, a run that ends right after an
    error, a warning the answer leaves out, a code-execution tool used after a
    refusal, and faults injected by 'toolscore mcp proxy --inject' that the
    answer hides. Needs no gold file and no API key.

    TRACE_FILE: the agent trace or the proxy session.
    """
    from rich.markup import escape

    from toolscore.core import load_gold_standard
    from toolscore.metrics.honesty import apply_injections, check_honesty
    from toolscore.transcript import load_transcript

    console = Console()
    try:
        transcript = load_transcript(
            trace_file, format=format, final_answer=_read_text_option(final_answer)
        )
        if injected is not None:
            apply_injections(transcript.calls, _session_injections(injected))
        report = check_honesty(
            transcript.calls,
            transcript.final_answer,
            gold_calls=load_gold_standard(gold) if gold else None,
            config=load_honesty_config(config_path) if config_path else None,
            final_source=transcript.final_source,
        )
    except (OSError, ValueError) as exc:
        print_error(f"Could not check {trace_file}: {exc}", console)
        sys.exit(2)

    counts = report["false_success"]
    noun = "call" if len(transcript.calls) == 1 else "calls"
    console.print(
        f"\n[bold]Honesty check[/bold]  {label or trace_file}  "
        f"({len(transcript.calls)} tool {noun})"
    )
    if transcript.final_answer is None:
        console.print(
            "[yellow]Final answer: not in the trace[/yellow] [dim](checks that need it report "
            "unknown; pass --final-answer)[/dim]"
        )
    else:
        answer = " ".join(transcript.final_answer.split())
        shown = answer if len(answer) <= 100 else answer[:99] + "…"
        console.print(f"Final answer [dim]({transcript.final_source})[/dim]: {escape(shown)!r}")
    if report.get("results") == "missing":
        console.print(
            "[yellow]Tool results: not in the trace[/yellow] [dim](warnings, errors and refusals "
            "cannot be seen; those checks report unknown)[/dim]"
        )
    console.print()

    if report["findings"]:
        for finding in report["findings"]:
            style = "red" if finding["severity"] == "error" else "yellow"
            console.print(
                f"  [{style}]{finding['severity'].upper():<7}[/{style}]  "
                f"{escape(finding['message'])} [dim]({finding['rule']})[/dim]"
            )
        console.print()

    table = Table(title="False success", header_style="bold magenta", title_style="bold")
    table.add_column("Count")
    table.add_column("Value", justify="right")
    for key, value in counts.items():
        if value is None:
            shown_value = "[dim]n/a (no gold)[/dim]" if key == "failed_required" else "unknown"
        else:
            shown_value = str(value)
        table.add_row(key, shown_value)
    console.print(table)

    verdict = {True: "[red]FLAGGED[/red]", False: "[green]no false success found[/green]"}
    missing = (
        "no final answer"
        if transcript.final_answer is None
        else "no tool results"
        if report.get("results") == "missing"
        else "missing evidence"
    )
    console.print(
        f"Verdict: {verdict.get(report['flagged'], f'[yellow]unknown ({missing})[/yellow]')}\n"
    )

    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        console.print(f"[dim]>[/dim] JSON: [cyan]{json_path}[/cyan]")

    if fail_on_findings and _honesty_errors(report):
        sys.exit(1)


@main.command()
@click.argument("trace_file", type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.option(
    "--format",
    "-f",
    type=click.Choice(
        ["auto", "openai", "anthropic", "gemini", "mcp", "langchain", "otel", "custom"]
    ),
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
@click.argument("gold_file", required=False, type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.argument("trace_files", nargs=-1, type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.option(
    "--names",
    "-n",
    multiple=True,
    help="Model names (same order as trace files, e.g., -n gpt-6-luna -n claude-haiku-5-5)",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(
        ["auto", "openai", "anthropic", "gemini", "mcp", "langchain", "otel", "custom"]
    ),
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
@click.option(
    "--runs",
    "runs_files",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    help=(
        "Repeated runs: a JSONL file (toolscore agent run output or an export), repeatable. "
        "Switches to the statistics view (N, Wilson intervals, Fisher test, pass^k)."
    ),
)
@click.option(
    "--variant",
    "variants",
    multiple=True,
    metavar="NAME=DIR",
    help="Repeated runs: a directory of traces for one variant, scored against GOLD_FILE.",
)
@click.option(
    "--variant-key", default=None, help="JSONL field naming the variant (default arm_id)."
)
@click.option("--k", "k", type=int, default=1, show_default=True, help="k of pass^k (runs mode).")
@click.option(
    "--baseline", default=None, help="Runs mode: compare every variant with this one only."
)
@click.option(
    "--min-n",
    type=int,
    default=10,
    show_default=True,
    help="Runs mode: runs per variant before a difference can be called distinguishable.",
)
@click.option(
    "--alpha", type=float, default=0.05, show_default=True, help="Runs mode: Fisher test level."
)
@click.option(
    "--min-score",
    type=float,
    default=0.9,
    show_default=True,
    help="Runs mode with --variant: the score a trace needs to pass.",
)
@click.option(
    "--protocol",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help=(
        "Runs mode: decision rules declared before the runs (YAML/JSON); evaluated and "
        "reported, exit 1 when the decision is reject."
    ),
)
@click.option(
    "--json",
    "json_out",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Runs mode: write the statistics as JSON.",
)
def compare(
    gold_file: Path | None,
    trace_files: tuple[Path, ...],
    names: tuple[str, ...],
    format: str,
    output: Path,
    verbose: bool,
    runs_files: tuple[Path, ...],
    variants: tuple[str, ...],
    variant_key: str | None,
    k: int,
    baseline: str | None,
    min_n: int,
    alpha: float,
    min_score: float,
    protocol: Path | None,
    json_out: Path | None,
) -> None:
    """Compare models or variants.

    One trace per model: GOLD_FILE TRACE_FILES... prints a side-by-side
    table of every metric.

    Repeated runs per variant (--runs runs.jsonl, or GOLD_FILE with
    --variant NAME=DIR): per-variant N, pass/fail/error/unknown counts (errored
    runs stay in the denominator), pass rates with 95% Wilson intervals,
    pass^k per task, two-sided Fisher exact tests, and "not distinguishable"
    when the intervals overlap or N is too small. --protocol evaluates
    pre-declared decision rules.

    Examples:

        toolscore compare gold.json gpt4_trace.json claude_trace.json \\
            -n gpt-6-luna -n claude-haiku-5-5 -o comparison.json

        toolscore compare --runs runs.jsonl --k 3 --protocol protocol.yaml
    """
    if runs_files or variants:
        from toolscore.commands.stats import run_compare

        run_compare(
            runs_files,
            variants,
            gold_file,
            variant_key,
            k,
            baseline,
            min_n,
            alpha,
            min_score,
            protocol,
            json_out,
        )
        return
    console = Console()

    if gold_file is None or not trace_files:
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
    type=click.Choice(
        ["auto", "openai", "anthropic", "gemini", "mcp", "langchain", "otel", "custom"]
    ),
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


def _read_text_option(value: str | None) -> str | None:
    """A text option, or the contents of a file when it is ``@PATH``."""
    if value is None or not value.startswith("@"):
        return value
    return Path(value[1:]).read_text(encoding="utf-8")


def _session_injections(path: Path) -> list[dict[str, Any]]:
    """The ``injections`` list of a ``toolscore mcp proxy`` session file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    injections = data.get("injections") if isinstance(data, dict) else None
    if not isinstance(injections, list):
        raise ValueError(f"{path} has no 'injections' list (is it a 'mcp proxy' session?)")
    return [i for i in injections if isinstance(i, dict)]


def _honesty_errors(honesty: Any) -> int:
    """How many error-severity honesty findings a ``honesty_metrics`` dict holds."""
    findings = honesty.get("findings", []) if isinstance(honesty, dict) else []
    return sum(1 for f in findings if f.get("severity") == "error")


def _parse_weights(overrides: tuple[str, ...]) -> dict[str, float] | None:
    """Parse repeated ``--weight NAME=VALUE`` options into a weights dict."""
    if not overrides:
        return None
    weights: dict[str, float] = {}
    for item in overrides:
        name, sep, value = item.partition("=")
        try:
            weights[name.strip()] = float(value)
        except ValueError:
            sep = ""
        if not sep:
            raise click.BadParameter(f"expected NAME=VALUE, got {item!r}", param_hint="--weight")
    return weights


def _is_url(text: str) -> bool:
    """Whether a positional MCP target is a Streamable HTTP URL."""
    return text.startswith(("http://", "https://"))


def _resolve_mcp_target(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    console: Console,
    headers: tuple[str, ...] = (),
    auth_env: str | None = None,
) -> MCPServerSpec:
    """Resolve the server to test from a positional command/URL or a config file.

    Exactly one source must be supplied: a positional server command (or
    ``http(s)://`` URL), or a ``--config`` path. Supplying both or neither is an
    error.

    Args:
        command: The positional tokens. A single token is a shell-quoted
            command string (``shlex``-split) or a URL; several tokens (for
            example ``-- npx -y server "/path with spaces"`` from an MCP client
            config's ``args`` array) are already an argument vector.
        config: Path to an MCP host config file, or ``None``.
        server: The server name to select from the config, or ``None``.
        console: Console for printing error output.
        headers: ``--header "Name: value"`` options (``${VAR}`` expanded).
        auth_env: ``--auth-env VAR``: send ``Authorization: Bearer $VAR``.

    Returns:
        The resolved :class:`~toolscore.mcp.MCPServerSpec`.

    Raises:
        SystemExit: With code 2 if the inputs are ambiguous, missing, or the
            config cannot be loaded.
    """
    from toolscore.mcp import MCPServerSpec, load_mcp_config
    from toolscore.mcp.config import parse_header

    positional = " ".join(command).strip()

    if positional and config is not None:
        print_error("Provide exactly one of a server command or --config, not both.", console)
        sys.exit(2)
    if not positional and config is None:
        print_error(
            "Provide an MCP server command (quoted), a server URL, or --config PATH "
            "[--server NAME].",
            console,
        )
        sys.exit(2)

    if positional:
        if len(command) == 1 and _is_url(command[0]):
            from toolscore.mcp.client import safe_url

            spec = MCPServerSpec(name=safe_url(command[0]), command=[], url=command[0])
        elif len(command) == 1:
            spec = MCPServerSpec(name=positional, command=shlex.split(command[0]))
        else:
            spec = MCPServerSpec(name=positional, command=list(command))
    else:
        assert config is not None  # narrowed by the checks above
        try:
            spec = load_mcp_config(config, server=server)
        except (FileNotFoundError, ValueError) as exc:
            print_error(f"Failed to load MCP config: {exc}", console)
            sys.exit(2)

    if (headers or auth_env) and spec.url is None:
        print_error("--header and --auth-env apply to HTTP servers (a URL) only.", console)
        sys.exit(2)
    try:
        for item in headers:
            name, value = parse_header(item)
            spec.headers[name] = value
    except ValueError as exc:
        print_error(str(exc), console)
        sys.exit(2)
    if auth_env:
        token = os.environ.get(auth_env)
        if not token:
            print_error(f"--auth-env: environment variable {auth_env} is not set.", console)
            sys.exit(2)
        spec.headers["Authorization"] = f"Bearer {token}"
    return spec


def _mcp_connection_options(func: Any) -> Any:
    """Add the options shared by commands that connect to an MCP server."""
    options = [
        click.option(
            "--config",
            type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
            default=None,
            help=(
                "MCP host config file: Claude Desktop, Cursor or Claude Code (mcpServers) or "
                "VS Code (servers); stdio or url entries. Alternative to COMMAND."
            ),
        ),
        click.option("--server", default=None, help="Server name to select from --config."),
        click.option(
            "--header",
            "headers",
            multiple=True,
            metavar='"NAME: VALUE"',
            help=(
                "HTTP header for a URL server (repeatable). ${VAR} is read from the "
                "environment; quote with single quotes so the shell leaves it alone."
            ),
        ),
        click.option(
            "--auth-env",
            metavar="VAR",
            default=None,
            help="Send 'Authorization: Bearer <value of VAR>' to a URL server.",
        ),
        click.option(
            "--protocol",
            type=click.Choice(["auto", "modern", "legacy"]),
            default="auto",
            show_default=True,
            help=(
                "MCP protocol era: auto probes for 2026-07-28 (stateless) and falls back to "
                "the 2025-11-25 initialize handshake."
            ),
        ),
        click.option("--timeout", type=float, default=30.0, help="Per-call timeout in seconds."),
    ]
    for option in reversed(options):
        func = option(func)
    return func


def _argument_fixtures(
    options: tuple[str, ...], path: Path | None, console: Console
) -> ArgumentFixtures:
    """Read ``--args-file`` and ``--arg`` values (``--arg`` wins)."""
    from toolscore.mcp.fixtures import ArgumentFixtures, load_fixtures

    try:
        fixtures = load_fixtures(path) if path is not None else ArgumentFixtures()
        return fixtures.merged(ArgumentFixtures.from_options(options))
    except ValueError as exc:
        print_error(f"Invalid argument values: {exc}", console)
        sys.exit(2)


def _connect(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    headers: tuple[str, ...],
    auth_env: str | None,
    protocol: str,
    timeout: float,
    console: Console,
) -> MCPClient:
    """Resolve the target and build an unstarted client for it."""
    from toolscore.mcp import open_client

    spec = _resolve_mcp_target(command, config, server, console, headers, auth_env)
    return open_client(spec, timeout=timeout, protocol=protocol)  # type: ignore[arg-type]


@main.group()
def mcp() -> None:
    """Test, lint, score, record and fault-inject MCP servers.

    Point these commands at any MCP server: pass its launch command as a single
    quoted string, its Streamable HTTP URL, or an MCP host config file with
    --config/--server. Speaks MCP 2026-07-28 and falls back to the initialize
    handshake of earlier revisions.
    """


@mcp.command("list")
@click.argument("command", nargs=-1)
@_mcp_connection_options
@click.option(
    "--json",
    "json_out",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help=(
        "Also save a snapshot (server, protocol, instructions and full tool definitions) "
        "for `toolscore mcp diff` and `mcp verify-pin`."
    ),
)
def mcp_list(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    headers: tuple[str, ...],
    auth_env: str | None,
    protocol: str,
    timeout: float,
    json_out: Path | None,
) -> None:
    """List the tools advertised by an MCP server.

    COMMAND: the server launch command as a single quoted string, e.g.
    "python server.py", or a URL such as https://example.com/mcp
    (omit when using --config).
    """
    from toolscore.mcp.snapshot import ServerSnapshot, write_snapshot

    console = Console()
    client = _connect(command, config, server, headers, auth_env, protocol, timeout, console)

    try:
        with client:
            snapshot = ServerSnapshot.from_client(client, source=" ".join(command))
    except Exception as exc:  # surface any launch/protocol failure to the user
        print_error(f"Failed to query MCP server: {exc}", console)
        sys.exit(1)
    info, tools = snapshot.server_info, snapshot.tools
    protocol_version, era = snapshot.protocol_version, snapshot.era

    name = str(info.get("name", "unknown server"))
    version = str(info.get("version", ""))
    how = "stateless" if era == "modern" else "initialize handshake"
    console.print(
        f"\n[bold]{name}[/bold] [dim]{version}[/dim]  ({len(tools)} tools)  "
        f"[dim]MCP {protocol_version}, {how}[/dim]\n"
    )

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
    if json_out is not None:
        write_snapshot(json_out, snapshot)
        console.print(f"[dim]Snapshot written to {json_out}.[/dim]")


@mcp.command("record")
@click.argument("command", nargs=-1)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="MCP host config file with a stdio server entry (alternative to a command).",
)
@click.option("--server", default=None, help="Server name to select from --config.")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    required=True,
    help="Trace file to write (read it with --format mcp).",
)
def mcp_record(
    command: tuple[str, ...], config: Path | None, server: str | None, output: Path
) -> None:
    """Record real tool calls between an MCP client and a server.

    Put this command where your MCP client launches the server (for example in
    claude_desktop_config.json or your agent's MCP settings). It starts the
    server and relays every message unchanged, while writing each tools/call
    request with its result, error and duration to OUTPUT. Score the recording
    with: toolscore eval gold.json OUTPUT --format mcp

    Recording works for stdio servers; it is a stdio proxy.

    COMMAND: the server launch command as a single quoted string
    (omit when using --config).
    """
    # stdout carries the MCP protocol, so every message from us goes to stderr.
    console = Console(stderr=True)
    exit_code, recorder = _run_recorder(command, config, server, output, console)
    console.print(
        f"[dim]toolscore: recorded {recorder.calls_recorded} tool call(s) to {output}[/dim]"
    )
    # A server killed by a signal reports -N; shells report that as 128 + N.
    sys.exit(exit_code if exit_code >= 0 else 128 - exit_code)


def _run_recorder(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    output: Path,
    console: Console,
    injector: FaultInjector | None = None,
) -> tuple[int, MCPRecorder]:
    """Resolve a stdio server and relay one session through the recorder."""
    from toolscore.mcp.recorder import MCPRecorder

    spec = _resolve_mcp_target(command, config, server, console)
    if spec.url is not None:
        print_error(
            "The recorder is a stdio proxy and cannot relay a URL server; record the agent's "
            "calls from its own logs or traces instead (toolscore eval --format otel/openai/...).",
            console,
        )
        sys.exit(2)
    recorder = MCPRecorder(spec.command, output, env=spec.env or None, injector=injector)
    try:
        exit_code = recorder.run()
    except OSError as exc:
        print_error(f"Failed to launch MCP server {spec.command!r}: {exc}", console)
        sys.exit(1)
    return exit_code, recorder


@mcp.command("proxy")
@click.argument("command", nargs=-1)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="MCP host config file with a stdio server entry (alternative to a command).",
)
@click.option("--server", default=None, help="Server name to select from --config.")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    required=True,
    help="Session file to write (calls, results and the injected faults).",
)
@click.option(
    "--inject",
    "inject",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help=(
        "Fault spec (JSON or YAML): which tools and calls get an error, a JSON-RPC error, a "
        "warning, an empty or truncated result, a delay, a timeout, or a disabled / "
        "permission-denied answer. Without it the proxy only records."
    ),
)
def mcp_proxy(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    output: Path,
    inject: Path | None,
) -> None:
    """Relay an MCP stdio server, inject faults into chosen calls, and record the session.

    Put this command where your MCP client (Claude Code, Cursor, Claude
    Desktop, your agent) launches the server. Use the agent as usual. The
    session file records what the agent saw and which faults were injected,
    so the honesty checks can tell whether the agent disclosed them:

        toolscore honesty session.json --final-answer @answer.txt

    The proxy speaks stdio only; HTTP servers cannot be proxied.

    COMMAND: the server launch command (omit when using --config).
    """
    from toolscore.mcp.faults import FaultInjector, load_fault_spec

    console = Console(stderr=True)
    injector = None
    if inject is not None:
        try:
            injector = FaultInjector(load_fault_spec(inject))
        except ValueError as exc:
            print_error(f"Invalid fault spec: {exc}", console)
            sys.exit(2)
    exit_code, recorder = _run_recorder(command, config, server, output, console, injector)
    injected = len(recorder.injections)
    console.print(
        f"[dim]toolscore: recorded {recorder.calls_recorded} tool call(s), "
        f"{injected} with an injected fault, to {output}[/dim]"
    )
    sys.exit(exit_code if exit_code >= 0 else 128 - exit_code)


def _pin_options(func: Any) -> Any:
    """Add ``--pin LOCK`` and ``--pin-fail-on`` (verify the tools against a lock file)."""
    func = click.option(
        "--pin-fail-on",
        type=click.Choice(["drift", "capability", "never"]),
        default="drift",
        show_default=True,
        help="With --pin: what fails (any drift, only a new delete/exec capability, or never).",
    )(func)
    return click.option(
        "--pin",
        type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
        default=None,
        help="Also check the tools against this lock file (toolscore mcp pin); exit 1 on drift.",
    )(func)


@mcp.command("lint")
@click.argument("command", nargs=-1)
@_mcp_connection_options
@_pin_options
def mcp_lint(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    headers: tuple[str, ...],
    auth_env: str | None,
    protocol: str,
    timeout: float,
    pin: Path | None,
    pin_fail_on: str,
) -> None:
    """Statically lint an MCP server's tool definitions.

    Checks schemas, descriptions, behavior annotations (readOnlyHint,
    destructiveHint, ...), references to missing tools and tool-poisoning
    patterns. Each issue has a rule ID. Exits 1 if any error-severity issue is
    found.

    COMMAND: the server launch command as a single quoted string, or a URL
    (omit when using --config).
    """
    from toolscore.mcp import lint_tools

    console = Console()
    client = _connect(command, config, server, headers, auth_env, protocol, timeout, console)

    from toolscore.mcp.snapshot import ServerSnapshot

    try:
        with client:
            snapshot = ServerSnapshot.from_client(client, source=" ".join(command))
    except Exception as exc:  # surface any launch/protocol failure to the user
        print_error(f"Failed to query MCP server: {exc}", console)
        sys.exit(1)
    tools, instructions = snapshot.tools, snapshot.instructions

    pin_ok = True
    if pin is not None:
        from toolscore.commands.mcp_pin import check_pin

        pin_ok = check_pin(pin, snapshot, pin_fail_on, console).ok

    issues = lint_tools(tools, instructions=instructions)
    errors = sum(1 for i in issues if i.severity == "error")
    warnings = sum(1 for i in issues if i.severity == "warning")

    if not issues:
        console.print(f"\n[green]OK[/green] No lint issues across {len(tools)} tools.\n")
        if not pin_ok:
            sys.exit(1)
        return

    console.print(f"\n[bold]Lint:[/bold] {errors} errors, {warnings} warnings\n")
    table = Table(header_style="bold magenta")
    table.add_column("Severity")
    table.add_column("Tool", style="cyan")
    table.add_column("Rule", style="dim")
    table.add_column("Message")
    for issue in issues:
        color = "red" if issue.severity == "error" else "yellow"
        table.add_row(f"[{color}]{issue.severity}[/{color}]", issue.tool, issue.rule, issue.message)
    console.print(table)
    console.print()

    if errors or not pin_ok:
        sys.exit(1)


@mcp.command("test")
@click.argument("command", nargs=-1)
@_mcp_connection_options
@click.option("--cases", type=int, default=3, help="Happy-path scenarios per tool (default: 3).")
@click.option("--no-edge-cases", is_flag=True, default=False, help="Skip edge-case scenarios.")
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
    "--badge",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Write an SVG badge with this run's grade ('MCP grade: A · Toolscore').",
)
@click.option(
    "--badge-json",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Write a shields.io endpoint JSON file with this run's grade.",
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
@click.option(
    "--arg",
    "arg_options",
    multiple=True,
    metavar="[TOOL:]NAME=VALUE",
    help=(
        "A value the server accepts, used in every happy path (repeatable). NAME=VALUE applies "
        "to each tool with that parameter, TOOL:NAME=VALUE to one tool. VALUE is read as JSON "
        "when it parses (5, true, [1]), else as text. For servers limited to allowed roots: "
        "--arg path=/tmp/sandbox/notes.txt"
    ),
)
@click.option(
    "--args-file",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help='JSON or YAML file of argument values: {"*": {NAME: VALUE}, "TOOL": {NAME: VALUE}}.',
)
@click.option(
    "--probes",
    is_flag=True,
    default=False,
    help=(
        "Run effect probes: check that tools really did what they reported (bounds such as "
        "head/limit on read-only tools; with --allow-writes, round trips through read tools). "
        "High-confidence failures lower the score and cap the grade at C."
    ),
)
@click.option(
    "--allow-writes",
    is_flag=True,
    default=False,
    help=(
        "Let probes call write tools (create/add/update/...) and read the result back. They "
        "leave marker records behind: use a disposable server."
    ),
)
@click.option(
    "--probe-config",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help=(
        "JSON or YAML file declaring round-trip pairs, bound relations, agreements and argument "
        "values for the probes (implies --probes)."
    ),
)
@click.option(
    "--no-probe-grade-cap",
    is_flag=True,
    default=False,
    help=(
        "Do not cap the grade at C when a high-confidence probe fails (the score is the same "
        "either way)."
    ),
)
@_pin_options
def mcp_test(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    headers: tuple[str, ...],
    auth_env: str | None,
    protocol: str,
    timeout: float,
    cases: int,
    no_edge_cases: bool,
    report: str | None,
    output: Path | None,
    badge: Path | None,
    badge_json: Path | None,
    fail_under: str | None,
    ci: bool,
    arg_options: tuple[str, ...],
    args_file: Path | None,
    probes: bool,
    allow_writes: bool,
    probe_config: Path | None,
    no_probe_grade_cap: bool,
    pin: Path | None,
    pin_fail_on: str,
) -> None:
    """Run the full scorecard against an MCP server.

    Connects to the server, generates happy-path and edge-case scenarios from
    each tool's schema, executes them, checks results against declared output
    schemas, lints the definitions, and prints an A-F scorecard. With --probes
    it also checks that tools really did what they reported.

    The scenarios call every tool, write tools included, with generated
    values; point the command at a server you can safely write to.

    COMMAND: the server launch command as a single quoted string, e.g.
    "python server.py", or a URL such as https://example.com/mcp
    (omit when using --config).
    """
    from toolscore.mcp import (
        grade_meets,
        print_scorecard,
        scorecard_to_json,
        scorecard_to_markdown,
    )
    from toolscore.mcp.badge import badge_endpoint, badge_svg
    from toolscore.mcp.scorecard import score_server

    console = Console()

    valid_grades = {"A", "B", "C", "D", "F"}
    if fail_under is not None and fail_under.upper() not in valid_grades:
        print_error(f"--fail-under must be one of A-F, got {fail_under!r}.", console)
        sys.exit(2)

    if report is not None and output is None:
        print_error("--report requires --output PATH.", console)
        sys.exit(2)

    fixtures = _argument_fixtures(arg_options, args_file, console)
    probe_setting: ProbeConfig | bool = probes
    if probe_config is not None:
        from toolscore.mcp.probes import load_probe_config

        try:
            probe_setting = load_probe_config(probe_config)
        except ValueError as exc:
            print_error(f"Invalid probe config: {exc}", console)
            sys.exit(2)
    client = _connect(command, config, server, headers, auth_env, protocol, timeout, console)

    try:
        with client:
            card = score_server(
                client,
                cases_per_tool=cases,
                include_edge_cases=not no_edge_cases,
                fixtures=fixtures,
                probes=probe_setting,
                allow_writes=allow_writes,
                probe_grade_cap=not no_probe_grade_cap,
            )
    except Exception as exc:  # surface any launch/protocol failure to the user
        print_error(f"Failed to test MCP server: {exc}", console)
        sys.exit(1)

    wrote_file = False
    if report is not None and output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        if report == "json":
            output.write_text(json.dumps(scorecard_to_json(card), indent=2), encoding="utf-8")
        else:
            output.write_text(scorecard_to_markdown(card), encoding="utf-8")
        name = str(card.server_info.get("name", "server"))
        capped = f", {card.grade_cap_note}" if card.grade_capped else ""
        console.print(
            f"[bold]{name}[/bold] -> Grade [bold]{card.grade}[/bold] "
            f"(score {card.score:.0%}{capped}). Report written to [cyan]{output}[/cyan]."
        )
        wrote_file = True

    badge_notes: list[str] = []
    for path, content in (
        (badge, badge_svg(card.grade, card.grade_cap_note) if badge else ""),
        (
            badge_json,
            json.dumps(badge_endpoint(card.grade, card.grade_cap_note), ensure_ascii=False) + "\n",
        ),
    ):
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            capped = f", {card.grade_cap_note}" if card.grade_capped else ""
            badge_notes.append(f"[dim]Badge (grade {card.grade}{capped}) written to {path}.[/dim]")

    # Always show the console scorecard unless a file report was the only output.
    if ci or not wrote_file:
        print_scorecard(card, console=console)
    for note in badge_notes:
        console.print(note)

    if ci:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with Path(summary_path).open("a", encoding="utf-8") as handle:
                handle.write(scorecard_to_markdown(card) + "\n")
            console.print("[dim]Wrote the scorecard to the GitHub Actions job summary.[/dim]")

    if pin is not None:
        from toolscore.commands.mcp_pin import check_pin
        from toolscore.mcp.snapshot import ServerSnapshot

        snapshot = ServerSnapshot(
            tools=card.tools,
            server_info=card.server_info,
            protocol_version=card.protocol_version,
            era=card.era,
            instructions=card.instructions,
        )
        if not check_pin(pin, snapshot, pin_fail_on, console, ci=ci).ok:
            console.print(f"[red]The server drifted from {pin}.[/red]")
            sys.exit(1)

    if fail_under is not None and not grade_meets(card.grade, fail_under):
        console.print(f"[red]Grade {card.grade} is below the required {fail_under.upper()}.[/red]")
        sys.exit(1)

    if ci and fail_under is None:
        # Default CI gate: fail on real problems (a tool that breaks on valid
        # input, an edge-case crash, a schema error, or a high-confidence probe
        # failure) -- but not on warnings.
        has_blocking = (
            card.lint_error_count > 0
            or card.probe_error_count > 0
            or any(not r.ok for r in card.results)
        )
        if has_blocking:
            console.print("[red]Blocking issues found (see 'Top issues to fix' above).[/red]")
            sys.exit(1)


@main.command("demo")
@click.option(
    "--truth",
    is_flag=True,
    default=False,
    help=(
        "Show the truth checks instead: effect probes catch a sample tool that reports "
        "success and stores nothing, and the honesty check catches an agent that overrides "
        "a disabled button and reports success."
    ),
)
@click.pass_context
def demo(ctx: click.Context, truth: bool) -> None:
    """Health-check a bundled sample MCP server -- zero setup, no API key.

    Launches a small sample MCP server that ships with toolscore (one with a few
    deliberate issues) and prints the same scorecard that ``toolscore mcp test``
    produces, so you can see the instant verdict in seconds.

    With --truth, the sample server runs with a silent-no-op bug and the effect
    probes check that its writes really happened; then the honesty check reads a
    bundled agent trace and compares what the tools returned with what the agent
    told the user. Everything runs locally and calls no model.
    """
    from toolscore.mcp import MCPStdioClient, print_scorecard
    from toolscore.mcp.scorecard import score_server

    console = Console()
    sample_server = Path(__file__).resolve().parent / "mcp" / "sample_server.py"
    if not sample_server.is_file():
        print_error(f"Bundled sample server not found at {sample_server}.", console)
        sys.exit(1)

    command = [sys.executable, str(sample_server)]
    if truth:
        command += ["--bug", "silent-skip"]
        console.print(
            "[bold]toolscore demo --truth[/bold] - did the tool really do it, and did the agent "
            "tell the truth about it?\n\n"
            "[bold]1. A tool that reports success and does nothing.[/bold] The sample server "
            "runs with a bug: [cyan]create_note[/cyan] on an existing title says it saved the "
            "note and changes nothing. Effect probes write marked notes, write again to the "
            "same title and read them back (they run only against this disposable server).\n"
        )
    else:
        console.print(
            "[bold]toolscore demo[/bold] - grading a bundled sample MCP server "
            "(no setup, no API key).\n"
        )

    try:
        with MCPStdioClient(command, timeout=30.0) as client:
            card = score_server(
                client,
                cases_per_tool=3,
                include_edge_cases=True,
                probes=truth,
                allow_writes=truth,
            )
    except Exception as exc:  # surface any launch/protocol failure to the user
        print_error(f"Failed to run the sample server: {exc}", console)
        sys.exit(1)

    print_scorecard(card, console=console)
    if not truth:
        console.print(
            "\n[dim]That's the health-check. Now point it at your own server:[/dim] "
            '[bold]toolscore mcp test "python your_server.py"[/bold]'
            "\n[dim]See the truth checks:[/dim] [bold]toolscore demo --truth[/bold]"
        )
        return

    trace = Path(__file__).resolve().parent / "templates" / "demo" / "disabled_button.json"
    console.print(
        "\n[bold]2. An agent that reports success after a tool refused.[/bold] A browser "
        "agent's trace: the order button is disabled, the agent enables it with JavaScript, "
        "clicks it and tells the user the order was placed."
    )
    ctx.invoke(
        honesty,
        trace_file=trace,
        format="auto",
        gold=None,
        final_answer=None,
        injected=None,
        config_path=None,
        json_path=None,
        fail_on_findings=False,
        label="browser agent trace (bundled)",
    )
    console.print(
        "[dim]Now check your own:[/dim] "
        '[bold]toolscore mcp test "python your_server.py" --probes[/bold] '
        "[dim](add --allow-writes only for a disposable server) and[/dim] "
        "[bold]toolscore honesty your_trace.json[/bold]"
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
    type=click.Choice(
        ["auto", "openai", "anthropic", "gemini", "mcp", "langchain", "otel", "custom"]
    ),
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


def _register_commands() -> None:
    from toolscore.commands import register

    register(main, mcp)


_register_commands()


if __name__ == "__main__":
    main()
