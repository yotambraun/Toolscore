"""Zero-dependency synchronous MCP client over subprocess stdio.

This module implements a minimal `JSON-RPC 2.0`_ client speaking the `Model
Context Protocol`_ (MCP) *stdio* transport, using only the Python standard
library (``subprocess``, ``json``, ``threading``, ``queue``).

The stdio transport frames messages as newline-delimited JSON: each JSON-RPC
message is a single JSON object on its own line written to the server's stdin,
and responses arrive the same way on stdout. The server's stderr carries
free-form log output, which we drain on a background thread so it can never
block the protocol.

Typical usage::

    with MCPStdioClient(["python", "server.py"]) as client:
        for tool in client.list_tools():
            print(tool.name)
        result = client.call_tool("add", {"a": 2, "b": 3})
        print(result.content)

.. _JSON-RPC 2.0: https://www.jsonrpc.org/specification
.. _Model Context Protocol: https://modelcontextprotocol.io/
"""

from __future__ import annotations

import collections
import contextlib
import json
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

#: Protocol version this client advertises during the handshake.
DEFAULT_PROTOCOL_VERSION = "2025-06-18"

#: Number of trailing stderr characters surfaced in diagnostic error messages.
_STDERR_TAIL_CHARS = 2000


def _client_version() -> str:
    """Return the installed toolscore package version, or a fallback.

    Returns:
        The distribution version string, or ``"0.0.0"`` if the package metadata
        cannot be located (for example when running from a source checkout that
        has not been installed).
    """
    for dist in ("tool-scorer", "toolscore"):
        try:
            return _pkg_version(dist)
        except PackageNotFoundError:
            continue
    return "0.0.0"


@dataclass
class MCPToolDef:
    """A tool advertised by an MCP server.

    Attributes:
        name: The tool's unique name.
        description: Human-readable description (may be empty).
        input_schema: The JSON Schema for the tool's arguments, taken verbatim
            from the server's ``inputSchema`` field.
    """

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class MCPToolResult:
    """The outcome of a ``tools/call`` invocation.

    Attributes:
        content: The parsed ``content`` list from the call result (or the raw
            error payload when the call failed at the JSON-RPC level).
        is_error: ``True`` if the result reported ``isError`` or the response was
            a JSON-RPC error.
        raw: The full JSON-RPC response object.
        duration: Wall-clock seconds measured client-side for the round trip.
    """

    content: Any
    is_error: bool
    raw: dict[str, Any]
    duration: float


# Safety cap on tools/list pagination to bound a misbehaving server.
_MAX_LIST_TOOLS_PAGES = 100


class MCPError(Exception):
    """Raised on MCP protocol or transport failures."""


class MCPTimeoutError(MCPError):
    """Raised when a request does not receive a response within the timeout."""


