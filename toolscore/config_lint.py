"""Lint agent instruction files and MCP host configs against the tools that really exist.

Agents read instruction files (``CLAUDE.md``, ``AGENTS.md``, ``SKILL.md``,
Cursor rules, Copilot instructions) that name the tools to use. When a server
is renamed, a tool is removed, or an instruction tells the agent to delete
with a tool that declares itself read-only, nothing warns you: the agent just
calls a tool that is not there, or a client lets a "read-only" tool run
without asking. :func:`lint_config` finds these mismatches.

What it reads:

* instruction files: ``CLAUDE.md``, ``CLAUDE.local.md``, ``AGENTS.md``, any
  ``SKILL.md``, ``.cursor/rules/**/*.mdc|*.md``, ``.cursorrules``,
  ``.github/copilot-instructions.md``, ``.github/instructions/*.instructions.md``;
* MCP host configs: ``.mcp.json``, ``.cursor/mcp.json``, ``.vscode/mcp.json``,
  ``claude_desktop_config.json`` (and, only when asked, the user's
  ``~/.claude.json``);
* the tools each server exposes, from snapshot or lock files
  (``toolscore mcp list --json``, ``toolscore mcp pin``) or, only when asked,
  by starting the configured servers (``connect=True``).

Rules (all conservative: a finding needs an exact tool reference):

* ``config-server-invalid`` (error): a host-config entry Toolscore cannot use
  (no command or URL, the deprecated SSE transport, unreadable JSON).
* ``config-unknown-server`` (warning): an ``mcp__<server>__<tool>`` name whose
  server no host config defines.
* ``config-unknown-tool`` (error): an ``mcp__<server>__<tool>`` name whose
  server is known and does not expose the tool, or a quoted name written as a
  tool (```purge_all` tool``) that no known server exposes.
* ``config-annotation-contradiction`` (warning): "use X to delete/create/..."
  where X declares ``readOnlyHint: true``, or "use X to read/list/..." where X
  declares ``destructiveHint: true``.

Rules that need a tool inventory are reported as skipped when there is none,
never as passed. Claude Code's built-in tools (``Read``, ``Bash``, ...) and
plain prose are never flagged; ``mcp__plugin_*`` and ``mcp__claude_ai_*``
names come from plugins and connectors outside the repository and are not
checked against it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.mcp.client import MCPToolDef

#: The rule IDs :func:`lint_config` reports.
CONFIG_RULES = (
    "config-server-invalid",
    "config-unknown-server",
    "config-unknown-tool",
    "config-annotation-contradiction",
)
#: Rules that need to know which tools each server exposes.
INVENTORY_RULES = ("config-unknown-tool", "config-annotation-contradiction")

_INSTRUCTION_NAMES = frozenset(
    {"CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "SKILL.md", ".cursorrules"}
)
_HOST_CONFIG_NAMES = frozenset({".mcp.json", "claude_desktop_config.json"})
_SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".tox",
        "site-packages",
    }
)
_FOREIGN_SERVER_PREFIXES = ("plugin_", "claude_ai_")

_MCP_NAME = re.compile(r"\bmcp__(?P<server>[A-Za-z0-9_.-]+?)__(?P<tool>[A-Za-z0-9_.-]+)")
_QUOTED_TOOL = re.compile(r"[`'\"](?P<name>[a-z][a-z0-9]*(?:[_-][a-z0-9]+)+)[`'\"]\s+tool\b")
_USE_TOOL = re.compile(
    r"\b(?:use|call|run|invoke)\s+(?:the\s+)?[`'\"]?(?P<tool>(?:mcp__[A-Za-z0-9_.-]+|[A-Za-z][\w.-]*))"
    r"[`'\"]?(?:\s+tool)?\s+(?:to|for)\s+(?P<verb>[a-z]+)(?P<particle>\s+up)?",
    re.IGNORECASE,
)

_FIX_SERVER_INVALID = "Fix the entry: a stdio server needs 'command', a remote one 'url'."
_FIX_SSE = "Point the entry at the server's Streamable HTTP endpoint (type 'http')."
_FIX_UNKNOWN_SERVER = (
    "Add the server to the repository's MCP config (.mcp.json), or fix the name in the "
    "instruction file."
)
_FIX_UNKNOWN_TOOL = (
    "Point the instruction at a tool the server exposes (check `toolscore mcp list`), or remove it."
)
_FIX_READ_ONLY = (
    "Use a tool that can make the change, or, if this tool does change state, fix its "
    "annotations: readOnlyHint: true lets clients run it without asking."
)
_FIX_DESTRUCTIVE = (
    "Use a read-only tool for lookups; the server says this one can delete or overwrite data."
)


@dataclass
class ConfigIssue:
    """One finding of :func:`lint_config`.

    Attributes:
        rule: The rule ID (see :data:`CONFIG_RULES`).
        severity: ``"error"`` or ``"warning"``.
        path: The file it is in.
        line: The 1-based line, or ``None`` for a whole file.
        message: What is wrong.
        fix: How to fix it.
    """

    rule: str
    severity: str
    path: str
    line: int | None
    message: str
    fix: str

    def to_json(self) -> dict[str, Any]:
        """A JSON-safe dict of the issue."""
        return {
            "rule": self.rule,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "fix": self.fix,
        }


@dataclass
class ConfigLintReport:
    """What :func:`lint_config` read and found.

    Attributes:
        instruction_files: The instruction files read.
        host_configs: The MCP host config files read.
        servers: Configured server names, each with the config file defining it.
        inventory: For each server with a known tool list, its tools by name.
        skipped_rules: Rules that could not run, with the reason.
        issues: The findings, in file order.
    """

    instruction_files: list[str] = field(default_factory=list)
    host_configs: list[str] = field(default_factory=list)
    servers: dict[str, str] = field(default_factory=dict)
    inventory: dict[str, dict[str, MCPToolDef]] = field(default_factory=dict)
    skipped_rules: dict[str, str] = field(default_factory=dict)
    issues: list[ConfigIssue] = field(default_factory=list)

    @property
    def errors(self) -> int:
        """How many error-severity issues there are."""
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warnings(self) -> int:
        """How many warning-severity issues there are."""
        return sum(1 for i in self.issues if i.severity == "warning")

    def to_json(self) -> dict[str, Any]:
        """A JSON-safe dict of the report."""
        return {
            "instruction_files": self.instruction_files,
            "host_configs": self.host_configs,
            "servers": {
                name: {"config": config, "tools": sorted(self.inventory.get(name, {})) or None}
                for name, config in self.servers.items()
            },
            "skipped_rules": self.skipped_rules,
            "issues": [i.to_json() for i in self.issues],
            "summary": {"errors": self.errors, "warnings": self.warnings},
        }


def _is_instruction_file(path: Path) -> bool:
    parts = path.parts
    if path.name in _INSTRUCTION_NAMES:
        return True
    if path.name == "copilot-instructions.md" and parts[-2:-1] == (".github",):
        return True
    if path.name.endswith(".instructions.md") and ".github" in parts:
        return True
    return ".cursor" in parts and "rules" in parts and path.suffix in (".md", ".mdc")


def _is_host_config(path: Path) -> bool:
    if path.name in _HOST_CONFIG_NAMES:
        return True
    return path.name == "mcp.json" and path.parent.name in (".cursor", ".vscode")


def discover_files(paths: list[Path]) -> tuple[list[Path], list[Path]]:
    """Find instruction files and MCP host configs under ``paths``.

    Args:
        paths: Files or directories (directories are searched recursively,
            skipping ``.git``, ``node_modules``, virtual environments and build output).

    Returns:
        ``(instruction files, host config files)``, sorted.
    """
    instructions: set[Path] = set()
    configs: set[Path] = set()

    def consider(path: Path, explicit: bool) -> None:
        if _is_host_config(path):
            configs.add(path)
        elif _is_instruction_file(path) or (explicit and path.suffix in (".md", ".mdc")):
            instructions.add(path)

    for root in paths:
        if root.is_file():
            consider(root, explicit=True)
            continue
        if not root.is_dir():
            continue
        stack = [root]
        while stack:
            folder = stack.pop()
            try:
                entries = list(folder.iterdir())
            except OSError:
                continue
            for entry in entries:
                if entry.is_dir():
                    if entry.name not in _SKIP_DIRS:
                        stack.append(entry)
                elif entry.is_file():
                    consider(entry, explicit=False)
    return sorted(instructions), sorted(configs)


def _config_servers(path: Path) -> tuple[dict[str, Any], str | None]:
    """The server entries of a host config file, or an error message."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"cannot read {path.name}: {exc}"
    if not isinstance(data, dict):
        return {}, f"{path.name} is not a JSON object"
    servers: dict[str, Any] = {}
    for key in ("mcpServers", "servers"):
        if isinstance(data.get(key), dict):
            servers.update(data[key])
    projects = data.get("projects")
    if path.name == ".claude.json" and isinstance(projects, dict):
        for project in projects.values():
            if isinstance(project, dict) and isinstance(project.get("mcpServers"), dict):
                servers.update(project["mcpServers"])
    return servers, None


