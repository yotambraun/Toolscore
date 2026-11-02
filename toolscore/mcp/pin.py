"""Pin an MCP server's tools and catch drift: a defense against "rug pulls".

An MCP server can change what it tells the model at any time: a tool's
description gains a hidden instruction, a harmless tool starts deleting, a new
``run_command`` tool appears. Clients approve a server once and rarely look
again. ``toolscore mcp pin`` writes ``toolscore.lock.json`` with a SHA-256 of
every tool's name, description, input and output schema and annotations, the
server's identity, protocol and instructions, and a **capability manifest**;
``toolscore mcp verify-pin`` (and ``mcp test --pin`` / ``mcp lint --pin``) fail
when the live server drifts from it.

Capabilities (per tool): ``read``, ``write``, ``delete``, ``network``,
``exec`` or ``unknown``. They are derived transparently, and every capability
lists its sources:

1. **Annotations first.** ``readOnlyHint: true`` gives ``read`` (and rules out
   ``write``); ``readOnlyHint: false`` gives ``write``; ``destructiveHint: true``
   on a tool that is not read-only gives ``delete``; ``openWorldHint: true``
   gives ``network``.
2. **Then name and description rules** add what the annotations do not rule
   out: delete verbs (``delete``, ``remove``, ``drop``...) give ``delete``;
   write verbs (``create``, ``update``, ``send``...) ``write``; read verbs
   (``get``, ``list``, ``search``...) ``read``; execution words (``exec``,
   ``shell``, ``eval``, ``run_command``, "executes shell commands") ``exec``;
   network words (``fetch``, ``http``, ``url``, ``browse``, "HTTP request")
   ``network``. A description that starts with a delete verb ("Deletes...")
   gives ``delete`` whatever the name says. A rule never removes a capability,
   and a read-only hint never hides ``delete`` or ``exec`` that a name or
   description shows.
3. **Overrides** (``--capabilities caps.json``: ``{"tool": ["read"]}``) replace
   the derived set for a tool and are stored in the lock.

A tool with no capability found is ``unknown``.

Drift rules (``severity`` in brackets):

* ``pin-tool-added`` [error]: a tool the lock does not have.
* ``pin-tool-removed`` [error]: a locked tool is gone.
* ``pin-tool-changed`` [error]: a tool's description, title, input or output
  schema or annotations changed (with a text diff).
* ``pin-capability-added`` [error]: a tool gained ``delete`` or ``exec``
  (:data:`RISKY_CAPABILITIES`), or a new tool has one.
* ``pin-instructions-changed`` [error]: the server instructions changed.
* ``pin-lock-modified`` [error]: the lock file does not match its own hash.
* ``pin-server-changed`` [info]: the server's name or version changed.
* ``pin-protocol-changed`` [info]: the protocol version changed.

``fail_on`` decides what fails: ``"drift"`` (default, any error),
``"capability"`` (only new risky capabilities and a modified lock) or
``"never"`` (report only).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from toolscore.mcp.lint_rules import _DESTRUCTIVE_VERBS, _READ_VERBS, _WRITE_VERBS, _name_words
from toolscore.mcp.snapshot import ServerSnapshot, text_diff, tool_to_json
from toolscore.receipts import json_sha256

if TYPE_CHECKING:
    from toolscore.mcp.client import MCPToolDef

#: Layout version of a lock file.
LOCK_VERSION = "1"
#: The ``kind`` of a lock file.
LOCK_KIND = "toolscore.mcp-lock"
#: Default lock file name.
DEFAULT_LOCK_FILE = "toolscore.lock.json"

#: Every capability, in display order.
CAPABILITIES: tuple[str, ...] = ("read", "write", "delete", "network", "exec", "unknown")
#: Capabilities whose appearance fails a pin check.
RISKY_CAPABILITIES = frozenset({"delete", "exec"})

#: Drift rule IDs with a one-line meaning.
PIN_RULES: dict[str, str] = {
    "pin-tool-added": "a tool the lock does not have",
    "pin-tool-removed": "a locked tool is gone",
    "pin-tool-changed": "a tool's description, schema or annotations changed",
    "pin-capability-added": "a tool gained a delete or exec capability",
    "pin-instructions-changed": "the server instructions changed",
    "pin-lock-modified": "the lock file does not match its own hash",
    "pin-server-changed": "the server's name or version changed",
    "pin-protocol-changed": "the protocol version changed",
}

#: The ``fail_on`` modes.
FAIL_MODES: tuple[str, ...] = ("drift", "capability", "never")

#: Fields of a tool definition that are hashed, in order.
HASHED_FIELDS: tuple[str, ...] = (
    "name",
    "title",
    "description",
    "inputSchema",
    "outputSchema",
    "annotations",
)

_EXEC_WORDS = frozenset(
    {
        "exec", "execute", "shell", "bash", "sh", "zsh", "powershell", "pwsh", "cmd",
        "eval", "evaluate", "terminal", "spawn", "subprocess", "interpreter", "repl",
    }
)  # fmt: skip
#: ``run`` is execution only next to one of these (``run_command``, ``run_python``).
_RUN_OBJECTS = frozenset(
    {"code", "command", "commands", "script", "scripts", "shell", "python", "js", "javascript",
     "program", "process", "cmd"}
)  # fmt: skip
_NETWORK_WORDS = frozenset(
    {
        "fetch", "http", "https", "url", "urls", "download", "upload", "browse", "browser",
        "navigate", "web", "webhook", "email", "mail", "curl", "scrape", "crawl",
    }
)  # fmt: skip
_EXEC_TEXT = re.compile(
    r"\b(?:execut(?:e|es|ing)|runs?|evaluat(?:e|es|ing))\s+(?:arbitrary\s+|any\s+|a\s+|the\s+)?"
    r"(?:shell\s+|system\s+|terminal\s+|python\s+|javascript\s+|js\s+)?"
    r"(?:commands?|code|scripts?|programs?|expressions?)\b",
    re.IGNORECASE,
)
_NETWORK_TEXT = re.compile(
    r"\b(?:https?\s+requests?|https?://|web\s+pages?|webhooks?|the\s+internet|(?:a|any)\s+URL"
    r"|sends?\s+(?:an?\s+)?e-?mails?)\b",
    re.IGNORECASE,
)


# -- capabilities ----------------------------------------------------------------


def infer_capabilities(tool: MCPToolDef) -> dict[str, list[str]]:
    """Derive a tool's capabilities and why (see the module docstring).

    Args:
        tool: The tool.

    Returns:
        Capability -> its sources, in :data:`CAPABILITIES` order; ``{"unknown":
        [...]}`` when nothing was found.
    """
    found: dict[str, list[str]] = {}

    def add(capability: str, source: str) -> None:
        found.setdefault(capability, [])
        if source not in found[capability]:
            found[capability].append(source)

    hints = tool.annotations if isinstance(tool.annotations, dict) else {}
    read_only = hints.get("readOnlyHint")
    if read_only is True:
        add("read", "annotation readOnlyHint: true")
    elif read_only is False:
        add("write", "annotation readOnlyHint: false")
    if hints.get("destructiveHint") is True and read_only is not True:
        add("delete", "annotation destructiveHint: true")
    if hints.get("openWorldHint") is True:
        add("network", "annotation openWorldHint: true")

    words = _name_words(tool.name)
    starts_with_read = bool(words) and words[0] in _READ_VERBS
    for word in words:
        if word in _DESTRUCTIVE_VERBS and not starts_with_read:
            add("delete", f"name word {word!r}")
        elif word in _WRITE_VERBS and not starts_with_read and read_only is not True:
            add("write", f"name word {word!r}")
        if word in _EXEC_WORDS:
            add("exec", f"name word {word!r}")
        if word in _NETWORK_WORDS:
            add("network", f"name word {word!r}")
    if "run" in words and any(w in _RUN_OBJECTS for w in words):
        add("exec", "name 'run' + " + next(repr(w) for w in words if w in _RUN_OBJECTS))
    if starts_with_read:
        add("read", f"name word {words[0]!r}")

    description = tool.description or ""
    match = _EXEC_TEXT.search(description)
    if match:
        add("exec", f"description {match.group(0)!r}")
    match = _NETWORK_TEXT.search(description)
    if match:
        add("network", f"description {match.group(0)!r}")
    first = re.match(r"\s*([A-Za-z]+)", description)
    if first:
        verb = first.group(1).lower()
        stem = verb[:-1] if verb.endswith("s") else verb
        if stem in _DESTRUCTIVE_VERBS:
            # Risky capabilities are never hidden by a harmless name.
            add("delete", f"description verb {verb!r}")
        elif not found.keys() & {"read", "write", "delete"}:
            if stem in _WRITE_VERBS:
                add("write", f"description verb {verb!r}")
            elif stem in _READ_VERBS:
                add("read", f"description verb {verb!r}")

    if not found:
        return {"unknown": ["no annotation, name or description rule matched"]}
    return {cap: found[cap] for cap in CAPABILITIES if cap in found}


def load_capability_overrides(path: str | Path) -> dict[str, list[str]]:
    """Read ``{"tool": ["read", ...]}`` capability overrides (JSON).

    Raises:
        ValueError: On a value that is not a list of known capabilities.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_overrides(data)


