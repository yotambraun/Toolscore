"""``toolscore regrade``: re-score saved traces without re-running anything."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from toolscore.reports import print_error


def _parse_weights(overrides: tuple[str, ...]) -> dict[str, float] | None:
    from toolscore.cli import _parse_weights as parse

    return parse(overrides)


@click.command("regrade")
@click.argument("sources", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.option(
    "--gold",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="New gold file or contract (default: the one in each receipt; required for bare traces).",
)
@click.option(
    "--weight",
    "weight_overrides",
    multiple=True,
    metavar="NAME=VALUE",
    help="New score weight (repeatable), e.g. --weight required_call_recall=0.3.",
)
@click.option(
    "--forbidden",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Forbidden-call rules (default: the receipt's, if any).",
)
@click.option(
    "--format",
    "trace_format",
    default=None,
    help="Trace format (default: the receipt's, else auto).",
)
@click.option(
    "--receipt-dir",
    type=click.Path(file_okay=False, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Write a new receipt per source into this directory (<source stem>.receipt.json).",
)
@click.option(
    "--json",
    "json_out",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Write the before/after table as JSON.",
)
@click.option(
    "--no-verify",
    is_flag=True,
    default=False,
    help="Regrade even when a receipt's inputs changed (the problems are still reported).",
)
def regrade(
    sources: tuple[Path, ...],
    gold: Path | None,
    weight_overrides: tuple[str, ...],
    forbidden: Path | None,
    trace_format: str | None,
    receipt_dir: Path | None,
    json_out: Path | None,
    no_verify: bool,
) -> None:
    """Re-score saved traces with a new contract or weights, without re-running anything.

    Record once, re-score forever. SOURCES are receipts written by
    `toolscore eval --receipt` (their trace, gold and weights are the defaults,
    and the trace must still match the receipt's hash) or trace files (with
    --gold). Prints the score and grade before and after.

    Example:

        toolscore regrade run.receipt.json --gold contract-v2.json
    """
    from toolscore.receipts import ReceiptMismatchError, write_receipt
    from toolscore.receipts import regrade as do_regrade

    console = Console()
    weights = _parse_weights(weight_overrides)
    rows: list[dict[str, object]] = []
    failed = 0
    for source in sources:
        try:
            outcome = do_regrade(
                source,
                gold=gold,
                weights=weights,
                forbidden=forbidden,
                format=trace_format,
                verify=not no_verify,
            )
        except ReceiptMismatchError as exc:
            print_error(f"{source}: not regraded, {exc}", console)
            failed += 1
            continue
        except (ValueError, FileNotFoundError) as exc:
            print_error(f"{source}: {exc}", console)
            failed += 1
            continue
        for problem in outcome.problems or []:
            console.print(f"[yellow]warning[/yellow] {source}: {problem}")
        receipt_path = None
        if receipt_dir is not None:
            receipt_path = write_receipt(
                receipt_dir / f"{source.stem}.receipt.json", outcome.receipt
            )
        previous = outcome.previous or {}
        rows.append(
            {
                "source": str(source),
                "before_score": previous.get("score"),
                "before_grade": previous.get("grade"),
                "after_score": outcome.result.score,
                "after_grade": outcome.result.grade,
                "delta": outcome.score_delta,
                "receipt": str(receipt_path) if receipt_path else None,
            }
        )

    if rows:
        table = Table(title="Regrade", header_style="bold magenta")
        table.add_column("Source", style="cyan")
        table.add_column("Before", justify="right")
        table.add_column("After", justify="right")
        table.add_column("Change", justify="right")
        for row in rows:
            before = (
                f"{row['before_score']:.1%} {row['before_grade']}"
                if isinstance(row["before_score"], (int, float))
                else "unknown"
            )
            delta = row["delta"]
            change = f"{delta:+.1%}" if isinstance(delta, float) else "n/a"
            table.add_row(
                str(row["source"]),
                before,
                f"{row['after_score']:.1%} {row['after_grade']}",
                change,
            )
        console.print(table)
        console.print("[dim]Nothing was re-run: same traces, new contract or weights.[/dim]")
    if json_out is not None:
        json_out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    if failed:
        sys.exit(1)
