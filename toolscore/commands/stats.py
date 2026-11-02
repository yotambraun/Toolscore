"""``toolscore compare --runs`` / ``--variant`` and ``toolscore select``."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from toolscore.reports import print_error

if TYPE_CHECKING:
    from toolscore.stats import Comparison, ProtocolResult, Run, Selection


def _pct(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.0%}"


def load_run_sources(
    runs_files: tuple[Path, ...],
    variants: tuple[str, ...],
    gold: Path | None,
    variant_key: str | None,
    min_score: float,
    console: Console,
) -> list[Run]:
    """Runs from JSONL files and ``NAME=DIR`` trace directories (exit 2 on bad input)."""
    from toolscore.stats import load_runs, runs_from_traces

    runs: list[Run] = []
    try:
        runs.extend(load_runs(runs_files, variant_key))
    except (OSError, ValueError) as exc:
        print_error(str(exc), console)
        sys.exit(2)
    for item in variants:
        name, sep, directory = item.partition("=")
        if not sep or not name or not Path(directory).is_dir():
            print_error(f"--variant expects NAME=DIR with an existing DIR, got {item!r}", console)
            sys.exit(2)
        if gold is None:
            print_error(
                "--variant NAME=DIR needs the GOLD_FILE argument to score the traces", console
            )
            sys.exit(2)
        runs.extend(runs_from_traces(name, directory, gold, min_score=min_score))
    if not runs:
        print_error("No runs found.", console)
        sys.exit(2)
    return runs


def print_comparison(comparison: Comparison, console: Console) -> None:
    """Print the per-variant table and the pairwise verdicts."""
    table = Table(title="Runs per variant", header_style="bold magenta")
    for column in ("Variant", "N", "pass", "fail", "error", "unknown"):
        table.add_column(column, justify="left" if column == "Variant" else "right")
    table.add_column("Pass rate [95% CI]", justify="right")
    table.add_column(f"pass^{comparison.k}", justify="right")
    table.add_column("Mean cost", justify="right")
    table.add_column("Mean latency", justify="right")
    for v in comparison.variants:
        low, high = v.interval
        cost = "unknown" if v.cost is None else f"${v.cost:.4f}"
        if v.cost is not None and v.cost_known < v.n:
            cost += f" ({v.cost_known}/{v.n})"
        latency = "unknown" if v.latency is None else f"{v.latency:.2f}s"
        if v.latency is not None and v.latency_known < v.n:
            latency += f" ({v.latency_known}/{v.n})"
        table.add_row(
            escape(v.variant),
            str(v.n),
            str(v.counts["pass"]),
            str(v.counts["fail"]),
            str(v.counts["error"]),
            str(v.counts["unknown"]),
            f"{_pct(v.pass_rate)} [{low:.0%}, {high:.0%}]",
            _pct(v.pass_hat_k),
            cost,
            latency,
        )
    console.print(table)
    if comparison.pairs:
        pairs = Table(title="Pass-rate differences", header_style="bold magenta")
        pairs.add_column("A")
        pairs.add_column("B")
        pairs.add_column("B - A", justify="right")
        pairs.add_column("Fisher p", justify="right")
        pairs.add_column("Verdict")
        for pair in comparison.pairs:
            diff = "unknown" if pair.difference is None else f"{pair.difference:+.0%}"
            style = "green" if pair.distinguishable else "yellow"
            pairs.add_row(
                escape(pair.a),
                escape(pair.b),
                diff,
                f"{pair.p_value:.3f}",
                f"[{style}]{escape(pair.verdict)}[/{style}]",
            )
        console.print(pairs)
    for note in comparison.notes:
        console.print(f"[dim]{note}[/dim]")
    console.print(
        "[dim]Light statistics for quick checks; for a full study (design, pre-registration, "
        "grading, reports) use Agent Eval Flow.[/dim]"
    )


def print_protocol(result: ProtocolResult, console: Console) -> None:
    """Print the evaluated protocol rules and the decision."""
    table = Table(title=f"Protocol {escape(result.title)}".strip(), header_style="bold magenta")
    table.add_column("Rule")
    table.add_column("Status")
    table.add_column("Detail")
    for rule in result.rules:
        style = {"pass": "green", "fail": "red"}.get(rule.status, "yellow")
        table.add_row(escape(rule.id), f"[{style}]{rule.status}[/{style}]", escape(rule.detail))
    console.print(table)
    style = {"adopt": "green", "reject": "red"}.get(result.decision, "yellow")
    console.print(
        f"Decision ({escape(result.candidate)} vs {escape(result.baseline)}): "
        f"[bold {style}]{result.decision}[/bold {style}]  "
        f"[dim]protocol sha256 {result.protocol_sha256[:12]}...[/dim]"
    )


def run_compare(
    runs_files: tuple[Path, ...],
    variants: tuple[str, ...],
    gold: Path | None,
    variant_key: str | None,
    k: int,
    baseline: str | None,
    min_n: int,
    alpha: float,
    min_score: float,
    protocol: Path | None,
    json_out: Path | None,
) -> None:
    """The runs mode of ``toolscore compare``."""
    from toolscore.stats import compare_runs, evaluate_protocol, load_protocol

    console = Console()
    runs = load_run_sources(runs_files, variants, gold, variant_key, min_score, console)
    try:
        comparison = compare_runs(runs, k=k, baseline=baseline, min_n=min_n, alpha=alpha)
    except ValueError as exc:
        print_error(str(exc), console)
        sys.exit(2)
    print_comparison(comparison, console)
    report = comparison.to_dict()
    exit_code = 0
    if protocol is not None:
        try:
            result = evaluate_protocol(load_protocol(protocol), comparison)
        except (OSError, ValueError) as exc:
            print_error(f"Invalid protocol: {exc}", console)
            sys.exit(2)
        print_protocol(result, console)
        report["protocol"] = result.to_dict()
        exit_code = 1 if result.decision == "reject" else 0
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    sys.exit(exit_code)


def print_selection(selection: Selection, console: Console) -> None:
    """Print the chosen variant, the ranking and the Pareto front."""
    objectives = ", ".join(f"{o.metric}:{o.direction}" for o in selection.objectives)
    console.print(f"[bold]Policy[/bold] {selection.policy}  [dim]({objectives})[/dim]")
    console.print(f"Ranking: {escape(' > '.join(selection.ranking))}")
    if selection.scores:
        console.print(
            "Weighted scores: "
            + escape(", ".join(f"{k} {v:.3f}" for k, v in selection.scores.items()))
        )
    console.print(f"Pareto front: {escape(', '.join(selection.pareto_front))}")
    for name, metrics in selection.unknown.items():
        console.print(
            f"[yellow]{escape(name)}: {', '.join(metrics)} unknown (ranked worst)[/yellow]"
        )
    console.print(
        f"[bold green]Selected: {escape(selection.chosen or '(none)')}[/bold green] "
        f"[dim]({escape(selection.reason)})[/dim]"
    )


@click.command("select")
@click.argument("gold_file", required=False, type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.option(
    "--runs",
    "runs_files",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    help="JSONL file of runs (toolscore agent run output or an export); repeatable.",
)
@click.option(
    "--variant",
    "variants",
    multiple=True,
    metavar="NAME=DIR",
    help="A directory of trace files for one variant, scored against GOLD_FILE; repeatable.",
)
@click.option(
    "--variant-key", default=None, help="JSONL field naming the variant (default arm_id)."
)
@click.option(
    "--policy",
    type=click.Choice(["lexicographic", "weighted", "pareto"]),
    default="lexicographic",
    show_default=True,
)
@click.option(
    "--objective",
    "objectives",
    multiple=True,
    metavar="METRIC[:max|min]",
    help=(
        "Objective, in priority order (repeatable; default pass_rate:max, cost:min, "
        "latency:min). Metrics: pass_rate, pass_lower, pass_hat_k, cost, latency, error_rate, "
        "unknown_rate."
    ),
)
@click.option(
    "--weight", "weights", multiple=True, metavar="METRIC=W", help="Weight (weighted policy)."
)
@click.option("--k", "k", type=int, default=1, show_default=True, help="k of pass^k.")
@click.option(
    "--min-score", type=float, default=0.9, show_default=True, help="Passing score for traces."
)
@click.option(
    "--json",
    "json_out",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Write the selection as JSON.",
)
def select(
    gold_file: Path | None,
    runs_files: tuple[Path, ...],
    variants: tuple[str, ...],
    variant_key: str | None,
    policy: str,
    objectives: tuple[str, ...],
    weights: tuple[str, ...],
    k: int,
    min_score: float,
    json_out: Path | None,
) -> None:
    """Pick a variant by lexicographic, weighted or Pareto objectives.

    Reads the same runs as `toolscore compare --runs` (or trace directories
    with --variant NAME=DIR and GOLD_FILE), then ranks the variants on the
    objectives (pass rate, cost, latency...). Unknown values (a variant
    without costs) rank worst and are reported. Always prints the Pareto front.

    Example:

        toolscore select --runs runs.jsonl --policy pareto \\
            --objective pass_rate:max --objective cost:min
    """
    from toolscore.stats import compare_runs, select_variant

    console = Console()
    runs = load_run_sources(runs_files, variants, gold_file, variant_key, min_score, console)
    parsed_weights: dict[str, float] = {}
    for item in weights:
        name, sep, value = item.partition("=")
        try:
            parsed_weights[name.strip()] = float(value)
        except ValueError:
            sep = ""
        if not sep:
            print_error(f"--weight expects METRIC=W, got {item!r}", console)
            sys.exit(2)
    try:
        selection = select_variant(
            compare_runs(runs, k=k),
            policy=policy,
            objectives=list(objectives) or None,
            weights=parsed_weights,
        )
    except ValueError as exc:
        print_error(str(exc), console)
        sys.exit(2)
    print_selection(selection, console)
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(selection.to_dict(), indent=2) + "\n", encoding="utf-8")
