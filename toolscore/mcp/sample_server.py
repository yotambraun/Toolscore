#!/usr/bin/env python
"""A bundled, deliberately-imperfect sample MCP server for ``toolscore demo``.

This is a tiny, standard-library-only MCP server (newline-delimited JSON-RPC 2.0
over stdio) that ships *inside* the toolscore package so ``toolscore demo`` can
run end to end with zero setup and no API keys. It models a small "notes" server
with a realistic mix of quality problems, so the demo scorecard shows a genuine,
actionable verdict rather than a perfect score:

* ``create_note`` -- clean schema; works (happy path passes). It stores the
  note; creating a note whose title exists replaces its body.
* ``list_notes``  -- clean schema; works.
* ``search_notes`` -- works, but its description is too short (lint warning).
* ``delete_note`` -- its ``note_id`` property has no ``type`` (lint error: an
  LLM has to guess the shape).
* ``export_notes`` -- always returns ``isError`` (a tool that fails on valid
  input -- the top issue the verdict surfaces).
* ``create_note`` declares no behavior annotations although it writes (lint
  warning); the read-only and destructive tools declare theirs.

The notes live in memory for the life of the process, so the effect probes of
``toolscore mcp test --probes`` can check that a write is really visible. Opt-in
``--bug`` modes make the server misbehave the way real servers have, without an
error, so the probes have something to catch (several may be given)::

    python -m toolscore.mcp.sample_server --bug silent-skip

* ``silent-skip`` -- ``create_note`` on an existing title reports success and
  changes nothing (the pattern of modelcontextprotocol/servers#4887).
* ``lose-on-write`` -- every new note replaces all stored notes, so earlier
  notes are lost after a write (the outcome of #4885).
* ``limit-ignored`` -- ``list_notes`` returns every note whatever ``limit`` says.

Run it with ``python -m toolscore.mcp.sample_server``.
"""

from __future__ import annotations

import argparse
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

#: The ``--bug`` modes this server can be started with.
BUG_MODES = ("silent-skip", "lose-on-write", "limit-ignored")
#: Notes present when the server starts, oldest first.
SEED_NOTES = (("ideas", "Build a tiny MCP server."), ("groceries", "Milk, eggs, coffee."))

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


class NotesStore:
    """The server's notes, in memory, with the opt-in ``--bug`` behaviors.

    Args:
        bugs: The ``--bug`` modes to enable (see :data:`BUG_MODES`).
    """

    def __init__(self, bugs: set[str] | frozenset[str] = frozenset()) -> None:
        unknown = set(bugs) - set(BUG_MODES)
        if unknown:
            raise ValueError(f"unknown bug mode(s): {sorted(unknown)}; choose from {BUG_MODES}")
        self.bugs = frozenset(bugs)
        #: Title -> body, oldest first.
        self.notes: dict[str, str] = dict(SEED_NOTES)

    def create(self, title: str, body: str) -> None:
        """Store a note; an existing title gets the new body (unless ``silent-skip``)."""
        if title in self.notes:
            if "silent-skip" not in self.bugs:
                self.notes[title] = body
            return
        if "lose-on-write" in self.bugs:
            self.notes.clear()
        self.notes[title] = body

    def titles(self, limit: Any) -> list[str]:
        """Note titles, newest first, at most ``limit`` when it is a non-negative integer."""
        titles = list(reversed(self.notes))
        if (
            "limit-ignored" not in self.bugs
            and isinstance(limit, int)
            and not isinstance(limit, bool)
            and limit >= 0
        ):
            titles = titles[:limit]
        return titles

    def search(self, query: Any) -> list[dict[str, str]]:
        """Notes whose title or body contains ``query`` (case-insensitive), newest first."""
        needle = str(query).lower() if isinstance(query, str) else ""
        return [
            {"title": title, "body": body}
            for title, body in reversed(self.notes.items())
            if needle in title.lower() or needle in body.lower()
        ]


def _text(value: Any) -> dict[str, Any]:
    """A text content item holding ``value`` as JSON."""
    return {"type": "text", "text": json.dumps(value)}


def _handle_call(request_id: Any, params: dict[str, Any], modern: bool, store: NotesStore) -> None:
    """Handle a ``tools/call`` request for the sample tools."""
    name = params.get("name")
    arguments = params.get("arguments")
    args: dict[str, Any] = arguments if isinstance(arguments, dict) else {}

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
        notes = store.titles(args.get("limit"))
        _result(
            request_id,
            {
                "content": [_text({"notes": notes, "count": len(notes)})],
                "structuredContent": {"notes": notes, "count": len(notes)},
            },
            modern,
        )
        return

    if name == "create_note":
        title, body = args.get("title"), args.get("body", "")
        if isinstance(title, str) and title and isinstance(body, str):
            store.create(title, body)
        _result(request_id, {"content": [{"type": "text", "text": "ok"}]}, modern)
        return

    if name == "search_notes":
        _result(
            request_id,
            {"content": [_text({"notes": store.search(args.get("query"))})]},
            modern,
        )
        return

    if name == "delete_note":
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
        _handle_call(request_id, params, modern, state["store"])
    else:
        _error(request_id, -32601, f"Method not found: {method!r}")


def main(argv: list[str] | None = None) -> int:
    """Run the sample server's read/dispatch loop until stdin closes.

    Args:
        argv: Command-line arguments (default: ``sys.argv[1:]``); ``--bug MODE``
            enables a misbehavior from :data:`BUG_MODES` and may be repeated.

    Returns:
        The exit code.
    """
    parser = argparse.ArgumentParser(description="Toolscore's sample notes MCP server.")
    parser.add_argument(
        "--bug",
        action="append",
        choices=BUG_MODES,
        default=[],
        help="Misbehave on purpose, without reporting an error (repeatable).",
    )
    options = parser.parse_args(argv)
    state: dict[str, Any] = {"initialized": False, "store": NotesStore(set(options.bug))}
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
