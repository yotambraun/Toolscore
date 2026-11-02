"""``toolscore mcp pin``, ``mcp verify-pin`` and ``mcp diff``."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console
from rich.table import Table

from toolscore.reports import print_error
from toolscore.reports.ci import ci_report_options

if TYPE_CHECKING:
    from toolscore.mcp.pin import PinReport
    from toolscore.mcp.snapshot import ServerSnapshot


def _is_snapshot_file(command: tuple[str, ...]) -> bool:
    return len(command) == 1 and command[0].endswith(".json") and Path(command[0]).is_file()


def snapshot_of(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    headers: tuple[str, ...],
    auth_env: str | None,
    protocol: str,
    timeout: float,
    console: Console,
) -> ServerSnapshot:
    """A snapshot of the target: a saved snapshot or lock file, or a live server."""
    from toolscore.cli import _connect
    from toolscore.mcp.snapshot import ServerSnapshot, load_snapshot

    if _is_snapshot_file(command) and config is None:
        try:
            return load_snapshot(command[0])
        except (OSError, ValueError) as exc:
            print_error(f"Cannot read snapshot {command[0]}: {exc}", console)
            sys.exit(2)
    client = _connect(command, config, server, headers, auth_env, protocol, timeout, console)
    try:
        with client:
            return ServerSnapshot.from_client(client, source=" ".join(command) or str(config))
    except Exception as exc:  # surface any launch/protocol failure to the user
        print_error(f"Failed to query MCP server: {exc}", console)
        sys.exit(1)


def print_pin_report(report: PinReport, console: Console) -> None:
    """Print a pin report with its verdict."""
    from toolscore.mcp.pin import render_pin_report

    console.print("[bold]Pin check[/bold]")
    console.print(render_pin_report(report), highlight=False)
    console.print()


def check_pin(
    lock_path: Path,
    snapshot: ServerSnapshot,
    fail_on: str,
    console: Console,
    ci: bool = False,
) -> PinReport:
    """Verify ``snapshot`` against a lock file and print the report (exit 2 on a bad lock)."""
    from toolscore.mcp.pin import load_lock, render_pin_report, verify_pin

    try:
        lock = load_lock(lock_path)
    except (OSError, ValueError) as exc:
        print_error(f"Cannot read lock file {lock_path}: {exc}", console)
        sys.exit(2)
    report = verify_pin(lock, snapshot, fail_on=fail_on)
    print_pin_report(report, console)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if ci and summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(
                "## Toolscore pin check\n\n```\n"
                + render_pin_report(report, color=False)
                + "\n```\n"
            )
    return report


def _connection_options(func: Any) -> Any:
    from toolscore.cli import _mcp_connection_options

    return _mcp_connection_options(func)


_FAIL_ON_HELP = (
    "What fails the check: drift (any tool, schema, description, annotation or instructions "
    "change, default), capability (only a new delete/exec capability) or never."
)


@click.command("pin")
@click.argument("command", nargs=-1)
@_connection_options
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default="toolscore.lock.json",
    show_default=True,
    help="Lock file to write.",
)
@click.option(
    "--capabilities",
    "capabilities_file",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help='JSON file overriding derived capabilities: {"tool": ["read"]}.',
)
def mcp_pin(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    headers: tuple[str, ...],
    auth_env: str | None,
    protocol: str,
    timeout: float,
    output: Path,
    capabilities_file: Path | None,
) -> None:
    """Pin a server's tools: write toolscore.lock.json with hashes and a capability manifest.

    Hashes each tool's name, title, description, input and output schema and
    annotations, and records the server's identity, protocol, instructions and
    each tool's capabilities (read, write, delete, network, exec or unknown;
    from annotations first, then name and description rules). Commit the lock;
    `toolscore mcp verify-pin` fails when the server drifts from it.

    COMMAND: the server launch command as a single quoted string, a URL, or a
    snapshot file from `toolscore mcp list --json` (omit when using --config).
    """
    from toolscore.mcp.pin import (
        build_lock,
        load_capability_overrides,
        load_lock,
        verify_pin,
        write_lock,
    )

    console = Console()
    overrides = None
    if capabilities_file is not None:
        try:
            overrides = load_capability_overrides(capabilities_file)
        except (OSError, ValueError) as exc:
            print_error(f"Invalid capability overrides: {exc}", console)
            sys.exit(2)
    snapshot = snapshot_of(command, config, server, headers, auth_env, protocol, timeout, console)
    previous = None
    if output.is_file():
        try:
            previous = verify_pin(load_lock(output), snapshot, fail_on="never")
        except ValueError:
            previous = None
    lock = build_lock(snapshot, overrides)
    write_lock(output, lock)

    table = Table(title=f"Pinned {snapshot.label}", header_style="bold magenta")
    table.add_column("Tool", style="cyan")
    table.add_column("Capabilities")
    table.add_column("Why", style="dim")
    for name, entry in lock["tools"].items():
        caps = entry["capabilities"]
        risky = {"delete", "exec"} & set(caps)
        shown = ", ".join(f"[red]{c}[/red]" if c in risky else c for c in caps)
        why = "; ".join(s for sources in entry["capability_sources"].values() for s in sources)
        table.add_row(name, shown, why)
    console.print(table)
    if previous is not None and previous.drifted:
        console.print(
            f"[yellow]Updated {output}:[/yellow] {len(previous.findings)} change(s) from the "
            "previous lock were accepted."
        )
    console.print(
        f"[dim]Wrote {output} ({len(lock['tools'])} tools, lock_sha256 "
        f"{lock['lock_sha256'][:12]}...). Commit it and run `toolscore mcp verify-pin` in CI.[/dim]"
    )


@click.command("verify-pin")
@click.argument("command", nargs=-1)
@_connection_options
@click.option(
    "--lock",
    "lock_path",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default="toolscore.lock.json",
    show_default=True,
    help="Lock file written by `toolscore mcp pin`.",
)
@click.option(
    "--fail-on",
    type=click.Choice(["drift", "capability", "never"]),
    default="drift",
    show_default=True,
    help=_FAIL_ON_HELP,
)
@click.option(
    "--json",
    "json_out",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Write the report as JSON.",
)
@click.option(
    "--ci",
    is_flag=True,
    default=False,
    help="Also write the report to $GITHUB_STEP_SUMMARY.",
)
@ci_report_options()
def mcp_verify_pin(
    command: tuple[str, ...],
    config: Path | None,
    server: str | None,
    headers: tuple[str, ...],
    auth_env: str | None,
    protocol: str,
    timeout: float,
    lock_path: Path,
    fail_on: str,
    json_out: Path | None,
    ci: bool,
    sarif_path: Path | None,
    junit_path: Path | None,
) -> None:
    """Check a server against its lock file; exit 1 when it drifted.

    Reports tools added, removed or changed (with text diffs of descriptions
    and schemas), new delete/exec capabilities, changed server instructions
    and a hand-edited lock; server version and protocol changes are info.

    COMMAND: the server launch command as a single quoted string, a URL, or a
    snapshot file (omit when using --config).
    """
    console = Console()
    snapshot = snapshot_of(command, config, server, headers, auth_env, protocol, timeout, console)
    report = check_pin(lock_path, snapshot, fail_on, console, ci=ci)
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    if sarif_path is not None or junit_path is not None:
        from toolscore.cli import _note_written
        from toolscore.reports.ci import outcomes_from_pin, write_ci_reports

        outcomes = outcomes_from_pin(report, str(lock_path))
        _note_written(write_ci_reports(outcomes, "mcp verify-pin", sarif_path, junit_path), console)
    if not report.ok:
        sys.exit(1)


def _target(text: str) -> tuple[str, ...]:
    return (text,)


@click.command("diff")
@click.argument("a")
@click.argument("b")
@click.option(
    "--test",
    "run_test",
    is_flag=True,
    default=False,
    help="Also run the scorecard on both (live servers only) and compare grades and probes.",
)
@click.option("--probes", is_flag=True, default=False, help="With --test: run the effect probes.")
@click.option(
    "--allow-writes",
    is_flag=True,
    default=False,
    help="With --test --probes: let probes write (use disposable servers).",
)
@click.option(
    "--fail-on",
    type=click.Choice(["any", "breaking", "none"]),
    default="any",
    show_default=True,
    help=(
        "Exit 1 on any difference, only on breaking ones (removed tool or parameter, newly "
        "required parameter, changed type, new delete/exec capability, new lint error, lower "
        "grade, newly failing probe), or never."
    ),
)
@click.option(
    "--json",
    "json_out",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Write the diff as JSON.",
)
@click.option(
    "--protocol",
    type=click.Choice(["auto", "modern", "legacy"]),
    default="auto",
    show_default=True,
    help="MCP protocol era for live servers.",
)
@click.option("--timeout", type=float, default=30.0, help="Per-call timeout in seconds.")
@ci_report_options(location=True)
def mcp_diff(
    a: str,
    b: str,
    run_test: bool,
    probes: bool,
    allow_writes: bool,
    fail_on: str,
    json_out: Path | None,
    protocol: str,
    timeout: float,
    sarif_path: Path | None,
    junit_path: Path | None,
    report_location: Path | None,
) -> None:
    """Compare two MCP servers, builds or configs.

    A and B are each a launch command (one quoted string), a URL, or a JSON
    snapshot (`toolscore mcp list --json`) or lock file (`toolscore mcp pin`).
    Shows tools added and removed, description, schema and annotation changes
    with text diffs, capability changes, new and resolved lint findings, and
    with --test the scorecard and probe deltas.

    Exit codes: 0 when nothing fails under --fail-on, 1 when it does, 2 on a
    usage or connection error.

    Example:

        toolscore mcp diff "npx -y @modelcontextprotocol/server-memory@2026.8.31" \\
            "npx -y @modelcontextprotocol/server-memory@2.0.1" --test --probes --allow-writes
    """
    from toolscore.mcp.server_diff import diff_snapshots, render_diff

    console = Console()
    snapshots = []
    cards = []
    for side in (a, b):
        target = _target(side)
        if run_test and _is_snapshot_file(target):
            print_error(f"--test needs live servers; {side} is a snapshot file.", console)
            sys.exit(2)
        if run_test:
            from toolscore.cli import _connect
            from toolscore.mcp.scorecard import score_server
            from toolscore.mcp.snapshot import ServerSnapshot

            client = _connect(target, None, None, (), None, protocol, timeout, console)
            try:
                with client:
                    snapshots.append(ServerSnapshot.from_client(client, source=side))
                    cards.append(score_server(client, probes=probes, allow_writes=allow_writes))
            except Exception as exc:  # surface any launch/protocol failure to the user
                print_error(f"Failed to test {side}: {exc}", console)
                sys.exit(2)
        else:
            try:
                snapshots.append(
                    snapshot_of(target, None, None, (), None, protocol, timeout, console)
                )
            except SystemExit:
                sys.exit(2)
    diff = diff_snapshots(
        snapshots[0], snapshots[1], scorecards=(cards[0], cards[1]) if cards else None
    )
    console.print(render_diff(diff), highlight=False)
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(diff.to_dict(), indent=2) + "\n", encoding="utf-8")
    if sarif_path is not None or junit_path is not None:
        from toolscore.cli import _note_written
        from toolscore.reports.ci import default_location, outcomes_from_diff, write_ci_reports

        where = default_location(report_location, None, _target(b))
        if where is None and Path(a).is_file():
            where = a
        outcomes = outcomes_from_diff(diff, fail_on, where)
        _note_written(write_ci_reports(outcomes, "mcp diff", sarif_path, junit_path), console)
    if diff.fails(fail_on):
        sys.exit(1)