def validate_overrides(data: Any) -> dict[str, list[str]]:
    """Check a capability override mapping (see :func:`load_capability_overrides`)."""
    if not isinstance(data, dict):
        raise ValueError('capability overrides must be an object: {"tool": ["read"]}')
    overrides: dict[str, list[str]] = {}
    for tool, caps in data.items():
        if not isinstance(caps, list) or not caps or any(c not in CAPABILITIES for c in caps):
            raise ValueError(
                f"capabilities for {tool!r} must be a non-empty list of {list(CAPABILITIES)}"
            )
        overrides[str(tool)] = [c for c in CAPABILITIES if c in caps]
    return overrides


def tool_capabilities(
    tool: MCPToolDef, overrides: dict[str, list[str]] | None = None
) -> dict[str, list[str]]:
    """A tool's capabilities with sources, after any override."""
    if overrides and tool.name in overrides:
        return {cap: ["override"] for cap in overrides[tool.name]}
    return infer_capabilities(tool)


# -- the lock ----------------------------------------------------------------------


def tool_definition(tool: MCPToolDef) -> dict[str, Any]:
    """The hashed part of a tool: :data:`HASHED_FIELDS` with ``None`` for absent ones."""
    data = tool_to_json(tool)
    return {key: data.get(key) for key in HASHED_FIELDS}


