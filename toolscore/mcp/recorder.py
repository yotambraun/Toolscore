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

With a :class:`~toolscore.mcp.faults.FaultInjector` it is also a
fault-injection proxy: chosen calls get an error, a warning, an empty or
truncated result, a delay or no answer at all (see :mod:`toolscore.mcp.faults`).
The session file then records what the client saw, marks each injected response
with ``injected``, and lists every injection under ``injections``, so the
honesty checks know which failures were real. Only single-message lines are
injected; JSON-RPC batches pass through unchanged.

Command line::

    toolscore mcp record "python my_server.py" -o session.json
    toolscore mcp proxy "python my_server.py" --inject faults.json -o session.json
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
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.mcp.faults import FaultInjector, Injection

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


#: Seconds to wait for the server to exit after its input closes.
_EXIT_TIMEOUT = 10.0


class MCPRecorder:
    """A transparent stdio proxy that records ``tools/call`` traffic.

    Args:
        command: The server launch command vector.
        output: Path of the trace file to write.
        env: Extra environment variables for the server process.
        cwd: Working directory for the server process.
        injector: Injects faults into chosen calls (``toolscore mcp proxy --inject``).

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
        injector: FaultInjector | None = None,
    ) -> None:
        if not command:
            raise ValueError("MCPRecorder requires a non-empty server command.")
        self._command = list(command)
        self._output = Path(output)
        self._env = dict(env or {})
        self._cwd = cwd
        self._injector = injector
        self._lock = threading.Lock()
        self._out_lock = threading.Lock()
        self._pending: dict[tuple[str, Any], float] = {}
        self._messages: list[dict[str, Any]] = []
        #: Forwarded calls whose response will be modified, by request id.
        self._modify: dict[tuple[str, Any], Injection] = {}
        #: Every injection made, as recorded in the session file.
        self.injections: list[dict[str, Any]] = []
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

    def _note_server_line(self, line: str, injected: dict[str, Any] | None = None) -> None:
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
                if injected is not None:
                    recorded["injected"] = injected
                recorded["duration"] = round(time.perf_counter() - started, 6)
                self._messages.append(recorded)
                self.calls_recorded += 1
                completed = True
        if completed:
            self.write()

    # -- fault injection ----------------------------------------------------

    def _intercept_client(self, line: str) -> tuple[str | None, str | None]:
        """Decide what a client line becomes: ``(line for the server, line for the client)``.

        Without an injector, or for anything but a single ``tools/call``
        request, the line goes to the server unchanged.
        """
        if self._injector is None:
            return line, None
        try:
            message = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return line, None
        if not isinstance(message, dict) or message.get("method") != "tools/call":
            return line, None
        key = _hashable_id(message.get("id"))
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        assert isinstance(params, dict)
        tool = params.get("name")
        if key is None or not isinstance(tool, str):
            return line, None
        injection = self._injector.decide(tool)
        if injection is None:
            return line, None
        record = injection.record(message.get("id"))
        with self._lock:
            self.injections.append(record)
        if injection.rule.forwards:
            with self._lock:
                self._modify[key] = injection
            return line, None
        meta = params.get("_meta")
        modern = isinstance(meta, dict) and "io.modelcontextprotocol/protocolVersion" in meta
        response = injection.synthesize(message.get("id"), modern)
        self._note_client_line(line)
        if response is None:
            # A timeout: nothing reaches the client. The recording still shows
            # the call as failed, marked as never sent.
            self._note_response(
                {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "error": {"code": -32001, "message": "no response (injected timeout)"},
                    "injected": record,
                    "not_sent": True,
                }
            )
            return None, None
        self._note_response({**response, "injected": record})
        return None, json.dumps(response) + "\n"

    def _intercept_server(self, line: str) -> tuple[str, dict[str, Any] | None]:
        """Apply a forwarded fault to a server line; returns the line and its injection record."""
        if not self._modify:
            return line, None
        try:
            message = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return line, None
        if not isinstance(message, dict) or "method" in message:
            return line, None
        key = _hashable_id(message.get("id"))
        with self._lock:
            injection = self._modify.pop(key, None) if key is not None else None
        if injection is None:
            return line, None
        if injection.fault == "delay":
            time.sleep(injection.rule.seconds)
        record = injection.record(message.get("id"))
        return json.dumps(injection.modify(message)) + "\n", record

    def _note_response(self, message: dict[str, Any]) -> None:
        """Record a response the proxy produced itself."""
        key = _hashable_id(message.get("id"))
        with self._lock:
            started = self._pending.pop(key, None) if key is not None else None
            recorded = dict(message)
            recorded["duration"] = (
                round(time.perf_counter() - started, 6) if started is not None else 0.0
            )
            self._messages.append(recorded)
            self.calls_recorded += 1
        self.write()

    def write(self) -> None:
        """Write the trace file atomically (a temporary file, then a rename)."""
        with self._lock:
            payload: dict[str, Any] = {
                "format": TRACE_FORMAT,
                "recorded_by": "toolscore mcp proxy" if self._injector else "toolscore mcp record",
                "server_command": self._command,
                "messages": list(self._messages),
            }
            if self._injector is not None:
                payload["fault_spec"] = self._injector.spec.to_dict()
                payload["injections"] = list(self.injections)
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

        def to_client(line: str) -> None:
            with self._out_lock:
                client_out.write(line)
                client_out.flush()

        def client_to_server() -> None:
            try:
                for line in client_in:
                    for_server, for_client = self._intercept_client(line)
                    if for_client is not None:
                        to_client(for_client)
                    if for_server is None:
                        continue
                    self._note_client_line(for_server)
                    server_in.write(for_server)
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
                line, injected = self._intercept_server(line)
                to_client(line)
                self._note_server_line(line, injected)
        except (BrokenPipeError, OSError, ValueError):
            pass  # the client went away; stop the server below
        finally:
            # Close the server's stdin so it sees end-of-input and exits, even when
            # the client stopped reading but has not closed its side.
            with contextlib.suppress(OSError, ValueError):
                server_in.close()
            try:
                return_code = process.wait(timeout=_EXIT_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    return_code = process.wait(timeout=_EXIT_TIMEOUT)
                except subprocess.TimeoutExpired:
                    process.kill()
                    return_code = process.wait()
            errors.join(timeout=2.0)
            self.write()
        return return_code