def _verb_kind(verb: str) -> str | None:
    from toolscore.mcp.lint_rules import _DESTRUCTIVE_VERBS, _READ_VERBS, _WRITE_VERBS

    word = verb.lower()
    if word in _DESTRUCTIVE_VERBS:
        return "delete"
    if word in _WRITE_VERBS:
        return "write"
    if word in _READ_VERBS or word in {"look", "lookup", "see", "explore", "investigate"}:
        return "read"
    return None


def lint_config(
    paths: list[Path] | None = None,
    snapshots: list[tuple[str | None, Path]] | None = None,
    connect: bool = False,
    user_config: Path | None = None,
    timeout: float = 30.0,
) -> ConfigLintReport:
    """Lint instruction files and MCP host configs.

    Args:
        paths: Files or directories to read (default: the current directory).
        snapshots: Tool inventories as ``(server name or None, file)``: a
            ``toolscore mcp list --json`` snapshot or a ``toolscore mcp pin``
            lock file. Without a name, the snapshot's own server name is used.
        connect: Start every configured server to list its tools. This runs
            the commands in the host configs; it is never done by default.
        user_config: Also read this user-scope config (``~/.claude.json``).
        timeout: Seconds to wait for each server with ``connect``.

    Returns:
        The report.
    """
    from toolscore.mcp.config import load_mcp_config, open_client
    from toolscore.mcp.lint_rules import _closest_tool
    from toolscore.mcp.snapshot import load_snapshot

    report = ConfigLintReport()
    instruction_files, host_configs = discover_files(paths or [Path()])
    if user_config is not None and user_config.is_file():
        host_configs.append(user_config)
    report.instruction_files = [str(p) for p in instruction_files]
    report.host_configs = [str(p) for p in host_configs]

    for config in host_configs:
        entries, error = _config_servers(config)
        if error is not None:
            report.issues.append(
                ConfigIssue(
                    "config-server-invalid", "error", str(config), None, error, _FIX_SERVER_INVALID
                )
            )
            continue
        for name in entries:
            report.servers.setdefault(name, str(config))
            if config.name == ".claude.json":
                continue
            try:
                spec = load_mcp_config(config, server=name)
            except (ValueError, KeyError, OSError) as exc:
                if "environment variable" in str(exc):  # fine in the file; unset here
                    if connect:
                        report.skipped_rules.setdefault(f"connect:{name}", str(exc))
                    continue
                report.issues.append(
                    ConfigIssue(
                        "config-server-invalid",
                        "error",
                        str(config),
                        None,
                        str(exc) if name in str(exc) else f"server '{name}': {exc}",
                        _FIX_SSE if "SSE" in str(exc) else _FIX_SERVER_INVALID,
                    )
                )
                continue
            if connect:
                try:
                    with open_client(spec, timeout=timeout) as client:
                        report.inventory[name] = {t.name: t for t in client.list_tools()}
                except Exception as exc:  # report, and keep linting the rest
                    report.skipped_rules.setdefault(
                        f"connect:{name}", f"could not list the tools of '{name}': {exc}"
                    )

    for bound, snapshot_file in snapshots or []:
        snapshot = load_snapshot(snapshot_file)
        server = bound or str(snapshot.server_info.get("name") or snapshot_file.stem)
        report.inventory[server] = snapshot.tool_map
        report.servers.setdefault(server, str(snapshot_file))

    if not report.inventory:
        for rule in INVENTORY_RULES:
            report.skipped_rules[rule] = (
                "no tool inventory: pass --snapshot (toolscore mcp list --json) or --pin "
                "(toolscore mcp pin) files, or --connect to start the configured servers"
            )

    all_tools: dict[str, MCPToolDef] = {}
    for tools in report.inventory.values():
        all_tools.update(tools)

    def find_tool(reference: str) -> MCPToolDef | None:
        match = _MCP_NAME.fullmatch(reference)
        if match:
            return report.inventory.get(match.group("server"), {}).get(match.group("tool"))
        return all_tools.get(reference)

    for file in instruction_files:
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if "://" in line and "mcp__" not in line and " tool" not in line:
                continue

            def add(
                rule: str, severity: str, message: str, fix: str, at: int = number, in_: Path = file
            ) -> None:
                report.issues.append(ConfigIssue(rule, severity, str(in_), at, message, fix))

            for match in _MCP_NAME.finditer(line):
                server, tool = match.group("server"), match.group("tool")
                if server.startswith(_FOREIGN_SERVER_PREFIXES):
                    continue
                if report.servers and server not in report.servers:
                    known = ", ".join(sorted(report.servers))
                    add(
                        "config-unknown-server",
                        "warning",
                        f"'{match.group(0)}' names server '{server}', which no MCP config here "
                        f"defines (configured: {known})",
                        _FIX_UNKNOWN_SERVER,
                    )
                elif server in report.inventory and tool not in report.inventory[server]:
                    hint = _closest_tool(tool, set(report.inventory[server]))
                    suggestion = f"; did you mean 'mcp__{server}__{hint}'?" if hint else ""
                    add(
                        "config-unknown-tool",
                        "error",
                        f"'{match.group(0)}': server '{server}' does not expose '{tool}'{suggestion}",
                        _FIX_UNKNOWN_TOOL,
                    )
            if all_tools:
                for match in _QUOTED_TOOL.finditer(line):
                    name = match.group("name")
                    if name in all_tools or name.startswith("mcp"):
                        continue
                    hint = _closest_tool(name, set(all_tools))
                    if hint is None:
                        continue  # not close to any MCP tool: likely a tool of something else
                    add(
                        "config-unknown-tool",
                        "error",
                        f"refers to the '{name}' tool, which no configured server exposes; "
                        f"did you mean '{hint}'?",
                        _FIX_UNKNOWN_TOOL,
                    )
            for match in _USE_TOOL.finditer(line):
                tool_def = find_tool(match.group("tool"))
                if tool_def is None:
                    continue
                kind = _verb_kind(match.group("verb"))
                hints = tool_def.annotations or {}
                verb = match.group("verb") + (match.group("particle") or "")
                if kind in ("delete", "write") and hints.get("readOnlyHint") is True:
                    add(
                        "config-annotation-contradiction",
                        "warning",
                        f"tells the agent to use '{tool_def.name}' to {verb}, but the tool declares "
                        "readOnlyHint: true",
                        _FIX_READ_ONLY,
                    )
                elif kind == "read" and hints.get("destructiveHint") is True:
                    add(
                        "config-annotation-contradiction",
                        "warning",
                        f"tells the agent to use '{tool_def.name}' to {verb}, but the tool declares "
                        "destructiveHint: true",
                        _FIX_DESTRUCTIVE,
                    )
    return report
