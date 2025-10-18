"""Command-line interface for Toolscore."""

import shutil
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

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


if __name__ == "__main__":
    main()
