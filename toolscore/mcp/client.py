"""Synchronous MCP clients for the stdio and Streamable HTTP transports.

This module implements a small `JSON-RPC 2.0`_ client for the `Model Context
Protocol`_ (MCP). The protocol logic lives in :class:`MCPClient`; two
transports sit underneath it:

* :class:`MCPStdioClient` launches the server as a subprocess and speaks
  newline-delimited JSON over its stdin/stdout. It uses only the Python
  standard library.
* :class:`MCPHttpClient` talks to a remote server over Streamable HTTP. It
  needs ``httpx`` (``pip install "tool-scorer[http]"``).

Both clients are *dual-era*. MCP revision ``2026-07-28`` removed the
``initialize`` handshake: every request carries its protocol version, client
identity and capabilities in ``_meta``, and servers implement
``server/discover``. Servers built on earlier revisions (``2025-11-25`` and
before) still expect the handshake. Following the specification's backward
compatibility rules, the client first probes with ``server/discover``; a
discovery result, or a recognized modern error, means a modern server. Any
other error, an HTTP ``4xx`` without a modern error body, or no answer within
the probe timeout means a legacy server, and the client falls back to
``initialize`` with :data:`LEGACY_PROTOCOL_VERSION`.

Typical usage::

    with MCPStdioClient(["python", "server.py"]) as client:
        print(client.protocol_version, client.era)
        for tool in client.list_tools():
            print(tool.name)
        result = client.call_tool("add", {"a": 2, "b": 3})
        print(result.text)

.. _JSON-RPC 2.0: https://www.jsonrpc.org/specification
.. _Model Context Protocol: https://modelcontextprotocol.io/specification/versioning
"""

from __future__ import annotations

import base64
import collections
import contextlib
import json
import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit

from toolscore.mcp.content import content_to_text

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

#: The current MCP revision (verified against modelcontextprotocol.io on
#: 2026-11-01). Stateless: no ``initialize``, the version travels in ``_meta``.
MODERN_PROTOCOL_VERSION = "2026-07-28"

#: The newest handshake-based revision, used for the ``initialize`` fallback.
LEGACY_PROTOCOL_VERSION = "2025-11-25"

#: Kept for backward compatibility: the version this client prefers.
DEFAULT_PROTOCOL_VERSION = MODERN_PROTOCOL_VERSION

#: Modern revisions this client speaks, newest first.
MODERN_PROTOCOL_VERSIONS: tuple[str, ...] = (MODERN_PROTOCOL_VERSION,)

#: Handshake-based revisions this client accepts from ``initialize``, newest first.
LEGACY_PROTOCOL_VERSIONS: tuple[str, ...] = (
    LEGACY_PROTOCOL_VERSION,
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)

#: JSON-RPC error codes the 2026-07-28 revision defines (HeaderMismatch,
#: MissingRequiredClientCapability, UnsupportedProtocolVersion). Receiving one
#: identifies a modern server.
MODERN_ERROR_CODES = frozenset({-32020, -32021, -32022})

#: ``UnsupportedProtocolVersionError``; its ``data.supported`` lists the versions.
UNSUPPORTED_PROTOCOL_VERSION_CODE = -32022

#: Seconds to wait for a ``server/discover`` answer before treating the server
#: as legacy (some legacy servers never answer requests sent before ``initialize``).
DEFAULT_PROBE_TIMEOUT = 5.0

#: Reserved ``_meta`` keys of the per-request protocol fields.
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

#: Number of trailing stderr characters surfaced in diagnostic error messages.
_STDERR_TAIL_CHARS = 2000

#: Characters of an HTTP error body quoted in an error message.
_HTTP_BODY_EXCERPT = 300

#: How the client picks the protocol era.
ProtocolMode = Literal["auto", "modern", "legacy"]


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
        annotations: The tool's ``annotations`` object (behavior hints such as
            ``readOnlyHint`` and ``destructiveHint``); empty when absent.
        output_schema: The tool's ``outputSchema``, or ``None`` when the tool
            declares none. Results must then carry conforming ``structuredContent``.
        title: The tool's display ``title``, or ``None``.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    title: str | None = None


