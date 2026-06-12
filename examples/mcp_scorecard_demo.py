#!/usr/bin/env python3
"""Example: run the MCP scorecard harness programmatically.

Spins up the bundled fake MCP server (``tests/fixtures/fake_mcp_server.py``)
over stdio, generates happy-path and edge-case scenarios from each advertised
tool's JSON schema, runs them, lints the schemas, and prints an A--F scorecard
-- the same thing ``toolscore mcp test`` does, but from Python.

Run it:

    uv run python examples/mcp_scorecard_demo.py

No API keys, no network: the fake server is pure stdlib and talks JSON-RPC over
stdin/stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console

from toolscore.mcp import (
    MCPScorecard,
    MCPStdioClient,
    generate_scenarios,
    lint_tools,
    print_scorecard,
    run_scenarios,
)

# Locate the bundled fake server relative to this file (works from any CWD).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_FAKE_SERVER = _REPO_ROOT / "tests" / "fixtures" / "fake_mcp_server.py"


def main() -> int:
    """Build a scorecard against the fake MCP server and print it."""
    console = Console()

    if not _FAKE_SERVER.is_file():
        console.print(f"[red]Could not find fake server at {_FAKE_SERVER}[/red]")
        return 1

    # Launch command: run the fake server with the current interpreter.
    command = [sys.executable, str(_FAKE_SERVER)]

    console.print(f"[dim]Launching MCP server:[/dim] {' '.join(command)}\n")

    with MCPStdioClient(command, timeout=30.0) as client:
        tools = client.list_tools()
        server_info = client.server_info

        console.print(
            f"Connected to [bold]{server_info.get('name', 'server')}[/bold] "
            f"({len(tools)} tools advertised)\n"
        )

        # Plan + execute scenarios, and lint the schemas.
        scenarios = generate_scenarios(tools, cases_per_tool=3, include_edge_cases=True)
        results = run_scenarios(client, scenarios)
        lint = lint_tools(tools)

    card = MCPScorecard(
        server_info=server_info,
        tools=tools,
        results=results,
        lint=lint,
    )

    # Pretty console scorecard (the same renderer the CLI uses).
    print_scorecard(card, console=console)

    # ...and a couple of programmatic assertions you might gate CI on.
    console.print(
        f"\nProgrammatic access: grade=[bold]{card.grade}[/bold], "
        f"score={card.score:.0%}, "
        f"happy_pass_rate={card.happy_pass_rate:.0%}, "
        f"lint_errors={card.lint_error_count}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