def tool_sha256(tool: MCPToolDef) -> str:
    """SHA-256 of a tool's name, title, description, schemas and annotations (canonical JSON)."""
    return json_sha256(tool_definition(tool))


def build_lock(
    snapshot: ServerSnapshot, overrides: dict[str, list[str]] | None = None
) -> dict[str, Any]:
    """Build the lock for a server snapshot.

    Args:
        snapshot: The server's tools and identity.
        overrides: Capability overrides by tool name.

    Returns:
        The lock dict (see the module docstring), with ``lock_sha256`` last.
    """
    from toolscore import __version__

    tools: dict[str, Any] = {}
    for tool in sorted(snapshot.tools, key=lambda t: t.name):
        definition = tool_definition(tool)
        capabilities = tool_capabilities(tool, overrides)
        tools[tool.name] = {
            "sha256": json_sha256(definition),
            "fields": {key: json_sha256(definition[key]) for key in HASHED_FIELDS},
            "capabilities": list(capabilities),
            "capability_sources": capabilities,
            "definition": definition,
        }
    lock: dict[str, Any] = {
        "lock_version": LOCK_VERSION,
        "kind": LOCK_KIND,
        "generated_by": f"toolscore {__version__}",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "server": {
            "name": snapshot.server_info.get("name", ""),
            "version": snapshot.server_info.get("version", ""),
        },
        "protocol": {"version": snapshot.protocol_version, "era": snapshot.era},
        "instructions_sha256": (
            json_sha256(snapshot.instructions) if snapshot.instructions is not None else None
        ),
        "tools": tools,
        "overrides": dict(overrides or {}),
    }
    lock["lock_sha256"] = json_sha256(_lock_body(lock))
    return lock


def _lock_body(lock: dict[str, Any]) -> dict[str, Any]:
    """The hashed part of a lock: everything but ``lock_sha256`` and ``created_at``."""
    return {k: v for k, v in lock.items() if k not in ("lock_sha256", "created_at")}


def write_lock(path: str | Path, lock: dict[str, Any]) -> Path:
    """Write a lock file (indented, sorted tool names) and return its path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def is_lock(data: Any) -> bool:
    """Whether parsed JSON is a Toolscore MCP lock file."""
    return isinstance(data, dict) and data.get("kind") == LOCK_KIND


def load_lock(path: str | Path) -> dict[str, Any]:
    """Read a lock file.

    Raises:
        ValueError: If the file is not a Toolscore lock.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not is_lock(data):
        raise ValueError(f"{path} is not a Toolscore lock file (kind {LOCK_KIND!r})")
    return dict(data)


