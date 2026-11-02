"""An in-process Streamable HTTP MCP server for tests (standard library only).

:class:`FakeHTTPServer` runs a ``ThreadingHTTPServer`` on ``127.0.0.1`` with a
random port and serves one MCP endpoint at ``/mcp``. It can behave as:

* ``era="modern"``: MCP 2026-07-28. Answers ``server/discover``, requires the
  ``_meta`` protocol version and the ``MCP-Protocol-Version`` / ``Mcp-Method``
  / ``Mcp-Name`` headers, and rejects mismatches with ``400`` and a
  ``HeaderMismatch`` (``-32020``) error.
* ``era="legacy"``: the 2025-11-25 session binding. ``initialize`` mints an
  ``Mcp-Session-Id``; other requests without it get ``400`` and a non-modern
  JSON-RPC error (the shape the TypeScript SDK returns).

``sse=True`` answers requests as a server-sent-event stream (a progress
notification, then the response); with ``ping=True`` the stream also carries
a ``ping`` request, and the client's answer lands in
:attr:`FakeHTTPServer.client_responses`. ``token`` requires ``Authorization: Bearer
<token>`` and answers ``401`` otherwise. Every request's headers are kept in
:attr:`FakeHTTPServer.requests` for assertions.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from tests.fixtures.fake_mcp_server import TOOLS

MODERN = "2026-07-28"
META_VERSION = "io.modelcontextprotocol/protocolVersion"

ECHO_TOOL: dict[str, Any] = {
    "name": "echo_region",
    "description": "Echo the region argument back.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "region": {"type": "string", "description": "A region.", "x-mcp-header": "Region"},
            "query": {"type": "string", "description": "Anything."},
        },
        "required": ["region"],
    },
}


class FakeHTTPServer:
    """A threaded fake MCP server; use as a context manager."""

    def __init__(
        self, era: str = "modern", sse: bool = False, token: str | None = None, ping: bool = False
    ) -> None:
        self.era = era
        self.sse = sse
        self.ping = ping
        self.client_responses: list[dict[str, Any]] = []
        self.token = token
        self.requests: list[dict[str, Any]] = []
        self.sessions: set[str] = set()
        self.deleted: list[str] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/mcp"

    def __enter__(self) -> FakeHTTPServer:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    # -- protocol ------------------------------------------------------------

    def answer(
        self, message: dict[str, Any], headers: dict[str, str]
    ) -> tuple[int, Any, dict[str, str]]:
        """Return ``(status, body, extra_headers)`` for one POSTed message."""
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}
        meta = params.get("_meta") if isinstance(params, dict) else None
        version = meta.get(META_VERSION) if isinstance(meta, dict) else None

        def ok(result: dict[str, Any]) -> tuple[int, Any, dict[str, str]]:
            return 200, {"jsonrpc": "2.0", "id": request_id, "result": result}, {}

        def err(
            status: int, code: int, text: str, data: Any = None
        ) -> tuple[int, Any, dict[str, str]]:
            error: dict[str, Any] = {"code": code, "message": text}
            if data is not None:
                error["data"] = data
            return status, {"jsonrpc": "2.0", "id": request_id, "error": error}, {}

        if request_id is None:
            return 202, None, {}
        if method is None and ("result" in message or "error" in message):
            self.client_responses.append(message)
            return 202, None, {}

        if self.era == "modern":
            if version is None:
                return err(400, -32602, "missing _meta protocol version")
            if version != MODERN:
                return err(400, -32022, "Unsupported protocol version", {"supported": [MODERN]})
            if (
                headers.get("mcp-protocol-version") != version
                or headers.get("mcp-method") != method
            ):
                return err(400, -32020, "Header mismatch")
            name = params.get("name")
            if method == "tools/call" and headers.get("mcp-name") != name:
                return err(400, -32020, "Header mismatch: Mcp-Name")
            if method == "tools/call" and name == "echo_region":
                region = params.get("arguments", {}).get("region")
                if headers.get("mcp-param-region") != region:
                    return err(400, -32020, "Header mismatch: Mcp-Param-Region")
            if method == "server/discover":
                return ok(
                    {
                        "resultType": "complete",
                        "supportedVersions": [MODERN],
                        "capabilities": {"tools": {}},
                        "_meta": {
                            "io.modelcontextprotocol/serverInfo": {
                                "name": "http-modern",
                                "version": "1.0",
                            }
                        },
                    }
                )
        else:
            if method == "initialize":
                session = f"session-{len(self.sessions) + 1}"
                self.sessions.add(session)
                status, body, _ = ok(
                    {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "http-legacy", "version": "1.0"},
                        "instructions": "Legacy over HTTP.",
                    }
                )
                return status, body, {"Mcp-Session-Id": session}
            if headers.get("mcp-session-id") not in self.sessions:
                return (
                    400,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32000,
                            "message": "Bad Request: No valid session ID provided",
                        },
                    },
                    {},
                )

        if method == "tools/list":
            return ok({"resultType": "complete", "tools": [*TOOLS, ECHO_TOOL]})
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name == "add":
                total = arguments.get("a", 0) + arguments.get("b", 0)
                return ok({"content": [{"type": "text", "text": str(total)}]})
            if name == "echo_region":
                return ok({"content": [{"type": "text", "text": str(arguments.get("region"))}]})
            if name == "flaky":
                return ok({"content": [{"type": "text", "text": "flaky"}], "isError": True})
            return ok({"content": [{"type": "text", "text": "ok"}]})
        return err(404 if self.era == "modern" else 200, -32601, f"Method not found: {method}")

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # silence the test output
                return

            def _headers(self) -> dict[str, str]:
                return {k.lower(): v for k, v in self.headers.items()}

            def do_DELETE(self) -> None:
                fake.deleted.append(self._headers().get("mcp-session-id", ""))
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self) -> None:
                headers = self._headers()
                length = int(headers.get("content-length", "0"))
                message = json.loads(self.rfile.read(length) or b"{}")
                fake.requests.append({"headers": headers, "body": message})
                if (
                    fake.token is not None
                    and headers.get("authorization") != f"Bearer {fake.token}"
                ):
                    self._write(401, b"", "text/plain", {})
                    return
                status, body, extra = fake.answer(message, headers)
                if body is None:
                    self._write(status, b"", "text/plain", extra)
                elif fake.sse and status == 200:
                    progress = {
                        "jsonrpc": "2.0",
                        "method": "notifications/progress",
                        "params": {"progress": 1},
                    }
                    ping = {"jsonrpc": "2.0", "id": "srv-ping", "method": "ping"}
                    payload = (
                        ": keep-alive\n\n"
                        + (f"event: message\ndata: {json.dumps(ping)}\n\n" if fake.ping else "")
                        + f"event: message\ndata: {json.dumps(progress)}\n\n"
                        f"event: message\ndata: {json.dumps(body)}\n\n"
                    ).encode()
                    self._write(status, payload, "text/event-stream", extra)
                else:
                    self._write(status, json.dumps(body).encode(), "application/json", extra)

            def _write(
                self, status: int, payload: bytes, content_type: str, extra: dict[str, str]
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                for key, value in extra.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(payload)

        return Handler
