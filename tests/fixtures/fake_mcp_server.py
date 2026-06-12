#!/usr/bin/env python
"""A minimal, stdlib-only MCP server over stdio for tests.

Speaks just enough of the Model Context Protocol stdio transport to exercise
:class:`toolscore.mcp.client.MCPStdioClient`: newline-delimited JSON-RPC 2.0
messages on stdin/stdout, with free-form logging on stderr.

Tools advertised:
    * ``add`` -- proper schema (two required numbers); returns ``a + b``.
    * ``flaky`` -- valid schema; every call returns ``isError: true``.
    * ``bad_schema`` -- intentionally malformed (no description; ``inputSchema``
      missing ``type``/``properties``).

Flags:
    ``--sleep <seconds>``  Delay every ``tools/call`` response by N seconds
    (used to drive client timeout tests).
    ``--paginate``  Serve ``tools/list`` across three terminating pages, one
    tool per page, using ``nextCursor``. Exercises the client's pagination loop.
    ``--paginate-loop``  Serve ``tools/list`` with a ``nextCursor`` that always
    repeats (``"loop"``), to drive the client's infinite-loop guard.

Run directly::

    python tests/fixtures/fake_mcp_server.py [--sleep 2] [--paginate] [--paginate-loop]
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

PROTOCOL_VERSION = "2025-06-18"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "add",
        "description": "Add two numbers and return the sum.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First addend."},
                "b": {"type": "number", "description": "Second addend."},
            },
            "required": ["a", "b"],
        },
    },
    {
        "name": "flaky",
        "description": "Always fails with an error result.",
        "inputSchema": {
            "type": "object",
            "properties": {"x": {"type": "string", "description": "Ignored input."}},
        },
    },
    {
        # Deliberately malformed: no description, and inputSchema lacks
        # "type"/"properties" to test client robustness.
        "name": "bad_schema",
        "inputSchema": {},
    },
]


def _log(message: str) -> None:
    """Write a free-form log line to stderr.

    Args:
        message: The message to log.
    """
    sys.stderr.write(f"[fake-mcp] {message}\n")
    sys.stderr.flush()


def _send(message: dict[str, Any]) -> None:
    """Write a single JSON-RPC message to stdout, newline-delimited.

    Args:
        message: The JSON-RPC message object.
    """
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _result(request_id: Any, result: dict[str, Any]) -> None:
    """Send a JSON-RPC success response.

    Args:
        request_id: The originating request id.
        result: The result payload.
    """
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Any, code: int, message: str) -> None:
    """Send a JSON-RPC error response.

    Args:
        request_id: The originating request id.
        code: The JSON-RPC error code.
        message: A human-readable error message.
    """
    _send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def _handle_call(request_id: Any, params: dict[str, Any], sleep: float) -> None:
    """Handle a ``tools/call`` request.

    Args:
        request_id: The originating request id.
        params: The request params (expects ``name`` and ``arguments``).
        sleep: Seconds to delay the response (for timeout tests).
    """
    if sleep > 0:
        time.sleep(sleep)

    name = params.get("name")
    arguments = params.get("arguments", {}) or {}

    if name == "add":
        total = arguments.get("a", 0) + arguments.get("b", 0)
        _result(request_id, {"content": [{"type": "text", "text": str(total)}]})
    elif name == "flaky":
        _result(
            request_id,
            {
                "content": [{"type": "text", "text": "flaky tool failed"}],
                "isError": True,
            },
        )
    elif name == "bad_schema":
        _result(request_id, {"content": [{"type": "text", "text": "ok"}]})
    else:
        _error(request_id, -32602, f"Unknown tool: {name!r}")


def _handle_list_tools(request_id: Any, params: dict[str, Any], mode: str) -> None:
    """Handle a ``tools/list`` request, optionally paginated.

    Args:
        request_id: The originating request id.
        params: The request params (may carry a ``cursor``).
        mode: One of ``"single"`` (all tools, no cursor), ``"paginate"`` (one
            tool per page across terminating pages), or ``"paginate-loop"``
            (always returns a repeating ``nextCursor`` to drive the loop guard).
    """
    cursor = params.get("cursor")

    if mode == "paginate-loop":
        # Always return the first tool and the same "loop" cursor forever.
        _result(request_id, {"tools": TOOLS[:1], "nextCursor": "loop"})
        return

    if mode == "paginate":
        # One tool per page; cursor encodes the next index. Terminate when
        # all tools have been served (no nextCursor on the final page).
        idx = int(cursor) if cursor is not None else 0
        idx = max(0, min(idx, len(TOOLS)))
        page = TOOLS[idx : idx + 1]
        response: dict[str, Any] = {"tools": page}
        if idx + 1 < len(TOOLS):
            response["nextCursor"] = str(idx + 1)
        _result(request_id, response)
        return

    _result(request_id, {"tools": TOOLS})


def main(argv: list[str]) -> int:
    """Run the fake server's read/dispatch loop.

    Args:
        argv: Command-line arguments (excluding the program name).

    Returns:
        Process exit code.
    """
    sleep = 0.0
    if "--sleep" in argv:
        idx = argv.index("--sleep")
        if idx + 1 < len(argv):
            sleep = float(argv[idx + 1])

    list_mode = "single"
    if "--paginate-loop" in argv:
        list_mode = "paginate-loop"
    elif "--paginate" in argv:
        list_mode = "paginate"

    _log(f"starting (sleep={sleep}, list_mode={list_mode})")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _log(f"ignoring non-JSON line: {line!r}")
            continue

        method = message.get("method")
        request_id = message.get("id")

        # Notifications have no id and require no response.
        if method == "notifications/initialized":
            _log("client initialized")
            continue

        if method == "initialize":
            _result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-mcp", "version": "0.1.0"},
                },
            )
        elif method == "tools/list":
            _handle_list_tools(request_id, message.get("params", {}) or {}, list_mode)
        elif method == "tools/call":
            _handle_call(request_id, message.get("params", {}) or {}, sleep)
        elif request_id is not None:
            _error(request_id, -32601, f"Method not found: {method!r}")
        else:
            _log(f"ignoring notification: {method!r}")

    _log("stdin closed; exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
