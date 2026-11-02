"""``toolscore export``: neutral, versioned run records for evaluation frameworks."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from toolscore.reports import print_error


@click.command("export")
@click.argument("inputs", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))  # type: ignore[type-var]
@click.option(
    "--format",
    "export_format",
    type=click.Choice(["aef"]),
    default="aef",
    show_default=True,
    help="aef: the neutral toolscore.run-record v1 schema, ready for Agent Eval Flow and others.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default="toolscore-runs.jsonl",
    show_default=True,
    help="JSONL output; a <output>.manifest.json with hashes is written next to it.",
)
@click.option(
    "--gold",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Gold file or contract to evaluate trace inputs against (receipts carry their own).",
)
@click.option("--variant", default="", help="Variant name for trace and receipt inputs.")
@click.option(
    "--min-score", type=float, default=0.9, show_default=True, help="Passing score for traces."
)
def export(
    inputs: tuple[Path, ...],
    export_format: str,
    output: Path,
    gold: Path | None,
    variant: str,
    min_score: float,
) -> None:
    """Export runs as one JSON record per run, in a documented, versioned schema.

    INPUTS are `toolscore agent run` JSONL files, trace files (any supported
    format) or receipts (`toolscore eval --receipt`). Each record has the
    requested and completed calls correlated by call_id, explicit unknown
    coverage (results, durations, cost, final answer), the evaluation and
    SHA-256 hashes; the manifest lists the sources and the output's hash.
    The schema ships as toolscore/schemas/run-record-v1.schema.json.
    """
    from toolscore.export import export_records, write_export

    del export_format  # one format today; the option keeps the CLI stable
    console = Console()
    try:
        records = export_records(inputs, gold=gold, variant=variant, min_score=min_score)
    except (OSError, ValueError) as exc:
        print_error(f"Cannot export: {exc}", console)
        sys.exit(2)
    path, manifest = write_export(output, records, inputs)
    unknown = sum(1 for r in records if r["coverage"]["unknown"])
    console.print(
        f"Wrote {len(records)} run record(s) to [cyan]{path}[/cyan] "
        f"(schema toolscore.run-record v1; {unknown} with unknown coverage) "
        f"and [cyan]{manifest}[/cyan]."
    )
