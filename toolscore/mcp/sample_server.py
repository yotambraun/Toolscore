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
"""

from __future__ import annotations

import json
import sys
from typing import Any

PROTOCOL_VERSION = "2025-06-18"

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
    },
]


def _send(message: dict[str, Any]) -> None:
    """Write a single JSON-RPC message to stdout, newline-delimited."""
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: dict[str, Any]) -> None:
    """Send a JSON-RPC success response."""
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, code: int, message: str) -> None:
    """Send a JSON-RPC error response."""
    _send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def _handle_call(request_id: Any, params: dict[str, Any]) -> None:
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
        )
        return

    if name in {"create_note", "list_notes", "search_notes", "delete_note"}:
        _result(request_id, {"content": [{"type": "text", "text": "ok"}]})
        return

    _error(request_id, -32602, f"Unknown tool: {name!r}")


def main() -> int:
    """Run the sample server's read/dispatch loop until stdin closes."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = message.get("method")
        request_id = message.get("id")

        if method == "notifications/initialized":
            continue
        if method == "initialize":
            _result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "notes-server", "version": "1.0.0"},
                },
            )
        elif method == "tools/list":
            _result(request_id, {"tools": TOOLS})
        elif method == "tools/call":
            _handle_call(request_id, message.get("params", {}) or {})
        elif request_id is not None:
            _error(request_id, -32601, f"Method not found: {method!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
