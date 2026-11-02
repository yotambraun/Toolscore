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
    ``--resources``  Also advertise ``read_note``, which returns its file as an
    embedded ``resource`` (the way GitHub's MCP server returns file contents).
    ``--instructions <text>``  Return ``<text>`` as the server ``instructions``
    in the ``initialize`` (or ``server/discover``) result.
    ``--era legacy|modern|dual``  ``legacy`` (default) speaks only the
    ``initialize`` handshake and answers unknown methods with ``-32601``.
    ``modern`` speaks only MCP 2026-07-28 (``server/discover``, per-request
    ``_meta``) and rejects ``initialize``. ``dual`` speaks both.
    ``--silent-unknown``  (legacy) never answer requests before ``initialize``,
    like legacy servers that drop them; drives the probe-timeout fallback.
    ``--modern-versions v1,v2``  Versions a modern server supports (default
    ``2026-07-28``); anything else gets ``UnsupportedProtocolVersionError``.
    ``--server-requests``  Before answering ``add``, send the client a ``ping``
    and a ``roots/list`` request, wait for both answers, and return them as
    the result text (JSON), to test that the client answers server requests.
    ``--flood N``  Before answering ``add``, send N log notifications.
    ``--input-required``  Also advertise ``ask_user``, which always answers
    ``resultType: "input_required"`` with an elicitation request.

Run directly::

    python tests/fixtures/fake_mcp_server.py [--sleep 2] [--paginate] [--paginate-loop]
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

PROTOCOL_VERSION = "2025-06-18"
MODERN_VERSION = "2026-07-28"
META_VERSION = "io.modelcontextprotocol/protocolVersion"

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


def _server_requests() -> list[dict[str, Any]]:
    """Send a ping and a roots/list request; read stdin until both are answered."""
    _send({"jsonrpc": "2.0", "id": "srv-ping", "method": "ping"})
    _send({"jsonrpc": "2.0", "id": "srv-roots", "method": "roots/list", "params": {}})
    answers: dict[str, dict[str, Any]] = {}
    for line in sys.stdin:
        message = json.loads(line) if line.strip() else {}
        if message.get("id") in ("srv-ping", "srv-roots"):
            answers[message["id"]] = message
        if len(answers) == 2:
            break
    return [answers.get("srv-ping", {}), answers.get("srv-roots", {})]


ASK_USER_TOOL: dict[str, Any] = {
    "name": "ask_user",
    "description": "Ask the user for their GitHub login before acting.",
    "inputSchema": {"type": "object", "properties": {"repo": {"type": "string"}}},
}


def _handle_call(
    request_id: Any,
    params: dict[str, Any],
    sleep: float,
    server_requests: bool = False,
    flood: int = 0,
) -> None:
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
        for index in range(flood):
            _send({"jsonrpc": "2.0", "method": "notifications/message", "params": {"n": index}})
        if server_requests:
            answers = _server_requests()
            _result(request_id, {"content": [{"type": "text", "text": json.dumps(answers)}]})
            return
        total = arguments.get("a", 0) + arguments.get("b", 0)
        _result(request_id, {"content": [{"type": "text", "text": str(total)}]})
    elif name == "ask_user":
        _result(
            request_id,
            {
                "resultType": "input_required",
                "inputRequests": {
                    "login": {
                        "method": "elicitation/create",
                        "params": {"mode": "form", "message": "Your GitHub login?"},
                    }
                },
                "requestState": "opaque",
            },
        )
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
    elif name == "read_note":
        _result(
            request_id,
            {
                "content": [
                    {"type": "text", "text": "successfully downloaded text file"},
                    {
                        "type": "resource",
                        "resource": {"uri": "file:///notes.md", "text": "# Notes\nStatus: draft\n"},
                    },
                ]
            },
        )
    else:
        _error(request_id, -32602, f"Unknown tool: {name!r}")


READ_NOTE_TOOL: dict[str, Any] = {
    "name": "read_note",
    "description": "Return the notes file as an embedded resource.",
    "inputSchema": {"type": "object", "properties": {}},
}


def _handle_list_tools(
    request_id: Any, params: dict[str, Any], mode: str, tools: list[dict[str, Any]] | None = None
) -> None:
    """Handle a ``tools/list`` request, optionally paginated.

    Args:
        request_id: The originating request id.
        params: The request params (may carry a ``cursor``).
        mode: One of ``"single"`` (all tools, no cursor), ``"paginate"`` (one
            tool per page across terminating pages), or ``"paginate-loop"``
            (always returns a repeating ``nextCursor`` to drive the loop guard).
    """
    cursor = params.get("cursor")
    tools = TOOLS if tools is None else tools

    if mode == "paginate-loop":
        # Always return the first tool and the same "loop" cursor forever.
        _result(request_id, {"tools": tools[:1], "nextCursor": "loop"})
        return

    if mode == "paginate":
        # One tool per page; cursor encodes the next index. Terminate when
        # all tools have been served (no nextCursor on the final page).
        idx = int(cursor) if cursor is not None else 0
        idx = max(0, min(idx, len(tools)))
        page = tools[idx : idx + 1]
        response: dict[str, Any] = {"tools": page}
        if idx + 1 < len(tools):
            response["nextCursor"] = str(idx + 1)
        _result(request_id, response)
        return

    _result(request_id, {"tools": tools})


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

    tools = [*TOOLS, READ_NOTE_TOOL] if "--resources" in argv else list(TOOLS)
    if "--input-required" in argv:
        tools.append(ASK_USER_TOOL)
    server_requests = "--server-requests" in argv
    flood = int(argv[argv.index("--flood") + 1]) if "--flood" in argv else 0
    instructions: str | None = None
    if "--instructions" in argv:
        idx = argv.index("--instructions")
        if idx + 1 < len(argv):
            instructions = argv[idx + 1]

    era = "legacy"
    if "--era" in argv:
        idx = argv.index("--era")
        if idx + 1 < len(argv):
            era = argv[idx + 1]
    silent_unknown = "--silent-unknown" in argv
    modern_versions = [MODERN_VERSION]
    if "--modern-versions" in argv:
        idx = argv.index("--modern-versions")
        if idx + 1 < len(argv):
            modern_versions = [v for v in argv[idx + 1].split(",") if v]

    _log(f"starting (sleep={sleep}, list_mode={list_mode}, era={era})")
    initialized = False

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
        params = message.get("params", {}) or {}
        meta = params.get("_meta") if isinstance(params, dict) else None
        version = meta.get(META_VERSION) if isinstance(meta, dict) else None

        # Notifications have no id and require no response.
        if method == "notifications/initialized":
            _log("client initialized")
            continue

        if method == "initialize":
            if era == "modern":
                _error(request_id, -32601, "initialize is not supported; send server/discover")
                continue
            initialized = True
            init_result: dict[str, Any] = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-mcp", "version": "0.1.0"},
            }
            if instructions is not None:
                init_result["instructions"] = instructions
            _result(request_id, init_result)
            continue

        modern = era in ("modern", "dual") and version is not None
        if modern and version not in modern_versions:
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32022,
                        "message": "Unsupported protocol version",
                        "data": {"supported": modern_versions, "requested": version},
                    },
                }
            )
            continue
        if not modern and not initialized:
            if silent_unknown or request_id is None:
                continue
            if era == "modern":
                _error(request_id, -32602, "missing _meta protocol version")
                continue
            if method != "server/discover":
                _error(request_id, -32002, "Server not initialized")
                continue

        if method == "server/discover" and modern:
            discover: dict[str, Any] = {
                "resultType": "complete",
                "supportedVersions": modern_versions,
                "capabilities": {"tools": {}},
                "_meta": {
                    "io.modelcontextprotocol/serverInfo": {
                        "name": "fake-mcp-modern",
                        "version": "0.2.0",
                    }
                },
            }
            if instructions is not None:
                discover["instructions"] = instructions
            _result(request_id, discover)
        elif method == "tools/list":
            _handle_list_tools(request_id, params, list_mode, tools)
        elif method == "tools/call":
            _handle_call(request_id, params, sleep, server_requests, flood)
        elif request_id is not None:
            _error(request_id, -32601, f"Method not found: {method!r}")
        else:
            _log(f"ignoring notification: {method!r}")

    _log("stdin closed; exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
