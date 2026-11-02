"""Command-line commands added in 1.11 for rigor: receipts, pinning, diffs, runs.

:mod:`toolscore.cli` builds the ``toolscore`` group; :func:`register` adds the
commands defined here to it (``regrade``, ``agent``, ``export``, ``select``,
``doctor``) and to its ``mcp`` group (``pin``, ``verify-pin``, ``diff``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import click


def register(main: click.Group, mcp: click.Group) -> None:
    """Add the commands of this package to the ``toolscore`` and ``toolscore mcp`` groups."""
    from toolscore.commands.mcp_pin import mcp_diff, mcp_pin, mcp_verify_pin
    from toolscore.commands.regrade import regrade
    from toolscore.commands.stats import select

    main.add_command(regrade)
    main.add_command(select)
    mcp.add_command(mcp_pin)
    mcp.add_command(mcp_verify_pin)
    mcp.add_command(mcp_diff)
