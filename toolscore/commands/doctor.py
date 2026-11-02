"""``toolscore doctor``: preflight checks before any paid call."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from toolscore.reports import print_error

_STYLES = {"pass": "green", "warn": "yellow", "fail": "red", "unknown": "yellow", "skip": "dim"}


@click.command("doctor")
@click.option(
    "--spec",
    "spec_file",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Agent spec: packages, API keys (names only), server, build, prices and budget.",
)
@click.option(
    "--contract",
    "contract_file",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Contract or gold file to validate.",
)
@click.option(
    "--server",
    "server_target",
    default=None,
    help="An MCP server to start and list (a quoted command or a URL), without a spec.",
)
@click.option(
    "--key",
    "keys",
    multiple=True,
    metavar="NAME",
    help="Environment variable that must be set (repeatable); only its presence is shown.",
)
@click.option(
    "--allow-unknown-price",
    is_flag=True,
    default=False,
    help="Treat models without a known price as a warning, as `agent run` would.",
)
@click.option("--no-server", is_flag=True, default=False, help="Do not start the spec's server.")
@click.option(
    "--json",
    "json_out",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Write the checks as JSON.",
)
def doctor(
    spec_file: Path | None,
    contract_file: Path | None,
    server_target: str | None,
    keys: tuple[str, ...],
    allow_unknown_price: bool,
    no_server: bool,
    json_out: Path | None,
) -> None:
    """Check everything a run needs before any paid call; exit 1 if a check fails.

    Checks the Python and Toolscore versions, the optional packages a spec
    needs, API keys by name (never their values), the spec and contract
    files, that the MCP server starts (protocol, tool count, build against the
    spec's verify), that every model has a known price, and the worst-case
    cost of the study against its budget. Calls no model.

    Example:

        toolscore doctor --spec study.yaml --contract contract.json
    """
    from toolscore.doctor import doctor_report, run_doctor

    console = Console()
    server = None
    if server_target:
        from toolscore.cli import _resolve_mcp_target

        server = _resolve_mcp_target((server_target,), None, None, console)
    checks = run_doctor(
        spec_path=spec_file,
        contract_path=contract_file,
        server=server,
        keys=list(keys),
        allow_unknown_price=allow_unknown_price,
        start_server=not no_server,
    )
    table = Table(title="toolscore doctor", header_style="bold magenta")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Detail")
    for check in checks:
        style = _STYLES.get(check.status, "white")
        table.add_row(
            escape(check.name), f"[{style}]{check.status}[/{style}]", escape(check.detail)
        )
    console.print(table)
    report = doctor_report(checks)
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["ok"]:
        print_error("Preflight failed: fix the failing checks before running.", console)
        sys.exit(1)
    console.print(f"[green]Preflight passed[/green] (worst status: {report['worst']}).")
