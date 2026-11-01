#!/usr/bin/env python
"""A minimal MCP server (stdio, initialize handshake) for the effect-probe tests.

Tools:

* ``read_text(path, head?, tail?)`` -- a five-line file; ``head``/``tail`` slice lines.
* ``list_items(limit?)`` / ``search_items(query)`` -- the same three items.
* ``roll()`` -- read-only, returns a different number on every call.
* ``create_record(name, value)`` -- stored nowhere that a read tool shows.
* ``add_entry(name, note)`` -- answers ``{"created": [], "skipped": [name]}`` for a
  name it has seen, and stores entries that ``get_entries()`` lists.

Flags (``--bug``): ``head-zero`` (``head: 0`` returns the whole file),
``tail-short`` (``tail: N`` returns N-1 lines), ``search-extra`` (search returns
an item ``list_items`` does not have), ``skip-silent`` (``add_entry`` answers
``{"created": [], "skipped": []}`` for a name it has seen and keeps the old note).
"""

from __future__ import annotations

import json
import random
import sys
from typing import Any

LINES = ["one", "two", "three", "four", "five"]
ITEMS = ["alpha", "beta", "gamma"]


def _tool(name: str, props: dict[str, Any], required: list[str], read_only: bool) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"The {name} tool of the probe test server.",
        "inputSchema": {"type": "object", "properties": props, "required": required},
        "annotations": {"readOnlyHint": read_only, "destructiveHint": False},
    }


TOOLS = [
    _tool(
        "read_text",
        {"path": {"type": "string"}, "head": {"type": "integer"}, "tail": {"type": "integer"}},
        ["path"],
        True,
    ),
    _tool("list_items", {"limit": {"type": "integer"}}, [], True),
    _tool("search_items", {"query": {"type": "string"}}, ["query"], True),
    _tool("roll", {}, [], True),
    _tool(
        "create_record", {"name": {"type": "string"}, "value": {"type": "string"}}, ["name"], False
    ),
    _tool("add_entry", {"name": {"type": "string"}, "note": {"type": "string"}}, ["name"], False),
    _tool("get_entries", {}, [], True),
]


def _text(value: Any) -> dict[str, Any]:
    text = value if isinstance(value, str) else json.dumps(value)
    return {"content": [{"type": "text", "text": text}]}


def call(
    name: str, args: dict[str, Any], bugs: set[str], entries: dict[str, str]
) -> dict[str, Any]:
    if name == "read_text":
        lines = list(LINES)
        head, tail = args.get("head"), args.get("tail")
        if isinstance(head, int) and (head or "head-zero" not in bugs):
            lines = lines[:head]
        elif isinstance(tail, int):
            n = tail - 1 if "tail-short" in bugs and tail > 0 else tail
            lines = lines[-n:] if n else []
        return _text("\n".join(lines))
    if name == "list_items":
        limit = args.get("limit")
        return _text({"items": ITEMS[:limit] if isinstance(limit, int) else ITEMS})
    if name == "search_items":
        found = [i for i in ITEMS if str(args.get("query", "")) in i]
        if "search-extra" in bugs:
            found.append("delta")
        return _text({"items": found})
    if name == "roll":
        return _text(str(random.random()))
    if name == "create_record":
        return _text("ok")
    if name == "add_entry":
        key, note = str(args.get("name")), str(args.get("note", ""))
        if key in entries:
            if "skip-silent" in bugs:
                return _text({"created": [], "skipped": []})
            return _text({"created": [], "skipped": [key]})
        entries[key] = note
        return _text({"created": [key], "skipped": []})
    if name == "get_entries":
        return _text(entries)
    return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}


def main(argv: list[str]) -> int:
    bugs = {argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--bug"}
    entries: dict[str, str] = {}
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        request_id, method = message.get("id"), message.get("method")
        if request_id is None:
            continue
        params = message.get("params") or {}
        if method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "probe-test", "version": "0.1.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            result = call(params.get("name"), params.get("arguments") or {}, bugs, entries)
        else:
            reply = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "no"}}
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
