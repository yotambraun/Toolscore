"""Server snapshots: what an MCP server advertised, saved to compare later.

``toolscore mcp list SERVER --json snapshot.json`` writes one;
``toolscore mcp diff`` and ``toolscore mcp verify-pin`` read it (as well as live
servers and lock files). Layout (``snapshot_version`` "1")::

    {
      "snapshot_version": "1",
      "kind": "toolscore.mcp-snapshot",
      "generated_by": "toolscore 1.11.0",
      "server": {"name": "memory-server", "version": "2.0.1"},
      "protocol": {"version": "2026-07-28", "era": "modern"},
      "instructions": null,
      "tools": [{"name": ..., "title": ..., "description": ..., "inputSchema": {...},
                 "outputSchema": {...}, "annotations": {...}}]
    }

Tools use the MCP field names, so a ``tools/list`` result can be pasted in.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from toolscore.mcp.client import MCPToolDef, _tool_def

if TYPE_CHECKING:
    from toolscore.mcp.client import MCPClient

#: Layout version of a snapshot file.
SNAPSHOT_VERSION = "1"
#: The ``kind`` of a snapshot file.
SNAPSHOT_KIND = "toolscore.mcp-snapshot"


def tool_to_json(tool: MCPToolDef) -> dict[str, Any]:
    """A tool definition with MCP field names (``inputSchema``...); empty fields left out."""
    data: dict[str, Any] = {"name": tool.name}
    if tool.title is not None:
        data["title"] = tool.title
    data["description"] = tool.description
    data["inputSchema"] = tool.input_schema
    if tool.output_schema is not None:
        data["outputSchema"] = tool.output_schema
    if tool.annotations:
        data["annotations"] = tool.annotations
    return data


@dataclass
class ServerSnapshot:
    """What a server advertised: its tools, identity, protocol and instructions.

    Attributes:
        tools: The tools, in the order the server listed them.
        server_info: ``serverInfo`` (``name``, ``version``).
        protocol_version: The protocol version used, if known.
        era: ``"modern"`` or ``"legacy"``, if known.
        instructions: The server ``instructions``, if any.
        source: Where the snapshot came from (a command, URL or file), for reports.
    """

    tools: list[MCPToolDef]
    server_info: dict[str, Any] = field(default_factory=dict)
    protocol_version: str | None = None
    era: str | None = None
    instructions: str | None = None
    source: str = ""

    @classmethod
    def from_client(cls, client: MCPClient, source: str = "") -> ServerSnapshot:
        """Snapshot a started client (lists its tools)."""
        tools = client.list_tools()
        return cls(
            tools=tools,
            server_info=dict(client.server_info),
            protocol_version=client.protocol_version,
            era=client.era,
            instructions=client.server_instructions,
            source=source,
        )

    @property
    def tool_map(self) -> dict[str, MCPToolDef]:
        """Tools by name."""
        return {tool.name: tool for tool in self.tools}

    @property
    def label(self) -> str:
        """``"memory-server 2.0.1"``, or the source."""
        name = str(self.server_info.get("name") or "")
        version = str(self.server_info.get("version") or "")
        return f"{name} {version}".strip() or self.source or "server"

    def to_json(self) -> dict[str, Any]:
        """The snapshot file layout (see the module docstring)."""
        from toolscore import __version__

        return {
            "snapshot_version": SNAPSHOT_VERSION,
            "kind": SNAPSHOT_KIND,
            "generated_by": f"toolscore {__version__}",
            "server": {
                "name": self.server_info.get("name", ""),
                "version": self.server_info.get("version", ""),
            },
            "protocol": {"version": self.protocol_version, "era": self.era},
            "instructions": self.instructions,
            "tools": [tool_to_json(tool) for tool in self.tools],
        }


def snapshot_from_json(data: Any, source: str = "") -> ServerSnapshot:
    """Read a snapshot, a lock file (``toolscore mcp pin``) or a raw ``tools/list`` result.

    Args:
        data: Parsed JSON.
        source: Where it came from, for reports.

    Returns:
        The snapshot.

    Raises:
        ValueError: If ``data`` holds no tool list.
    """
    if isinstance(data, list):
        data = {"tools": data}
    if not isinstance(data, dict):
        raise ValueError(f"{source or 'snapshot'}: expected a JSON object with 'tools'")
    raw_tools = data.get("tools")
    if isinstance(raw_tools, dict):  # a lock file: {name: {"definition": {...}}}
        raw_tools = [
            entry.get("definition", {"name": name})
            for name, entry in raw_tools.items()
            if isinstance(entry, dict)
        ]
    if isinstance(data.get("result"), dict):  # a JSON-RPC tools/list response
        raw_tools = data["result"].get("tools")
    if not isinstance(raw_tools, list):
        raise ValueError(f"{source or 'snapshot'}: no 'tools' list")
    server = data.get("server") if isinstance(data.get("server"), dict) else {}
    protocol = data.get("protocol") if isinstance(data.get("protocol"), dict) else {}
    instructions = data.get("instructions")
    return ServerSnapshot(
        tools=[_tool_def(t) for t in raw_tools if isinstance(t, dict)],
        server_info=dict(server or {}),
        protocol_version=(protocol or {}).get("version"),
        era=(protocol or {}).get("era"),
        instructions=instructions if isinstance(instructions, str) else None,
        source=source,
    )


def load_snapshot(path: str | Path) -> ServerSnapshot:
    """Read a snapshot or lock file from disk (see :func:`snapshot_from_json`)."""
    return snapshot_from_json(json.loads(Path(path).read_text(encoding="utf-8")), source=str(path))


def write_snapshot(path: str | Path, snapshot: ServerSnapshot) -> Path:
    """Write a snapshot file and return its path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(snapshot.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return target


def text_diff(before: str, after: str, from_name: str = "a", to_name: str = "b") -> str:
    """A unified diff of two texts, ``""`` when they are equal."""
    if before == after:
        return ""
    lines = difflib.unified_diff(
        before.splitlines(), after.splitlines(), fromfile=from_name, tofile=to_name, lineterm=""
    )
    return "\n".join(lines)
