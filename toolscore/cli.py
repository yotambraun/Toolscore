"""Command-line interface for Toolscore."""

import json
import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from toolscore import __version__
from toolscore.comparison import (
    compare_models,
    print_comparison_table,
    save_comparison_report,
)
from toolscore.core import evaluate_trace
from toolscore.debug import run_interactive_debug
from toolscore.generators import generate_from_openai_schema
from toolscore.generators.synthetic import save_gold_standard
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
    "--llm-judge",
    is_flag=True,
    default=False,
    help="Use LLM-as-a-judge for semantic evaluation (requires OpenAI API key)",
)
@click.option(
    "--llm-model",
    type=str,
    default="gpt-4o-mini",
    help="Model to use for LLM judge (default: gpt-4o-mini)",
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
def eval(
    gold_file: Path,
    trace_file: Path,
    format: str,
    output: Path,
    html: Path | None,
    no_side_effects: bool,
    llm_judge: bool,
    llm_model: str,
    verbose: bool,
    debug: bool,
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
            use_llm_judge=llm_judge,
            llm_judge_model=llm_model,
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

        # Interactive debug mode for failures
        if debug:
            run_interactive_debug(result, console=console)

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


@main.command()
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Output directory (default: current directory)",
)
def init(output_dir: Path | None) -> None:
    """Initialize a new Toolscore evaluation project.

    Creates gold standard template and example files to get started quickly.
    """
    console = Console()

    console.print("\n[bold cyan]🚀 Toolscore Quickstart[/bold cyan]\n")

    # Agent types with their template files
    agent_types = {
        "1": {
            "name": "Weather/API lookup",
            "file": "weather_agent.json",
            "complexity": "⭐ Beginner",
            "desc": "Simple API calls with basic parameters",
        },
        "2": {
            "name": "E-commerce/Shopping",
            "file": "ecommerce_agent.json",
            "complexity": "⭐⭐ Intermediate",
            "desc": "Multi-step workflow with cart management",
        },
        "3": {
            "name": "Code assistant",
            "file": "code_assistant.json",
            "complexity": "⭐⭐ Intermediate",
            "desc": "Code search, read, edit, and test execution",
        },
        "4": {
            "name": "RAG/Search agent",
            "file": "rag_agent.json",
            "complexity": "⭐⭐⭐ Advanced",
            "desc": "Vector search, reranking, generation, citations",
        },
        "5": {
            "name": "Multi-tool workflow",
            "file": "multi_tool_agent.json",
            "complexity": "⭐⭐⭐ Advanced",
            "desc": "Complex research and documentation workflow",
        },
    }

    # Display options table
    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("#", style="cyan", width=3)
    table.add_column("Agent Type", style="green")
    table.add_column("Complexity", style="yellow")
    table.add_column("Description", style="dim")

    for key, info in agent_types.items():
        table.add_row(key, info["name"], info["complexity"], info["desc"])

    console.print(table)
    console.print()

    # Get user choice
    choice = Prompt.ask(
        "What type of agent are you testing?",
        choices=list(agent_types.keys()),
        default="1",
    )

    selected = agent_types[choice]

    # Determine output directory
    if output_dir is None:
        output_dir = Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find the package directory to copy templates from
    try:
        import toolscore

        package_dir = Path(toolscore.__file__).parent.parent
        template_dir = package_dir / "examples" / "datasets"
        template_file = template_dir / selected["file"]

        if not template_file.exists():
            print_error(f"Template file not found: {template_file}", console)
            sys.exit(1)

        # Copy gold standard template
        gold_output = output_dir / "gold_calls.json"
        shutil.copy(template_file, gold_output)

        console.print(f"\n[green]✅ Created:[/green] {gold_output.name}")
        console.print(f"   [dim]Template: {selected['name']}[/dim]")

        # Create example trace (empty but valid)
        example_trace = output_dir / "example_trace.json"
        example_trace.write_text("[]")
        console.print(f"[green]✅ Created:[/green] {example_trace.name}")
        console.print("   [dim]Empty trace - replace with your agent's output[/dim]")

        # Create README
        readme_content = f"""# Toolscore Evaluation Project

## Agent Type: {selected['name']}
**Complexity:** {selected['complexity']}
**Description:** {selected['desc']}

## Quick Start

1. **Capture your agent's trace:**
   - Run your agent and save tool calls to `my_trace.json`
   - See examples at: https://github.com/yotambraun/toolscore/tree/main/examples

2. **Run evaluation:**
   ```bash
   toolscore eval gold_calls.json my_trace.json --html report.html
   ```

3. **View results:**
   - Console output shows key metrics
   - Open `report.html` for detailed analysis

## Advanced Usage

### With LLM Judge (semantic matching):
```bash
toolscore eval gold_calls.json my_trace.json --llm-judge
```

### Verbose output (see missing/extra tools):
```bash
toolscore eval gold_calls.json my_trace.json --verbose
```

### Compare multiple models:
```bash
toolscore eval gold_calls.json gpt4_trace.json --html gpt4.html
toolscore eval gold_calls.json claude_trace.json --html claude.html
```

## Files

- `gold_calls.json` - Expected tool calls (gold standard)
- `example_trace.json` - Replace with your agent's actual trace
- `README.md` - This file

## Need Help?

- 📖 Documentation: https://toolscore.readthedocs.io/
- 🎓 Tutorial: https://github.com/yotambraun/toolscore/blob/main/TUTORIAL.md
- 💬 Issues: https://github.com/yotambraun/toolscore/issues

## Next Steps

1. Review `gold_calls.json` and customize for your use case
2. Capture your agent's tool calls to a JSON file
3. Run `toolscore eval` and iterate!
"""

        readme_file = output_dir / "README.md"
        readme_file.write_text(readme_content)
        console.print(f"[green]✅ Created:[/green] {readme_file.name}")
        console.print("   [dim]Getting started guide[/dim]")

        # Success message with next steps
        console.print("\n[bold green]🎉 Project initialized successfully![/bold green]\n")

        console.print("[bold]Try it now:[/bold]")
        console.print(f"  [cyan]cd {output_dir}[/cyan]")
        console.print("  [cyan]toolscore eval gold_calls.json example_trace.json[/cyan]")
        console.print()

        console.print("[bold]Next steps:[/bold]")
        console.print("  1. Review and customize [cyan]gold_calls.json[/cyan]")
        console.print("  2. Capture your agent's trace to a JSON file")
        console.print("  3. Run evaluation and see results!")
        console.print()

    except Exception as e:
        print_error(f"Failed to initialize project: {e}", console)
        sys.exit(1)


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
    type=click.Choice(["auto", "openai", "anthropic", "langchain", "custom"]),
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
                use_llm_judge=False,  # Skip LLM judge for speed
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


if __name__ == "__main__":
    main()
