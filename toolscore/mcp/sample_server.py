#!/usr/bin/env python
"""A bundled, deliberately-imperfect sample MCP server for ``toolscore demo``.

This is a tiny, standard-library-only MCP server (newline-delimited JSON-RPC 2.0
over stdio) that ships *inside* the toolscore package so ``toolscore demo`` can
run end to end with zero setup and no API keys. It models a small "notes" server
with a realistic mix of quality problems, so the demo scorecard shows a genuine,
actionable verdict rather than a perfect score:

* ``create_note`` -- clean schema; works (happy path passes).
* ``list_notes``  -- clean schema; works.
* ``search_notes`` -- works, but its description is too short (lint warning).
* ``delete_note`` -- its ``note_id`` property has no ``type`` (lint error: an
  LLM has to guess the shape).
* ``export_notes`` -- always returns ``isError`` (a tool that fails on valid
  input -- the top issue the verdict surfaces).
* ``create_note`` declares no behavior annotations although it writes (lint
  warning); the read-only and destructive tools declare theirs.

The server is *dual-era*: it answers ``server/discover`` and per-request
``_meta`` (MCP 2026-07-28, stateless) as well as the ``initialize`` handshake of
earlier revisions, so it works with both kinds of client.

Run it with ``python -m toolscore.mcp.sample_server``.
"""

from __future__ import annotations

import json
import sys
from typing import Any

#: The stateless revision this server speaks (per-request ``_meta``).
MODERN_VERSION = "2026-07-28"
#: Handshake-based revisions it accepts in ``initialize``, newest first.
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
SUPPORTED_VERSIONS = [MODERN_VERSION, *LEGACY_VERSIONS]
SERVER_INFO = {"name": "notes-server", "version": "1.1.0"}
_META_VERSION = "io.modelcontextprotocol/protocolVersion"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "create_note",
        "description": "Create a note with a title and body and return its id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title for the note."},
                "body": {"type": "string", "description": "Full text content of the note."},
            },
            "required": ["title"],
        },
        # Writes, but declares no readOnlyHint/destructiveHint (lint warning).
    },
    {
        "name": "list_notes",
        "description": "List existing notes, newest first, up to a limit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum notes to return."},
            },
            "required": ["limit"],
        },
        "annotations": {"readOnlyHint": True},
        # Results carry structuredContent that conforms to this schema.
        "outputSchema": {
            "type": "object",
            "properties": {
                "notes": {"type": "array", "items": {"type": "string"}},
                "count": {"type": "integer"},
            },
            "required": ["notes", "count"],
        },
    },
    {
        # Works, but the description is too short to guide tool selection.
        "name": "search_notes",
        "description": "Search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to search for."},
            },
            "required": ["query"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        # The note_id property is missing a "type" -- an LLM must guess its shape.
        "name": "delete_note",
        "description": "Delete the note with the given id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"description": "Id of the note to delete."},
            },
            "required": ["note_id"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
    },
    {
        # Always errors, even on valid input -- the highest-priority issue.
        "name": "export_notes",
        "description": "Export all notes to the given format (json or markdown).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "description": "Export format: json or markdown."},
            },
            "required": ["format"],
        },
        "annotations": {"readOnlyHint": True},
    },
]


def _send(message: dict[str, Any]) -> None:
    """Write a single JSON-RPC message to stdout, newline-delimited."""
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: dict[str, Any], modern: bool) -> None:
    """Send a JSON-RPC success response (modern results carry resultType and serverInfo)."""
    if modern:
        result = {
            "resultType": "complete",
            **result,
            "_meta": {"io.modelcontextprotocol/serverInfo": SERVER_INFO},
        }
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, code: int, message: str, data: Any = None) -> None:
    """Send a JSON-RPC error response."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    _send({"jsonrpc": "2.0", "id": request_id, "error": error})


def _handle_call(request_id: Any, params: dict[str, Any], modern: bool) -> None:
    """Handle a ``tools/call`` request for the sample tools."""
    name = params.get("name")

    if name == "export_notes":
        # Deliberately broken: errors even on well-formed input.
        _result(
            request_id,
            {
                "content": [
                    {"type": "text", "text": "export failed: storage backend not configured"}
                ],
                "isError": True,
            },
            modern,
        )
        return

    if name == "list_notes":
        notes = ["groceries", "ideas"]
        _result(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps({"notes": notes, "count": 2})}],
                "structuredContent": {"notes": notes, "count": len(notes)},
            },
            modern,
        )
        return

    if name in {"create_note", "search_notes", "delete_note"}:
        _result(request_id, {"content": [{"type": "text", "text": "ok"}]}, modern)
        return

    _error(request_id, -32602, f"Unknown tool: {name!r}")


def _handle(message: dict[str, Any], state: dict[str, Any]) -> None:
    """Dispatch one message, serving modern (``_meta``) and legacy requests."""
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    meta = params.get("_meta")
    version = meta.get(_META_VERSION) if isinstance(meta, dict) else None

    if request_id is None:
        return  # notifications (e.g. notifications/initialized) need no answer

    if method == "initialize":
        requested = params.get("protocolVersion")
        negotiated = requested if requested in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
        state["initialized"] = True
        _result(
            request_id,
            {
                "protocolVersion": negotiated,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
            modern=False,
        )
        return

    modern = version is not None
    if modern and version != MODERN_VERSION:
        _error(
            request_id,
            -32022,
            "Unsupported protocol version",
            {"supported": SUPPORTED_VERSIONS, "requested": version},
        )
        return
    if not modern and not state["initialized"]:
        _error(request_id, -32602, "Missing _meta protocol version (or send initialize first)")
        return

    if method == "server/discover":
        _result(
            request_id,
            {"supportedVersions": SUPPORTED_VERSIONS, "capabilities": {"tools": {}}},
            modern=True,
        )
    elif method == "tools/list":
        listing: dict[str, Any] = {"tools": TOOLS}
        if modern:
            listing.update({"ttlMs": 60000, "cacheScope": "public"})
        _result(request_id, listing, modern)
    elif method == "tools/call":
        _handle_call(request_id, params, modern)
    else:
        _error(request_id, -32601, f"Method not found: {method!r}")


def main() -> int:
    """Run the sample server's read/dispatch loop until stdin closes."""
    state: dict[str, Any] = {"initialized": False}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict):
            _handle(message, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
