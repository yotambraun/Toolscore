"""``toolscore agent run``: run an agent study against an MCP server."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from toolscore.reports import print_error


@click.group("agent")
def agent() -> None:
    """Run LLM agents against MCP servers and record every run (agent harness)."""


def _usd(value: float | None) -> str:
    return "unknown" if value is None else f"${value:.4f}"


@agent.command("run")
@click.argument("spec_file", type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="JSONL output, one row per run (default: the spec's output, else <name>.runs.jsonl).",
)
@click.option("--max-runs", type=int, default=None, help="Stop after this many new runs.")
@click.option(
    "--retry-errors", is_flag=True, default=False, help="Run errored cells again when resuming."
)
@click.option(
    "--allow-unknown-price",
    is_flag=True,
    default=False,
    help="Run models without a known price (their cost is unknown; the budget cannot cap them).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the cells, prices and a worst-case cost; call nothing.",
)
def agent_run(
    spec_file: Path,
    output: Path | None,
    max_runs: int | None,
    retry_errors: bool,
    allow_unknown_price: bool,
    dry_run: bool,
) -> None:
    """Run every task x arm x repetition of SPEC_FILE and append one JSONL row per run.

    The order is shuffled with the spec's seed; a study that stops (budget,
    --max-runs, Ctrl-C) resumes where it left off. The budget is checked
    before every model call; a model without a known price is refused unless
    allowed. Real providers cost money: start with --dry-run and
    `toolscore doctor --spec SPEC_FILE`.

    SPEC_FILE: YAML or JSON (see the "Agent harness" docs).
    """
    from toolscore.mcp.agent import (
        BuildMismatchError,
        UnknownPriceError,
        estimate_study_cost,
        load_agent_spec,
        preflight_prices,
        run_study,
    )

    console = Console()
    try:
        spec = load_agent_spec(spec_file)
        prices = preflight_prices(spec, allow_unknown_price)
    except UnknownPriceError as exc:
        print_error(str(exc), console)
        sys.exit(2)
    except (OSError, ValueError) as exc:
        print_error(f"Invalid agent spec: {exc}", console)
        sys.exit(2)

    cells = spec.cells()
    estimate = estimate_study_cost(spec, prices)
    console.print(
        f"[bold]{escape(spec.name)}[/bold]: {len(spec.tasks)} task(s) x {len(spec.arms)} arm(s) x "
        f"{spec.repetitions} repetition(s) = {len(cells)} run(s), seed {spec.seed}"
    )
    for arm in spec.arms:
        price = prices.get(arm.id)
        shown = (
            "unknown" if price is None else f"${price.input}/{price.output} per 1M ({price.source})"
        )
        console.print(f"  arm {escape(arm.id)}: {arm.provider} {escape(arm.model)}, price {shown}")
    console.print(
        f"  worst case {_usd(estimate['total_usd'])} (max_turns {spec.limits.max_turns}, "
        f"budget max_usd {estimate['max_usd'] if estimate['max_usd'] is not None else 'none'})"
    )
    if dry_run:
        for order, (task, arm, rep) in enumerate(cells, start=1):
            console.print(f"  {order:>3}. {escape(task.id)}::{escape(arm.id)}::{rep}")
        console.print("[dim]Dry run: nothing was called.[/dim]")
        return

    def progress(row: dict[str, Any]) -> None:
        style = {"pass": "green", "fail": "red", "error": "red"}.get(row["outcome"], "yellow")
        denied = f", {len(row['guard_denials'])} denied" if row["guard_denials"] else ""
        console.print(
            f"  {row['order']:>3}. {escape(row['cell_id'])}: [{style}]{row['outcome']}[/{style}] "
            f"({row['status']}, {len(row['calls'])} call(s){denied}, {_usd(row['cost_usd'])})"
        )

    try:
        result = run_study(
            spec,
            output=output,
            max_runs=max_runs,
            retry_errors=retry_errors,
            allow_unknown_price=allow_unknown_price,
            on_row=progress,
        )
    except BuildMismatchError as exc:
        print_error(f"Build verification failed: {exc}", console)
        sys.exit(2)
    except ImportError as exc:
        print_error(str(exc), console)
        sys.exit(2)

    table = Table(title="Outcomes (this invocation)", header_style="bold magenta")
    table.add_column("Arm")
    for outcome in ("pass", "fail", "error", "unknown"):
        table.add_column(outcome, justify="right")
    for arm in spec.arms:
        rows = [r for r in result.rows if r["arm_id"] == arm.id]
        table.add_row(
            escape(arm.id), *(str(sum(1 for r in rows if r["outcome"] == o)) for o in
                             ("pass", "fail", "error", "unknown"))
        )  # fmt: skip
    console.print(table)
    unknown = (
        f", {result.unknown_cost_turns} model call(s) with unknown cost"
        if result.unknown_cost_turns
        else ""
    )
    console.print(
        f"Wrote {len(result.rows)} run(s) to [cyan]{result.output}[/cyan]"
        f" ({result.skipped} already done); spent ${result.spent_usd:.4f}{unknown}."
    )
    console.print(
        f"[dim]Next: toolscore compare --runs {result.output}  |  "
        f"toolscore export --format aef {result.output}[/dim]"
    )
    if result.stopped == "budget":
        print_error("Stopped: the next model call could exceed the budget (max_usd).", console)
        sys.exit(3)
