"""Parse Claude Desktop style MCP server configuration files.

The de-facto configuration format used by Claude Desktop and other MCP hosts
stores server definitions under an ``mcpServers`` mapping::

    {
        "mcpServers": {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                "env": {"DEBUG": "1"}
            }
        }
    }

This module turns such a file into a :class:`MCPServerSpec` ready to be passed
to :class:`toolscore.mcp.client.MCPStdioClient`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MCPServerSpec:
    """A single MCP server entry resolved from a config file.

    Attributes:
        name: The key under ``mcpServers`` identifying this server.
        command: The full command vector, i.e. ``[command, *args]``.
        env: Environment variable overrides for the server process.
    """

    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)


def load_mcp_config(path: str | Path, server: str | None = None) -> MCPServerSpec:
    """Load an MCP server specification from a Claude Desktop style config file.

    Args:
        path: Path to the JSON configuration file.
        server: Name of the server to load. If ``None`` and exactly one server
            is defined, that server is used. If ``None`` and multiple servers
            exist, a :class:`ValueError` is raised listing the available names.

    Returns:
        The resolved :class:`MCPServerSpec`.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file is malformed, the ``mcpServers`` key is missing
            or empty, the requested ``server`` is not found, or ``server`` is
            ``None`` while multiple servers are defined.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"MCP config file not found: {config_path}")

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"MCP config file is not valid JSON ({config_path}): {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"MCP config file must contain a JSON object: {config_path}")

    servers = raw.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        raise ValueError(
            f"MCP config file {config_path} is missing a non-empty 'mcpServers' object."
        )

    available = sorted(servers)

    if server is None:
        if len(servers) > 1:
            raise ValueError(
                f"Multiple MCP servers defined; specify one of: {', '.join(available)}"
            )
        server = next(iter(servers))
    elif server not in servers:
        raise ValueError(
            f"MCP server {server!r} not found in {config_path}. "
            f"Available servers: {', '.join(available)}"
        )

    entry = servers[server]
    if not isinstance(entry, dict):
        raise ValueError(f"MCP server {server!r} must be a JSON object in {config_path}.")

    command = entry.get("command")
    if not isinstance(command, str) or not command:
        raise ValueError(f"MCP server {server!r} must define a non-empty string 'command'.")

    raw_args = entry.get("args", [])
    if not isinstance(raw_args, list) or not all(isinstance(arg, str) for arg in raw_args):
        raise ValueError(f"MCP server {server!r} 'args' must be a list of strings.")

    raw_env = entry.get("env", {})
    if not isinstance(raw_env, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw_env.items()
    ):
        raise ValueError(f"MCP server {server!r} 'env' must be a mapping of string to string.")

    return MCPServerSpec(
        name=server,
        command=[command, *raw_args],
        env=dict(raw_env),
    )