class MCPStdioClient:
    """Synchronous MCP client communicating with a server over stdio.

    The client spawns the server as a subprocess, performs the MCP initialize
    handshake, and exposes ``list_tools`` / ``call_tool`` helpers. A daemon
    thread reads stdout lines into a queue and another drains stderr, so neither
    stream can deadlock the protocol.

    The instance is a context manager: entering calls :meth:`start` and exiting
    calls :meth:`close`.
    """

    def __init__(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the client.

        Args:
            command: The command vector used to launch the server, e.g.
                ``["python", "server.py", "--flag"]``.
            env: Environment variables to overlay on top of the current
                process environment (``os.environ``); ``PATH`` and friends are
                preserved unless explicitly overridden.
            cwd: Working directory for the server process.
            timeout: Default per-request timeout in seconds.
        """
        self._command = list(command)
        self._extra_env = dict(env) if env else {}
        self._cwd = str(cwd) if cwd is not None else None
        self.timeout = timeout

        self._process: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        # Bounded buffer: verbose servers can emit unlimited stderr, so cap the
        # retained lines to the most recent 500 (only the tail is ever surfaced).
        self._stderr_lines: collections.deque[str] = collections.deque(maxlen=500)
        self._stderr_lock = threading.Lock()

        self._next_id = 0
        self._started = False

        #: Notifications/requests initiated by the server that we do not handle.
        self.server_messages: list[dict[str, Any]] = []
        #: Protocol version negotiated during the handshake.
        self.protocol_version: str = DEFAULT_PROTOCOL_VERSION
        #: ``serverInfo`` returned by the initialize handshake.
        self.server_info: dict[str, Any] = {}

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> MCPStdioClient:
        """Start the server and perform the handshake.

        Returns:
            This client instance.
        """
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the server process on context exit."""
        self.close()

    def start(self) -> dict[str, Any]:
        """Spawn the server process and run the initialize handshake.

        Returns:
            The ``serverInfo`` dictionary reported by the server (may be empty
            if the server omits it).

        Raises:
            MCPError: If the process cannot be spawned or the handshake fails.
        """
        if self._started:
            raise MCPError("Client already started.")

        full_env = {**os.environ, **self._extra_env}
        try:
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=full_env,
                cwd=self._cwd,
                text=True,
                encoding="utf-8",
                bufsize=1,  # line-buffered
            )
        except (OSError, ValueError) as exc:
            raise MCPError(f"Failed to launch MCP server {self._command!r}: {exc}") from exc

        self._started = True
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()

        try:
            self.server_info = self._handshake()
        except Exception:
            self.close()
            raise
        return self.server_info

    def close(self) -> None:
        """Shut down the server process gracefully.

        Closes stdin, waits briefly for the process to exit, then terminates and
        finally kills it if necessary. Safe to call multiple times.
        """
        process = self._process
        if process is None:
            return

        if process.stdin is not None:
            with contextlib.suppress(OSError, ValueError):
                process.stdin.close()

        if process.poll() is None:
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=2.0)

        # Unblock any pending queue consumers.
        self._stdout_queue.put(None)
        self._process = None
        self._started = False

    # -- handshake & protocol ---------------------------------------------

    def _handshake(self) -> dict[str, Any]:
        """Perform the MCP initialize handshake.

        Returns:
            The ``serverInfo`` dictionary from the initialize response.

        Raises:
            MCPError: If the server returns an error to ``initialize``.
        """
        result = self._request(
            "initialize",
            {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "toolscore", "version": _client_version()},
            },
        )

        negotiated = result.get("protocolVersion")
        if isinstance(negotiated, str) and negotiated:
            self.protocol_version = negotiated

        self._notify("notifications/initialized", {})

        server_info = result.get("serverInfo", {})
        return server_info if isinstance(server_info, dict) else {}

    def list_tools(self) -> list[MCPToolDef]:
        """List the tools advertised by the server.

        Follows pagination via the ``nextCursor`` field until exhausted. Guards
        against a misbehaving server that paginates forever: a repeated cursor
        or more than ``_MAX_LIST_TOOLS_PAGES`` pages raises :class:`MCPError`.

        Returns:
            The advertised tools as :class:`MCPToolDef` objects.

        Raises:
            MCPError: On a protocol or transport failure, or if the server
                paginates in a loop (repeated cursor) or beyond the page cap.
            MCPTimeoutError: If the server does not respond in time.
        """
        tools: list[MCPToolDef] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _page in range(_MAX_LIST_TOOLS_PAGES):
            params: dict[str, Any] = {}
            if cursor is not None:
                params["cursor"] = cursor
            result = self._request("tools/list", params)

            for tool in result.get("tools", []) or []:
                if not isinstance(tool, dict):
                    continue
                schema = tool.get("inputSchema", {})
                tools.append(
                    MCPToolDef(
                        name=str(tool.get("name", "")),
                        description=str(tool.get("description", "")),
                        input_schema=schema if isinstance(schema, dict) else {},
                    )
                )

            next_cursor = result.get("nextCursor")
            if not next_cursor:
                return tools
            next_cursor = str(next_cursor)
            if next_cursor in seen_cursors:
                raise MCPError(
                    f"MCP server returned a repeated pagination cursor "
                    f"{next_cursor!r} from tools/list; aborting to avoid an "
                    "infinite pagination loop."
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        raise MCPError(
            f"MCP server exceeded the tools/list pagination cap of "
            f"{_MAX_LIST_TOOLS_PAGES} pages; aborting to avoid an infinite loop."
        )

    def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult:
        """Invoke a tool on the server.

        Args:
            name: The tool name.
            arguments: Arguments matching the tool's input schema.

        Returns:
            The :class:`MCPToolResult`. ``is_error`` is ``True`` both when the
            server reports ``isError`` and when the call yields a JSON-RPC error.

        Raises:
            MCPTimeoutError: If the server does not respond in time.
            MCPError: On a transport failure (e.g. the process dies).
        """
        started = time.perf_counter()
        response = self._roundtrip("tools/call", {"name": name, "arguments": arguments})
        duration = time.perf_counter() - started

        if "error" in response:
            return MCPToolResult(
                content=response["error"],
                is_error=True,
                raw=response,
                duration=duration,
            )

        result = response.get("result", {})
        if not isinstance(result, dict):
            result = {}
        return MCPToolResult(
            content=result.get("content", []),
            is_error=bool(result.get("isError", False)),
            raw=response,
            duration=duration,
        )

    # -- request plumbing --------------------------------------------------

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a request and return its ``result``, raising on JSON-RPC errors.

        Args:
            method: The JSON-RPC method name.
            params: The request parameters.

        Returns:
            The ``result`` object from the response.

        Raises:
            MCPError: If the server returns a JSON-RPC error.
            MCPTimeoutError: If no response arrives in time.
        """
        response = self._roundtrip(method, params)
        if "error" in response:
            error = response["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            code = error.get("code") if isinstance(error, dict) else None
            raise MCPError(f"MCP error for {method!r} (code={code}): {message}")
        result = response.get("result", {})
        return result if isinstance(result, dict) else {}

    def _roundtrip(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a request and wait for the response with the matching id.

        Server-initiated notifications and requests received while waiting are
        stored in :attr:`server_messages` and ignored.

        Args:
            method: The JSON-RPC method name.
            params: The request parameters.

        Returns:
            The full JSON-RPC response object.

        Raises:
            MCPError: If the client is not started or the process died.
            MCPTimeoutError: If no matching response arrives within the timeout.
        """
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})

        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPTimeoutError(
                    f"Timed out after {self.timeout}s waiting for response to {method!r}."
                )
            try:
                message = self._stdout_queue.get(timeout=remaining)
            except queue.Empty:
                raise MCPTimeoutError(
                    f"Timed out after {self.timeout}s waiting for response to {method!r}."
                ) from None

            if message is None:
                # Reader thread signalled EOF / process exit.
                raise MCPError(
                    f"MCP server exited before responding to {method!r}. {self._diagnostics()}"
                )

            if message.get("id") == request_id and ("result" in message or "error" in message):
                return message

            # Notification or unrelated server-initiated message: stash & ignore.
            self.server_messages.append(message)

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (a request without an id).

        Args:
            method: The notification method name.
            params: The notification parameters.
        """
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _send(self, message: dict[str, Any]) -> None:
        """Serialize and write a single JSON-RPC message to the server's stdin.

        Args:
            message: The JSON-RPC message object.

        Raises:
            MCPError: If the client is not started or the write fails (which
                typically indicates the process has died).
        """
        process = self._process
        if process is None or process.stdin is None:
            raise MCPError("MCP client is not started.")
        if process.poll() is not None:
            raise MCPError(
                f"MCP server has exited (returncode={process.returncode}). {self._diagnostics()}"
            )
        line = json.dumps(message, separators=(",", ":")) + "\n"
        try:
            process.stdin.write(line)
            process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise MCPError(
                f"Failed to write to MCP server stdin: {exc}. {self._diagnostics()}"
            ) from exc

    # -- background readers ------------------------------------------------

    def _read_stdout(self) -> None:
        """Read newline-delimited JSON from stdout into the response queue.

        Runs on a daemon thread. Non-JSON lines are ignored. On EOF a sentinel
        (``None``) is enqueued so waiting consumers can detect process exit.
        """
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                message = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self._stdout_queue.put(message)
        # EOF: signal consumers.
        self._stdout_queue.put(None)

    def _read_stderr(self) -> None:
        """Drain the server's stderr into an in-memory buffer.

        Runs on a daemon thread so verbose server logging cannot block the
        protocol streams.
        """
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            with self._stderr_lock:
                self._stderr_lines.append(line)

    def _stderr_tail(self) -> str:
        """Return the trailing portion of captured stderr.

        Returns:
            Up to :data:`_STDERR_TAIL_CHARS` characters of the most recent
            stderr output.
        """
        with self._stderr_lock:
            text = "".join(self._stderr_lines)
        return text[-_STDERR_TAIL_CHARS:]

    def _diagnostics(self) -> str:
        """Build a diagnostic suffix including return code and stderr tail.

        Returns:
            A human-readable diagnostic string for inclusion in error messages.
        """
        returncode = self._process.returncode if self._process is not None else None
        tail = self._stderr_tail().strip()
        parts = [f"returncode={returncode}"]
        if tail:
            parts.append(f"stderr tail:\n{tail}")
        return " ".join(parts)