@dataclass
class MCPToolResult:
    """The outcome of a ``tools/call`` invocation.

    Attributes:
        content: The parsed ``content`` list from the call result (or the raw
            error payload when the call failed at the JSON-RPC level).
        is_error: ``True`` if the result reported ``isError``, the response was
            a JSON-RPC error, or the server asked for client input this client
            cannot provide.
        raw: The full JSON-RPC response object.
        duration: Wall-clock seconds measured client-side for the round trip.
    """

    content: Any
    is_error: bool
    raw: dict[str, Any]
    duration: float

    @property
    def text(self) -> str:
        """The result as the text an MCP client would show a model.

        Renders every content item, not only ``text``: embedded resources (how
        many servers return file contents), resource links, and placeholders for
        images and audio. See :func:`toolscore.mcp.content.content_to_text`.
        """
        return content_to_text(self.content)

    @property
    def structured_content(self) -> Any:
        """The result's ``structuredContent``, or ``None`` when absent."""
        result = self.raw.get("result")
        return result.get("structuredContent") if isinstance(result, dict) else None

    @property
    def has_structured_content(self) -> bool:
        """Whether the result carries a ``structuredContent`` field at all."""
        result = self.raw.get("result")
        return isinstance(result, dict) and "structuredContent" in result


# Safety cap on tools/list pagination to bound a misbehaving server.
_MAX_LIST_TOOLS_PAGES = 100


class MCPError(Exception):
    """Raised on MCP protocol or transport failures."""


class MCPTimeoutError(MCPError):
    """Raised when a request does not receive a response within the timeout."""


class MCPHTTPStatusError(MCPError):
    """Raised when an HTTP response carries an error status and no JSON-RPC body.

    Attributes:
        status: The HTTP status code.
    """

    def __init__(self, message: str, status: int) -> None:
        """Initialize the error.

        Args:
            message: The error message.
            status: The HTTP status code.
        """
        super().__init__(message)
        self.status = status


def _error_code(response: Mapping[str, Any]) -> int | None:
    """The integer ``error.code`` of a JSON-RPC response, if any."""
    error = response.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, int) and not isinstance(code, bool):
            return code
    return None


def _error_message(response: Mapping[str, Any]) -> str:
    """The ``error.message`` of a JSON-RPC response, or its repr."""
    error = response.get("error")
    if isinstance(error, dict):
        return str(error.get("message", ""))
    return str(error)


def _supported_versions(response: Mapping[str, Any]) -> list[str]:
    """The ``data.supported`` list of an ``UnsupportedProtocolVersionError``."""
    error = response.get("error")
    data = error.get("data") if isinstance(error, dict) else None
    supported = data.get("supported") if isinstance(data, dict) else None
    if isinstance(supported, list):
        return [v for v in supported if isinstance(v, str)]
    return []


