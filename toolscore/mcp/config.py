"""Parse MCP server configuration files (Claude Desktop, Cursor, VS Code, Claude Code).

MCP hosts store server definitions in JSON. Claude Desktop, Cursor and Claude
Code use an ``mcpServers`` mapping; VS Code (``.vscode/mcp.json``) uses
``servers``. An entry either launches a local server over stdio::

    {
        "mcpServers": {
            "filesystem": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                "env": {"DEBUG": "1"}
            }
        }
    }

or points at a remote server over Streamable HTTP::

    {
        "servers": {
            "github": {
                "type": "http",
                "url": "https://api.githubcopilot.com/mcp/",
                "headers": {"Authorization": "Bearer ${env:GITHUB_TOKEN}"}
            }
        }
    }

``${VAR}`` and ``${env:VAR}`` in ``url`` and ``headers`` are replaced with
environment variables, so tokens stay out of the file. A missing variable is an
error that names the variable, never its value.

This module turns such a file into a :class:`MCPServerSpec`; see
:func:`toolscore.mcp.open_client` to connect to it.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from toolscore.mcp.client import MCPClient, ProtocolMode

#: Entry ``type`` values that mean Streamable HTTP.
_HTTP_TYPES = frozenset({"http", "streamable-http", "streamable_http", "streamablehttp"})

_ENV_REFERENCE = re.compile(r"\$\{(?:env:)?([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class MCPServerSpec:
    """A single MCP server entry resolved from a config file.

    Attributes:
        name: The key under ``mcpServers`` / ``servers`` identifying this server.
        command: The full command vector, i.e. ``[command, *args]`` (empty for
            a remote server).
        env: Environment variable overrides for the server process (often
            API keys, so kept out of the repr).
        url: The Streamable HTTP endpoint of a remote server, or ``None`` for
            a stdio server. It may hold a token, so it is kept out of the repr.
        headers: HTTP headers for a remote server (environment references
            already expanded). Treat the values as secrets.
    """

    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict, repr=False)
    url: str | None = field(default=None, repr=False)
    headers: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def transport(self) -> str:
        """``"http"`` for a remote server, ``"stdio"`` otherwise."""
        return "http" if self.url else "stdio"


def expand_env(value: str, what: str = "value") -> str:
    """Replace ``${VAR}`` and ``${env:VAR}`` with environment variables.

    Args:
        value: The text to expand.
        what: What the text is, for the error message (e.g. ``"header 'Authorization'"``).

    Returns:
        The expanded text.

    Raises:
        ValueError: If a referenced variable is not set. The message names the
            variable but never shows any value.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = os.environ.get(name)
        if resolved is None:
            raise ValueError(
                f"{what} refers to ${{{name}}}, but environment variable {name} is not set."
            )
        return resolved

    return _ENV_REFERENCE.sub(replace, value)


def parse_header(text: str) -> tuple[str, str]:
    """Parse a ``"Name: value"`` header option, expanding ``${VAR}`` references.

    Args:
        text: The header as given on the command line.

    Returns:
        The ``(name, value)`` pair.

    Raises:
        ValueError: If the text is not ``Name: value`` or a variable is unset.
    """
    name, sep, value = text.partition(":")
    name = name.strip()
    if not sep or not name or any(c.isspace() for c in name):
        # Never echo the input: a mistyped option may be the secret itself.
        raise ValueError(
            "Expected a header as 'Name: value' (a name without spaces, then a colon)."
        )
    return name, expand_env(value.strip(), f"header {name!r}")


def load_mcp_config(path: str | Path, server: str | None = None) -> MCPServerSpec:
    """Load an MCP server specification from an MCP host config file.

    Args:
        path: Path to the JSON configuration file (``mcpServers`` or VS Code
            ``servers`` layout).
        server: Name of the server to load. If ``None`` and exactly one server
            is defined, that server is used. If ``None`` and multiple servers
            exist, a :class:`ValueError` is raised listing the available names.

    Returns:
        The resolved :class:`MCPServerSpec`.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file is malformed, the server mapping is missing or
            empty, the requested ``server`` is not found, ``server`` is ``None``
            while multiple servers are defined, the entry uses the deprecated
            SSE transport, or a referenced environment variable is unset.
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
    if servers is None:
        servers = raw.get("servers")
    if not isinstance(servers, dict) or not servers:
        raise ValueError(
            f"MCP config file {config_path} is missing a non-empty 'mcpServers' "
            "(or VS Code 'servers') object."
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

    kind = str(entry.get("type", "")).lower()
    url = entry.get("url", entry.get("serverUrl"))
    if kind == "sse":
        raise ValueError(
            f"MCP server {server!r} uses the HTTP+SSE transport, which the MCP specification "
            "deprecated in 2025-03-26; toolscore supports stdio and Streamable HTTP."
        )
    if url is not None or kind in _HTTP_TYPES:
        return _http_spec(server, url, entry)

    command = entry.get("command")
    if not isinstance(command, str) or not command:
        raise ValueError(
            f"MCP server {server!r} must define a non-empty string 'command' (stdio) or 'url' "
            "(Streamable HTTP)."
        )

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


def _http_spec(server: str, url: object, entry: dict[str, object]) -> MCPServerSpec:
    """Build the spec of a Streamable HTTP entry."""
    if not isinstance(url, str) or not url:
        raise ValueError(f"MCP server {server!r} must define a non-empty string 'url'.")
    url = expand_env(url, f"MCP server {server!r} 'url'")
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"MCP server {server!r} 'url' must start with http:// or https://.")
    raw_headers = entry.get("headers", {})
    if not isinstance(raw_headers, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw_headers.items()
    ):
        raise ValueError(f"MCP server {server!r} 'headers' must be a mapping of string to string.")
    headers = {
        key: expand_env(value, f"MCP server {server!r} header {key!r}")
        for key, value in raw_headers.items()
    }
    return MCPServerSpec(name=server, command=[], url=url, headers=headers)


def open_client(
    spec: MCPServerSpec, timeout: float = 30.0, protocol: ProtocolMode = "auto"
) -> MCPClient:
    """Build the right client for a server spec (stdio or Streamable HTTP).

    The client is not started; use it as a context manager::

        with open_client(load_mcp_config("mcp.json", "github")) as client:
            tools = client.list_tools()

    Args:
        spec: The resolved server entry.
        timeout: Per-request timeout in seconds.
        protocol: ``"auto"``, ``"modern"`` or ``"legacy"`` (see
            :class:`toolscore.mcp.client.MCPClient`).

    Returns:
        An :class:`~toolscore.mcp.client.MCPHttpClient` for a ``url`` entry,
        otherwise an :class:`~toolscore.mcp.client.MCPStdioClient`.
    """
    from toolscore.mcp.client import MCPHttpClient, MCPStdioClient

    if spec.url:
        return MCPHttpClient(spec.url, headers=spec.headers, timeout=timeout, protocol=protocol)
    return MCPStdioClient(spec.command, env=spec.env or None, timeout=timeout, protocol=protocol)
