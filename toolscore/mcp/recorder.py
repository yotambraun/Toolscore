"""Record real MCP tool traffic with a transparent stdio proxy.

:class:`MCPRecorder` sits between any MCP client (an IDE, a desktop app, an
agent framework) and an MCP server that speaks the stdio transport. Every line
the client writes goes to the server unchanged, every line the server writes
goes back unchanged, and the server's stderr passes through, so neither side can
tell the recorder is there.

While relaying, it keeps each ``tools/call`` request and the response with the
same JSON-RPC id, plus the measured round-trip ``duration``, and writes them as
a trace that :class:`toolscore.adapters.mcp.MCPAdapter` reads (one call per
request, with result, error and duration). Nothing else is recorded:
``initialize``, notifications and ``tools/list`` are protocol, not tool calls.

The trace file is rewritten after every completed call, so a crashed session
still leaves a usable trace.

Command line::

    toolscore mcp record "python my_server.py" -o session.json
    toolscore eval gold.json session.json --format mcp
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO, Any

#: Value of the ``format`` field in a recorded trace file.
TRACE_FORMAT = "mcp"


def _hashable_id(request_id: Any) -> tuple[str, Any] | None:
    """A JSON-RPC id usable as a dict key (ints and strings never collide)."""
    if isinstance(request_id, bool) or not isinstance(request_id, (int, str)):
        return None
    return (type(request_id).__name__, request_id)


def _messages(line: str) -> list[dict[str, Any]]:
    """Parse one stdio line into JSON-RPC messages (a single message or a batch)."""
    try:
        decoded = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(decoded, dict):
        return [decoded]
    if isinstance(decoded, list):
        return [item for item in decoded if isinstance(item, dict)]
    return []


class MCPRecorder:
    """A transparent stdio proxy that records ``tools/call`` traffic.

    Args:
        command: The server launch command vector.
        output: Path of the trace file to write.
        env: Extra environment variables for the server process.
        cwd: Working directory for the server process.

    Example:
        >>> recorder = MCPRecorder(["python", "server.py"], Path("session.json"))
        >>> exit_code = recorder.run()  # relays stdin/stdout until the client disconnects
    """

    def __init__(
        self,
        command: list[str],
        output: str | Path,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        if not command:
            raise ValueError("MCPRecorder requires a non-empty server command.")
        self._command = list(command)
        self._output = Path(output)
        self._env = dict(env or {})
        self._cwd = cwd
        self._lock = threading.Lock()
        self._pending: dict[tuple[str, Any], float] = {}
        self._messages: list[dict[str, Any]] = []
        #: Number of completed tool calls recorded so far.
        self.calls_recorded = 0

    # -- recording ----------------------------------------------------------

    def _note_client_line(self, line: str) -> None:
        """Remember ``tools/call`` requests sent by the client."""
        for message in _messages(line):
            if message.get("method") != "tools/call":
                continue
            key = _hashable_id(message.get("id"))
            if key is None:
                continue
            with self._lock:
                self._pending[key] = time.perf_counter()
                self._messages.append(message)

    def _note_server_line(self, line: str) -> None:
        """Pair responses with recorded requests and save the trace."""
        completed = False
        for message in _messages(line):
            if "method" in message or not ("result" in message or "error" in message):
                continue
            key = _hashable_id(message.get("id"))
            with self._lock:
                started = self._pending.pop(key, None) if key is not None else None
                if started is None:
                    continue
                recorded = dict(message)
                recorded["duration"] = round(time.perf_counter() - started, 6)
                self._messages.append(recorded)
                self.calls_recorded += 1
                completed = True
        if completed:
            self.write()

    def write(self) -> None:
        """Write the trace file atomically (a temporary file, then a rename)."""
        with self._lock:
            payload = {
                "format": TRACE_FORMAT,
                "recorded_by": "toolscore mcp record",
                "server_command": self._command,
                "messages": list(self._messages),
            }
        self._output.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._output.with_name(self._output.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._output)

    # -- relaying -----------------------------------------------------------

    def run(
        self,
        stdin: IO[str] | None = None,
        stdout: IO[str] | None = None,
        stderr: IO[str] | None = None,
    ) -> int:
        """Relay a whole session and return the server's exit code.

        Reads client messages from ``stdin`` until it closes, relays server
        output to ``stdout`` until the server exits, and passes the server's
        stderr through. The trace is written at the end even if no tool was
        called.

        Args:
            stdin: Client-to-server stream (default: ``sys.stdin``).
            stdout: Server-to-client stream (default: ``sys.stdout``).
            stderr: Where the server's stderr goes (default: ``sys.stderr``).

        Returns:
            The server process exit code.
        """
        client_in = stdin if stdin is not None else sys.stdin
        client_out = stdout if stdout is not None else sys.stdout
        log = stderr if stderr is not None else sys.stderr

        process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **self._env},
            cwd=self._cwd,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        assert process.stdin is not None and process.stdout is not None
        assert process.stderr is not None
        server_in, server_out, server_err = process.stdin, process.stdout, process.stderr

        def client_to_server() -> None:
            try:
                for line in client_in:
                    self._note_client_line(line)
                    server_in.write(line)
                    server_in.flush()
            except (BrokenPipeError, OSError, ValueError):
                pass
            finally:
                with contextlib.suppress(OSError):
                    server_in.close()

        def pass_stderr() -> None:
            for line in server_err:
                log.write(line)
                log.flush()

        forward = threading.Thread(target=client_to_server, daemon=True)
        errors = threading.Thread(target=pass_stderr, daemon=True)
        forward.start()
        errors.start()

        try:
            for line in server_out:
                client_out.write(line)
                client_out.flush()
                self._note_server_line(line)
        finally:
            return_code = process.wait()
            errors.join(timeout=2.0)
            self.write()
        return return_code