class MCPClient:
    """Transport-independent MCP protocol logic (dual-era).

    Subclasses provide the transport by implementing :meth:`_open`,
    :meth:`_close_transport`, :meth:`_roundtrip` and :meth:`_notify`. This class
    handles era detection, per-request ``_meta``, ``tools/list`` pagination and
    ``tools/call``.

    The instance is a context manager: entering calls :meth:`start` and exiting
    calls :meth:`close`.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        protocol: ProtocolMode = "auto",
        probe_timeout: float | None = None,
    ) -> None:
        """Initialize the protocol state.

        Args:
            timeout: Default per-request timeout in seconds.
            protocol: ``"auto"`` (probe with ``server/discover``, fall back to
                ``initialize``), ``"modern"`` (2026-07-28 only) or ``"legacy"``
                (``initialize`` handshake only).
            probe_timeout: Seconds to wait for the ``server/discover`` probe in
                ``"auto"`` mode before falling back. Defaults to
                ``min(timeout, DEFAULT_PROBE_TIMEOUT)``.
        """
        if protocol not in ("auto", "modern", "legacy"):
            raise ValueError(f"protocol must be 'auto', 'modern' or 'legacy', got {protocol!r}")
        self.timeout = timeout
        self.protocol_mode: ProtocolMode = protocol
        self.probe_timeout = (
            probe_timeout if probe_timeout is not None else min(timeout, DEFAULT_PROBE_TIMEOUT)
        )
        self._next_id = 0
        self._started = False
        self._tool_schemas: dict[str, dict[str, Any]] = {}

        #: Notifications/requests initiated by the server that we do not handle,
        #: and responses that arrived after their request gave up waiting.
        self.server_messages: list[dict[str, Any]] = []
        #: Protocol version in use: the version sent in ``_meta`` (modern) or
        #: the one ``initialize`` negotiated (legacy).
        self.protocol_version: str = DEFAULT_PROTOCOL_VERSION
        #: ``"modern"`` (per-request ``_meta``) or ``"legacy"`` (``initialize``
        #: handshake) once started; ``None`` before.
        self.era: str | None = None
        #: The server's self-reported name and version.
        self.server_info: dict[str, Any] = {}
        #: The server's ``instructions``, or ``None``. MCP clients pass these to
        #: the model, so they are part of what the model reads (and of its
        #: context cost).
        self.server_instructions: str | None = None
        #: The server's ``capabilities`` object.
        self.server_capabilities: dict[str, Any] = {}
        #: Protocol versions the server listed in ``server/discover`` (modern only).
        self.server_versions: list[str] = []

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> MCPClient:
        """Connect and agree on a protocol version.

        Returns:
            This client instance.
        """
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the connection on context exit."""
        self.close()

    def start(self) -> dict[str, Any]:
        """Open the transport and agree on a protocol version with the server.

        Returns:
            The server's self-reported ``serverInfo`` (may be empty).

        Raises:
            MCPError: If the transport cannot be opened or no protocol version
                can be agreed on.
        """
        if self._started:
            raise MCPError("Client already started.")
        self._open()
        self._started = True
        try:
            self._negotiate()
        except BaseException:
            self.close()
            raise
        return self.server_info

    def close(self) -> None:
        """Close the transport. Safe to call multiple times."""
        self._close_transport()
        self._started = False

    # -- transport hooks (implemented by subclasses) ------------------------

    def _open(self) -> None:
        """Open the underlying transport."""
        raise NotImplementedError

    def _close_transport(self) -> None:
        """Close the underlying transport (idempotent)."""
        raise NotImplementedError

    def _roundtrip(
        self,
        method: str,
        params: dict[str, Any],
        request_id: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send one request and return the JSON-RPC response with its id.

        Args:
            method: The JSON-RPC method name.
            params: The request parameters (``_meta`` already applied).
            request_id: The id to use; a fresh one is allocated when ``None``.
            timeout: Seconds to wait; :attr:`timeout` when ``None``.

        Returns:
            The full JSON-RPC response object (``result`` or ``error``).
        """
        raise NotImplementedError

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification."""
        raise NotImplementedError

    def _reset_session(self) -> None:
        """Forget transport-level session state before a fresh ``initialize``."""

    # -- era detection -------------------------------------------------------

    def _new_id(self) -> int:
        """Allocate the next request id."""
        self._next_id += 1
        return self._next_id

    def _modern_meta(self, version: str) -> dict[str, Any]:
        """The per-request ``_meta`` fields a modern request carries."""
        return {
            META_PROTOCOL_VERSION: version,
            META_CLIENT_INFO: {"name": "toolscore", "version": _client_version()},
            META_CLIENT_CAPABILITIES: {},
        }

    def _params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Add the per-request ``_meta`` fields when speaking a modern version."""
        if self.era != "modern":
            return params
        meta = dict(params.get("_meta") or {})
        meta.update(self._modern_meta(self.protocol_version))
        return {**params, "_meta": meta}

    def _negotiate(self) -> None:
        """Detect the server's era and settle the protocol version.

        Raises:
            MCPError: If no mutually supported version exists.
        """
        if self.protocol_mode == "legacy":
            self._initialize(LEGACY_PROTOCOL_VERSION)
            return

        auto = self.protocol_mode == "auto"
        probe_id = self._new_id()
        try:
            response = self._roundtrip(
                "server/discover",
                {"_meta": self._modern_meta(MODERN_PROTOCOL_VERSION)},
                request_id=probe_id,
                timeout=self.probe_timeout if auto else self.timeout,
            )
        except MCPTimeoutError:
            if not auto:
                raise MCPError(
                    f"The server did not answer server/discover within {self.timeout}s; "
                    f"it may not speak MCP {MODERN_PROTOCOL_VERSION}. Retry with "
                    "protocol 'auto' or 'legacy'."
                ) from None
            self._fall_back(probe_id, "it did not answer server/discover in time")
            return
        except MCPHTTPStatusError as exc:
            if not auto or exc.status in (401, 403):
                raise
            self._fall_back(probe_id, f"server/discover returned HTTP {exc.status}")
            return

        if "result" in response:
            result = response["result"]
            self._adopt_discover(result if isinstance(result, dict) else {}, auto)
            return

        code = _error_code(response)
        if code == UNSUPPORTED_PROTOCOL_VERSION_CODE:
            self._choose_from_supported(_supported_versions(response), auto)
            return
        if code in MODERN_ERROR_CODES:
            raise MCPError(
                f"The server rejected server/discover (code={code}): {_error_message(response)}"
            )
        if not auto:
            raise MCPError(
                f"The server does not support server/discover (code={code}: "
                f"{_error_message(response)}); it may only speak a handshake-based MCP "
                "revision. Retry with protocol 'auto' or 'legacy'."
            )
        self._fall_back(probe_id, f"server/discover returned error code {code}")

    def _adopt_discover(self, result: dict[str, Any], auto: bool) -> None:
        """Use a ``DiscoverResult``: pick a version and record the server's identity."""
        versions = result.get("supportedVersions")
        listed = [v for v in versions if isinstance(v, str)] if isinstance(versions, list) else []
        self.server_versions = listed
        if listed and MODERN_PROTOCOL_VERSION not in listed:
            self._choose_from_supported(listed, auto)
            return
        self.era = "modern"
        self.protocol_version = MODERN_PROTOCOL_VERSION
        meta = result.get("_meta")
        info = meta.get(META_SERVER_INFO) if isinstance(meta, dict) else None
        if not isinstance(info, dict):
            info = result.get("serverInfo")
        self.server_info = info if isinstance(info, dict) else {}
        capabilities = result.get("capabilities")
        self.server_capabilities = capabilities if isinstance(capabilities, dict) else {}
        instructions = result.get("instructions")
        self.server_instructions = instructions if isinstance(instructions, str) else None

    def _choose_from_supported(self, supported: list[str], auto: bool) -> None:
        """Pick a version from a modern server's ``supported`` list."""
        for version in MODERN_PROTOCOL_VERSIONS:
            if version in supported:
                # Only reachable if the server lists our version yet rejected it.
                raise MCPError(
                    f"The server lists protocol version {version} as supported but rejected it."
                )
        legacy = [v for v in LEGACY_PROTOCOL_VERSIONS if v in supported]
        if legacy and auto:
            self._initialize(legacy[0])
            return
        ours = ", ".join([*MODERN_PROTOCOL_VERSIONS, *LEGACY_PROTOCOL_VERSIONS])
        theirs = ", ".join(supported) or "none listed"
        raise MCPError(
            f"No protocol version in common: the server supports {theirs}; "
            f"toolscore supports {ours}."
        )

    def _fall_back(self, probe_id: int, reason: str) -> None:
        """Fall back to the ``initialize`` handshake after a failed probe.

        If ``initialize`` fails but a late answer to the probe arrived meanwhile
        (a slow modern server), the client continues in the modern era.
        """
        self._reset_session()
        try:
            self._initialize(LEGACY_PROTOCOL_VERSION)
        except MCPError as exc:
            for message in self.server_messages:
                if message.get("id") == probe_id and isinstance(message.get("result"), dict):
                    self.era = None
                    self._adopt_discover(message["result"], auto=False)
                    return
            raise MCPError(
                f"Could not agree on an MCP protocol version: {reason}, so toolscore "
                f"fell back to the {LEGACY_PROTOCOL_VERSION} initialize handshake, which "
                f"also failed: {exc}"
            ) from exc

    def _initialize(self, version: str) -> None:
        """Run the legacy ``initialize`` handshake.

        Records :attr:`protocol_version`, :attr:`server_info`,
        :attr:`server_instructions` and :attr:`server_capabilities`.

        Raises:
            MCPError: If the server returns an error to ``initialize``.
        """
        result = self._request(
            "initialize",
            {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "toolscore", "version": _client_version()},
            },
        )
        self.era = "legacy"
        negotiated = result.get("protocolVersion")
        self.protocol_version = (
            negotiated if isinstance(negotiated, str) and negotiated else version
        )

        instructions = result.get("instructions")
        self.server_instructions = instructions if isinstance(instructions, str) else None
        capabilities = result.get("capabilities")
        self.server_capabilities = capabilities if isinstance(capabilities, dict) else {}
        server_info = result.get("serverInfo", {})
        self.server_info = server_info if isinstance(server_info, dict) else {}

        self._notify("notifications/initialized", {})

    # -- protocol operations -----------------------------------------------

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a request and return its ``result``, raising on JSON-RPC errors.

        Args:
            method: The JSON-RPC method name.
            params: The request parameters (``_meta`` is added in the modern era).

        Returns:
            The ``result`` object from the response.

        Raises:
            MCPError: If the server returns a JSON-RPC error, or a result type
                this client cannot handle.
            MCPTimeoutError: If no response arrives in time.
        """
        response = self._roundtrip(method, self._params(params))
        if "error" in response:
            code = _error_code(response)
            raise MCPError(f"MCP error for {method!r} (code={code}): {_error_message(response)}")
        result = response.get("result", {})
        result = result if isinstance(result, dict) else {}
        result_type = result.get("resultType", "complete")
        if result_type != "complete":
            raise MCPError(
                f"MCP server answered {method!r} with resultType {result_type!r}; toolscore "
                "handles only complete results."
            )
        return result

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
                if isinstance(tool, dict):
                    tools.append(_tool_def(tool))

            next_cursor = result.get("nextCursor")
            if not next_cursor:
                self._tool_schemas = {t.name: t.input_schema for t in tools}
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
            The :class:`MCPToolResult`. ``is_error`` is ``True`` when the server
            reports ``isError``, when the call yields a JSON-RPC error, and when
            the server asks for client input (``resultType: input_required``).

        Raises:
            MCPTimeoutError: If the server does not respond in time.
            MCPError: On a transport failure (e.g. the process dies).
        """
        started = time.perf_counter()
        response = self._roundtrip(
            "tools/call", self._params({"name": name, "arguments": arguments})
        )
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
        result_type = result.get("resultType", "complete")
        if result_type != "complete":
            return MCPToolResult(
                content=[
                    {
                        "type": "text",
                        "text": (
                            f"the server answered with resultType {result_type!r} (it asks "
                            "the client for input, which toolscore does not provide)"
                        ),
                    }
                ],
                is_error=True,
                raw=response,
                duration=duration,
            )
        return MCPToolResult(
            content=result.get("content", []),
            is_error=bool(result.get("isError", False)),
            raw=response,
            duration=duration,
        )