# -- verification ----------------------------------------------------------------------


@dataclass
class PinFinding:
    """One difference between a server and its lock.

    Attributes:
        rule: The rule ID (see :data:`PIN_RULES`).
        severity: ``"error"`` or ``"info"``.
        tool: The tool concerned, or ``""`` for server-level findings.
        message: What changed.
        diff: A unified text diff of what changed, when there is one.
        fields: The changed fields of a changed tool.
    """

    rule: str
    severity: str
    tool: str
    message: str
    diff: str = ""
    fields: list[str] = field(default_factory=list)


@dataclass
class PinReport:
    """The result of checking a server against its lock.

    Attributes:
        findings: Every difference, errors first.
        fail_on: The ``fail_on`` mode used (see :data:`FAIL_MODES`).
        server: The live server's label.
    """

    findings: list[PinFinding]
    fail_on: str = "drift"
    server: str = ""

    @property
    def failing(self) -> list[PinFinding]:
        """The findings that fail the check under :attr:`fail_on`."""
        if self.fail_on == "never":
            return []
        errors = [f for f in self.findings if f.severity == "error"]
        if self.fail_on == "capability":
            return [f for f in errors if f.rule in ("pin-capability-added", "pin-lock-modified")]
        return errors

    @property
    def ok(self) -> bool:
        """Whether the check passes under :attr:`fail_on`."""
        return not self.failing

    @property
    def drifted(self) -> bool:
        """Whether anything differs from the lock (errors or info)."""
        return bool(self.findings)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe report."""
        return {
            "ok": self.ok,
            "fail_on": self.fail_on,
            "server": self.server,
            "drifted": self.drifted,
            "findings": [
                {
                    "rule": f.rule,
                    "severity": f.severity,
                    "tool": f.tool,
                    "message": f.message,
                    "fields": f.fields,
                    "diff": f.diff,
                    "fails": f in self.failing,
                }
                for f in self.findings
            ],
        }


def verify_pin(
    lock: dict[str, Any],
    snapshot: ServerSnapshot,
    fail_on: str = "drift",
) -> PinReport:
    """Compare a server with its lock.

    Args:
        lock: The lock (see :func:`build_lock`).
        snapshot: The live server (or a saved snapshot of it).
        fail_on: ``"drift"``, ``"capability"`` or ``"never"``.

    Returns:
        The :class:`PinReport`.

    Raises:
        ValueError: On an unknown ``fail_on``.
    """
    if fail_on not in FAIL_MODES:
        raise ValueError(f"fail_on must be one of {FAIL_MODES}, got {fail_on!r}")
    findings: list[PinFinding] = []
    if lock.get("lock_sha256") != json_sha256(_lock_body(lock)):
        findings.append(
            PinFinding(
                "pin-lock-modified",
                "error",
                "",
                "the lock file was edited by hand: it does not match its own lock_sha256 "
                "(re-run toolscore mcp pin after review)",
            )
        )
    overrides = lock.get("overrides") or {}
    locked: dict[str, Any] = lock.get("tools") or {}
    live = snapshot.tool_map

    for name in sorted(live.keys() - locked.keys()):
        caps = tool_capabilities(live[name], overrides)
        risky = sorted(RISKY_CAPABILITIES & caps.keys())
        findings.append(
            PinFinding(
                "pin-tool-added",
                "error",
                name,
                f"new tool {name!r} ({', '.join(caps)}) is not in the lock",
                diff=text_diff("", _pretty(tool_definition(live[name])), "lock", "server"),
            )
        )
        if risky:
            findings.append(
                PinFinding(
                    "pin-capability-added",
                    "error",
                    name,
                    f"new tool {name!r} can {' and '.join(risky)} "
                    f"({'; '.join(s for c in risky for s in caps[c])})",
                )
            )
    for name in sorted(locked.keys() - live.keys()):
        findings.append(
            PinFinding("pin-tool-removed", "error", name, f"locked tool {name!r} is gone")
        )
    for name in sorted(live.keys() & locked.keys()):
        entry = locked[name]
        tool = live[name]
        definition = tool_definition(tool)
        if json_sha256(definition) != entry.get("sha256"):
            old = entry.get("definition") or {}
            fields = [
                key
                for key in HASHED_FIELDS
                if json_sha256(definition[key]) != (entry.get("fields") or {}).get(key)
            ]
            diffs = []
            for key in fields:
                before, after = old.get(key), definition[key]
                if isinstance(before, str) or isinstance(after, str):
                    diffs.append(text_diff(before or "", after or "", f"{key} (lock)", f"{key}"))
                else:
                    diffs.append(
                        text_diff(_pretty(before), _pretty(after), f"{key} (lock)", f"{key}")
                    )
            findings.append(
                PinFinding(
                    "pin-tool-changed",
                    "error",
                    name,
                    f"{name!r} changed: {', '.join(fields)}",
                    diff="\n".join(d for d in diffs if d),
                    fields=fields,
                )
            )
        caps = tool_capabilities(tool, overrides)
        gained = sorted((RISKY_CAPABILITIES & caps.keys()) - set(entry.get("capabilities") or []))
        if gained:
            findings.append(
                PinFinding(
                    "pin-capability-added",
                    "error",
                    name,
                    f"{name!r} can now {' and '.join(gained)} "
                    f"({'; '.join(s for c in gained for s in caps[c])})",
                )
            )

    instructions = json_sha256(snapshot.instructions) if snapshot.instructions is not None else None
    if instructions != lock.get("instructions_sha256"):
        findings.append(
            PinFinding(
                "pin-instructions-changed",
                "error",
                "",
                "the server instructions changed (they are sent to the model with every session)",
            )
        )
    locked_server = lock.get("server") or {}
    for key in ("name", "version"):
        before = str(locked_server.get(key) or "")
        after = str(snapshot.server_info.get(key) or "")
        if before != after:
            findings.append(
                PinFinding(
                    "pin-server-changed",
                    "info",
                    "",
                    f"server {key} {before or '(none)'} -> {after or '(none)'}",
                )
            )
    locked_protocol = (lock.get("protocol") or {}).get("version")
    if snapshot.protocol_version and locked_protocol != snapshot.protocol_version:
        findings.append(
            PinFinding(
                "pin-protocol-changed",
                "info",
                "",
                f"protocol {locked_protocol} -> {snapshot.protocol_version}",
            )
        )
    findings.sort(key=lambda f: (f.severity != "error", f.tool, f.rule))
    return PinReport(findings=findings, fail_on=fail_on, server=snapshot.label)


def _pretty(value: Any) -> str:
    """Indented, key-sorted JSON for text diffs (``""`` for ``None``)."""
    if value is None:
        return ""
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def capability_table(
    snapshot: ServerSnapshot, overrides: dict[str, list[str]] | None = None
) -> list[dict[str, Any]]:
    """Each tool's capabilities and their sources, for display."""
    return [
        {
            "tool": tool.name,
            "capabilities": list(caps),
            "sources": caps,
        }
        for tool in snapshot.tools
        for caps in [tool_capabilities(tool, overrides)]
    ]