def _tool_def(tool: dict[str, Any]) -> MCPToolDef:
    """Build an :class:`MCPToolDef` from one ``tools/list`` entry."""
    schema = tool.get("inputSchema", {})
    annotations = tool.get("annotations")
    output_schema = tool.get("outputSchema")
    title = tool.get("title")
    return MCPToolDef(
        name=str(tool.get("name", "")),
        description=str(tool.get("description", "") or ""),
        input_schema=schema if isinstance(schema, dict) else {},
        annotations=annotations if isinstance(annotations, dict) else {},
        output_schema=output_schema if isinstance(output_schema, dict) else None,
        title=title if isinstance(title, str) else None,
    )


class MCPStdioClient(MCPClient):
    """Synchronous MCP client communicating with a server over stdio.

    The client spawns the server as a subprocess and agrees on a protocol
    version (see :class:`MCPClient`). A daemon thread reads stdout lines into a
    queue and another drains stderr, so neither stream can deadlock the
    protocol. Standard library only.
    """

    def __init__(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        timeout: float = 30.0,
        protocol: ProtocolMode = "auto",
        probe_timeout: float | None = None,
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
            protocol: Era selection, see :class:`MCPClient`.
            probe_timeout: ``server/discover`` probe timeout, see :class:`MCPClient`.
        """
        super().__init__(timeout=timeout, protocol=protocol, probe_timeout=probe_timeout)
        self._command = list(command)
        self._extra_env = dict(env) if env else {}
        self._cwd = str(cwd) if cwd is not None else None

        self._process: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        # Bounded buffer: verbose servers can emit unlimited stderr, so cap the
        # retained lines to the most recent 500 (only the tail is ever surfaced).
        self._stderr_lines: collections.deque[str] = collections.deque(maxlen=500)
        self._stderr_lock = threading.Lock()

    def __enter__(self) -> MCPStdioClient:
        """Start the server and agree on a protocol version.

        Returns:
            This client instance.
        """
        self.start()
        return self

    # -- transport -----------------------------------------------------------

    def _open(self) -> None:
        """Spawn the server process and its reader threads.

        Raises:
            MCPError: If the process cannot be spawned.
        """
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

        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()

    def _close_transport(self) -> None:
        """Shut down the server process gracefully.

        Closes stdin, waits briefly for the process to exit, then terminates and
        finally kills it if necessary.
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

    def _roundtrip(
        self,
        method: str,
        params: dict[str, Any],
        request_id: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a request and wait for the response with the matching id.

        Server-initiated notifications and requests received while waiting, and
        late responses to earlier requests, are stored in
        :attr:`server_messages` and ignored.

        Raises:
            MCPError: If the client is not started or the process died.
            MCPTimeoutError: If no matching response arrives within the timeout.
        """
        if request_id is None:
            request_id = self._new_id()
        wait = self.timeout if timeout is None else timeout
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})

        deadline = time.monotonic() + wait
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPTimeoutError(
                    f"Timed out after {wait}s waiting for response to {method!r}."
                )
            try:
                message = self._stdout_queue.get(timeout=remaining)
            except queue.Empty:
                raise MCPTimeoutError(
                    f"Timed out after {wait}s waiting for response to {method!r}."
                ) from None

            if message is None:
                # Reader thread signalled EOF / process exit.
                raise MCPError(
                    f"MCP server exited before responding to {method!r}. {self._diagnostics()}"
                )

            if message.get("id") == request_id and ("result" in message or "error" in message):
                return message

            # Notification, server-initiated message or a late response: stash & ignore.
            self.server_messages.append(message)

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (a request without an id)."""
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


# -- Streamable HTTP ---------------------------------------------------------

_HEADER_SAFE = re.compile(r"[\x21-\x7e]([\x20-\x7e]*[\x21-\x7e])?")
_HEADER_TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")


def safe_url(url: str) -> str:
    """``url`` without credentials, query or fragment, for messages and reprs.

    A URL from a config file may carry a token (``https://user:pass@host`` or
    ``?token=...``); only ``scheme://host[:port]/path`` is ever shown.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return "<invalid URL>"
    return f"{parts.scheme}://{host}{port}{parts.path}"


def encode_header_value(value: str) -> str:
    """Encode a value for an ``Mcp-Name`` / ``Mcp-Param-*`` header.

    Plain visible ASCII is sent as-is; anything else (non-ASCII, control
    characters, leading/trailing whitespace, or text that looks like the
    sentinel) is sent as ``=?base64?<UTF-8 base64>?=``, as the 2026-07-28
    Streamable HTTP binding requires.

    Args:
        value: The header value to encode.

    Returns:
        The header-safe value.
    """
    looks_encoded = value.startswith("=?base64?") and value.endswith("?=")
    if _HEADER_SAFE.fullmatch(value) and not looks_encoded:
        return value
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"=?base64?{encoded}?="


def _mirrored_headers(schema: dict[str, Any], arguments: dict[str, Any]) -> dict[str, str]:
    """``Mcp-Param-*`` headers for parameters marked ``x-mcp-header`` in a schema.

    Only properties reachable through a chain of ``properties`` keys count.
    Values that are absent, ``None`` or not a string/integer/boolean are skipped.
    """
    headers: dict[str, str] = {}

    def walk(node: Any, values: Any) -> None:
        if not isinstance(node, dict) or not isinstance(values, dict):
            return
        properties = node.get("properties")
        if not isinstance(properties, dict):
            return
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict) or prop_name not in values:
                continue
            value = values[prop_name]
            header = prop_schema.get("x-mcp-header")
            if isinstance(header, str) and _HEADER_TOKEN.fullmatch(header):
                if isinstance(value, bool):
                    headers[f"Mcp-Param-{header}"] = "true" if value else "false"
                elif isinstance(value, int):
                    headers[f"Mcp-Param-{header}"] = str(value)
                elif isinstance(value, str):
                    headers[f"Mcp-Param-{header}"] = encode_header_value(value)
            walk(prop_schema, value)

    walk(schema, arguments)
    return headers


def _iter_sse_data(lines: Iterator[str]) -> Iterator[str]:
    """Yield the ``data`` payload of each server-sent event."""
    data: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r")
        if not line:
            if data:
                yield "\n".join(data)
                data = []
            continue
        if line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        if name == "data":
            data.append(value[1:] if value.startswith(" ") else value)
    if data:
        yield "\n".join(data)


class MCPHttpClient(MCPClient):
    """Synchronous MCP client for a remote server over Streamable HTTP.

    Supports both eras: the 2026-07-28 stateless binding (per-request
    ``MCP-Protocol-Version``, ``Mcp-Method`` and ``Mcp-Name`` headers, plus
    ``Mcp-Param-*`` headers for parameters a tool marks with ``x-mcp-header``)
    and the earlier session-based binding (``initialize``, ``Mcp-Session-Id``).
    Responses may be plain JSON or a server-sent-event stream.

    Requires ``httpx``: ``pip install "tool-scorer[http]"``.

    Header values (for example an ``Authorization`` token) are sent with every
    request but never included in error messages or reprs.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
        protocol: ProtocolMode = "auto",
        probe_timeout: float | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            url: The server's MCP endpoint, e.g. ``https://example.com/mcp``.
            headers: Extra headers sent with every request (e.g. authorization).
            timeout: Default per-request timeout in seconds.
            protocol: Era selection, see :class:`MCPClient`.
            probe_timeout: ``server/discover`` probe timeout. Defaults to
                ``timeout``: over HTTP a legacy server answers the probe with an
                error status, so a slow answer (a cold start) is waited for
                rather than taken for a legacy server.
        """
        super().__init__(
            timeout=timeout,
            protocol=protocol,
            probe_timeout=timeout if probe_timeout is None else probe_timeout,
        )
        if not url.startswith(("http://", "https://")):
            raise ValueError("MCP server URL must start with http:// or https://.")
        self.url = url
        #: The URL as shown in messages: no credentials, query or fragment.
        self.display_url = safe_url(url)
        self._headers = dict(headers) if headers else {}
        self._http: Any = None
        self._session_id: str | None = None

    def __repr__(self) -> str:
        """Show the URL but never header values."""
        return f"MCPHttpClient(url={self.display_url!r}, headers={sorted(self._headers)!r})"

    def _scrub(self, text: str) -> str:
        """Remove the full URL (which may hold credentials) from ``text``."""
        return text.replace(self.url, self.display_url)

    def __enter__(self) -> MCPHttpClient:
        """Connect and agree on a protocol version.

        Returns:
            This client instance.
        """
        self.start()
        return self

    # -- transport -----------------------------------------------------------

    def _open(self) -> None:
        """Create the HTTP client.

        Raises:
            MCPError: If ``httpx`` is not installed.
        """
        try:
            import httpx
        except ImportError as exc:
            raise MCPError(
                'Testing MCP servers over HTTP needs httpx: pip install "tool-scorer[http]"'
            ) from exc
        self._http = httpx.Client(follow_redirects=True, timeout=self.timeout)

    def _close_transport(self) -> None:
        """End a legacy session (best effort) and close the HTTP client."""
        http = self._http
        if http is None:
            return
        if self._session_id is not None:
            with contextlib.suppress(Exception):
                http.delete(self.url, headers=self._base_headers(), timeout=2.0)
        with contextlib.suppress(Exception):
            http.close()
        self._http = None
        self._session_id = None

    def _reset_session(self) -> None:
        """Forget any session id before a fresh ``initialize``."""
        self._session_id = None

    def _base_headers(self) -> dict[str, str]:
        """Headers sent with every request: user headers plus session/version."""
        headers = dict(self._headers)
        if self._session_id is not None:
            headers["Mcp-Session-Id"] = self._session_id
        if self.era == "legacy":
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    def _request_headers(self, method: str, params: dict[str, Any]) -> dict[str, str]:
        """All headers for one POST, including the modern mirrored headers."""
        headers = self._base_headers()
        headers["Accept"] = "application/json, text/event-stream"
        headers["Content-Type"] = "application/json"
        meta = params.get("_meta")
        version = meta.get(META_PROTOCOL_VERSION) if isinstance(meta, dict) else None
        if isinstance(version, str):
            headers["MCP-Protocol-Version"] = version
            headers["Mcp-Method"] = method
            name = params.get("uri") if method == "resources/read" else params.get("name")
            if method in ("tools/call", "resources/read", "prompts/get") and isinstance(name, str):
                headers["Mcp-Name"] = encode_header_value(name)
            if method == "tools/call" and isinstance(name, str):
                arguments = params.get("arguments")
                schema = self._tool_schemas.get(name)
                if isinstance(arguments, dict) and schema:
                    headers.update(_mirrored_headers(schema, arguments))
        return headers

    def _post(self, body: dict[str, Any], method: str, timeout: float) -> Any:
        """POST one message, converting transport failures to MCP errors."""
        import httpx

        if self._http is None:
            raise MCPError("MCP client is not started.")
        params = body.get("params")
        headers = self._request_headers(method, params if isinstance(params, dict) else {})
        request = self._http.build_request(
            "POST", self.url, json=body, headers=headers, timeout=timeout
        )
        try:
            return self._http.send(request, stream=True)
        except httpx.TimeoutException:
            raise MCPTimeoutError(
                f"Timed out after {timeout}s waiting for response to {method!r}."
            ) from None
        except httpx.HTTPError as exc:
            raise MCPError(
                f"HTTP request to {self.display_url} failed: {type(exc).__name__}: "
                f"{self._scrub(str(exc))}"
            ) from exc

    def _roundtrip(
        self,
        method: str,
        params: dict[str, Any],
        request_id: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """POST a request and return the JSON-RPC response with its id.

        Raises:
            MCPHTTPStatusError: On an HTTP error status without a JSON-RPC body.
            MCPTimeoutError: If the server does not answer in time.
            MCPError: On any other transport failure.
        """
        import httpx

        if request_id is None:
            request_id = self._new_id()
        wait = self.timeout if timeout is None else timeout
        body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        response = self._post(body, method, wait)
        try:
            session = response.headers.get("mcp-session-id")
            if method == "initialize" and session:
                self._session_id = session
            content_type = response.headers.get("content-type", "").lower()
            if response.status_code < 400 and "text/event-stream" in content_type:
                return self._read_event_stream(response, request_id, method, wait)
            text = response.read().decode("utf-8", errors="replace")
        except httpx.TimeoutException:
            raise MCPTimeoutError(
                f"Timed out after {wait}s waiting for response to {method!r}."
            ) from None
        except httpx.HTTPError as exc:
            raise MCPError(
                f"HTTP request to {self.display_url} failed: {type(exc).__name__}: "
                f"{self._scrub(str(exc))}"
            ) from exc
        finally:
            response.close()

        message = _json_object(text)
        if message is not None and ("result" in message or "error" in message):
            return message
        status = response.status_code
        if status in (401, 403):
            raise MCPHTTPStatusError(
                f"The MCP server at {self.display_url} answered HTTP {status} to {method!r}: it needs "
                "authorization. Pass a header (for example --auth-env TOKEN_VAR) or add "
                "'headers' to the server entry in the config file.",
                status,
            )
        excerpt = " ".join(text.split())[:_HTTP_BODY_EXCERPT]
        raise MCPHTTPStatusError(
            f"The MCP server at {self.display_url} answered HTTP {status} to {method!r}"
            + (f": {excerpt}" if excerpt else " with no JSON-RPC response."),
            status,
        )

    def _read_event_stream(
        self, response: Any, request_id: int, method: str, wait: float
    ) -> dict[str, Any]:
        """Read SSE events until the response with ``request_id`` arrives."""
        deadline = time.monotonic() + wait
        for data in _iter_sse_data(response.iter_lines()):
            message = _json_object(data)
            if message is not None:
                if message.get("id") == request_id and ("result" in message or "error" in message):
                    return message
                self.server_messages.append(message)
            if time.monotonic() > deadline:
                break
        if time.monotonic() > deadline:
            raise MCPTimeoutError(f"Timed out after {wait}s waiting for response to {method!r}.")
        raise MCPError(
            f"The MCP server at {self.display_url} closed the event stream for {method!r} "
            "without sending a response."
        )

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        """POST a notification; the server answers ``202 Accepted``."""
        response = self._post({"jsonrpc": "2.0", "method": method, "params": params}, method, 10.0)
        with contextlib.suppress(Exception):
            response.read()
        response.close()


def _json_object(text: str) -> dict[str, Any] | None:
    """Parse ``text`` as a JSON object, or return ``None``."""
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None