def render_pin_report(report: PinReport, color: bool = True) -> str:
    """The report as console markup (``color``) or plain text."""
    lines: list[str] = []
    if not report.findings:
        lines.append(
            f"{'[green]OK[/green]' if color else 'OK'} {report.server}: no drift from the lock."
        )
        return "\n".join(lines)
    failing = report.failing
    for finding in report.findings:
        tag = finding.severity.upper()
        if color:
            style = "red" if finding in failing else ("yellow" if tag == "ERROR" else "dim")
            tag = f"[{style}]{tag:<5}[/{style}]"
        rule = f"[dim]({finding.rule})[/dim]" if color else f"({finding.rule})"
        lines.append(f"  {tag}  {_escape(finding.message, color)} {rule}")
        if finding.diff:
            for line in finding.diff.splitlines():
                lines.append(f"         {_escape(line, color)}")
    verdict = "PASS" if report.ok else "FAIL"
    if color:
        verdict = f"[green]{verdict}[/green]" if report.ok else f"[red]{verdict}[/red]"
    lines.append(
        f"Pin check: {verdict} ({len(failing)} failing of {len(report.findings)} finding(s), "
        f"--fail-on {report.fail_on})"
    )
    return "\n".join(lines)


def _escape(text: str, color: bool) -> str:
    if not color:
        return text
    from rich.markup import escape

    return escape(text)
