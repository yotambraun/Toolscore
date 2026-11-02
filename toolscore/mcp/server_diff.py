"""Compare two MCP servers, builds or configs: ``toolscore mcp diff A B``.

Each side is a live server (a launch command or a URL) or a saved snapshot
(``toolscore mcp list --json``) or lock file (``toolscore mcp pin``). The diff
reports:

* tools added and removed;
* per tool, what changed in the title, description, input and output schema
  and annotations, with unified text diffs;
* capability changes (see :mod:`toolscore.mcp.pin`);
* the lint findings that are new in B and those B resolved;
* the server identity, protocol and instructions;
* with ``--test`` (live servers only), the two scorecards: grade, score, the
  component rates and the effect probes that newly fail or pass.

**Breaking** changes are the ones that can break an agent or widen what a tool
can do: a removed tool, a removed parameter, a newly required parameter, a
parameter whose type changed, a new ``delete`` or ``exec`` capability, a new
lint error, and (with ``--test``) a lower grade or a newly failing probe.
``--fail-on`` decides the exit code: ``any`` difference (default),
``breaking`` only, or ``none``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from toolscore.mcp.pin import RISKY_CAPABILITIES, tool_capabilities, tool_definition
from toolscore.mcp.snapshot import text_diff

if TYPE_CHECKING:
    from toolscore.mcp.harness import LintIssue
    from toolscore.mcp.scorecard import MCPScorecard
    from toolscore.mcp.snapshot import ServerSnapshot

__all__ = [
    "DIFF_FAIL_MODES",
    "ServerDiff",
    "ToolChange",
    "diff_snapshots",
    "render_diff",
    "text_diff",
]

#: ``--fail-on`` modes.
DIFF_FAIL_MODES: tuple[str, ...] = ("any", "breaking", "none")


def _pretty(value: Any) -> str:
    return "" if value is None else json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


@dataclass
class ToolChange:
    """How one tool differs between A and B.

    Attributes:
        tool: The tool name.
        fields: The changed fields (``description``, ``inputSchema``...).
        diffs: A unified diff per changed field.
        breaking: Why the change can break an agent (empty if it cannot).
        capabilities_added: Capabilities B has and A did not.
        capabilities_removed: Capabilities A had and B does not.
    """

    tool: str
    fields: list[str] = field(default_factory=list)
    diffs: dict[str, str] = field(default_factory=dict)
    breaking: list[str] = field(default_factory=list)
    capabilities_added: list[str] = field(default_factory=list)
    capabilities_removed: list[str] = field(default_factory=list)


@dataclass
class ServerDiff:
    """The difference between two servers (see the module docstring).

    Attributes:
        a: Label of side A.
        b: Label of side B.
        added: Tools only in B.
        removed: Tools only in A.
        changed: Tools in both that differ.
        lint_new: Lint issues in B that A did not have.
        lint_resolved: Lint issues in A that B no longer has.
        server_changes: Identity, protocol and instructions changes, as text.
        scorecards: ``(A, B)`` scorecards when ``--test`` ran, else ``None``.
        new_tool_capabilities: Capabilities of each added tool.
    """

    a: str
    b: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[ToolChange] = field(default_factory=list)
    lint_new: list[LintIssue] = field(default_factory=list)
    lint_resolved: list[LintIssue] = field(default_factory=list)
    server_changes: list[str] = field(default_factory=list)
    scorecards: tuple[MCPScorecard, MCPScorecard] | None = None
    new_tool_capabilities: dict[str, list[str]] = field(default_factory=dict)

    @property
    def breaking(self) -> list[str]:
        """Every breaking change, as one line each."""
        reasons = [f"tool {name!r} removed" for name in self.removed]
        for name, caps in self.new_tool_capabilities.items():
            risky = sorted(RISKY_CAPABILITIES & set(caps))
            if risky:
                reasons.append(f"new tool {name!r} can {' and '.join(risky)}")
        for change in self.changed:
            reasons.extend(f"{change.tool}: {reason}" for reason in change.breaking)
        reasons.extend(
            f"{i.tool}: new lint error {i.rule}" for i in self.lint_new if i.severity == "error"
        )
        reasons.extend(self.score_regressions)
        return reasons

    @property
    def score_regressions(self) -> list[str]:
        """A lower grade and newly failing high-confidence probes (``--test`` only)."""
        if self.scorecards is None:
            return []
        from toolscore.verdict import GRADE_ORDER

        card_a, card_b = self.scorecards
        reasons = []
        if GRADE_ORDER.index(card_b.grade) > GRADE_ORDER.index(card_a.grade):
            reasons.append(f"grade {card_a.grade} -> {card_b.grade}")
        reasons.extend(
            f"{tool}: probe {rule} now fails" for tool, rule in sorted(self.probe_deltas[0])
        )
        return reasons

    @property
    def probe_deltas(self) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
        """``(newly failing, newly passing)`` high-confidence probe ``(tool, rule)`` pairs."""
        if self.scorecards is None:
            return set(), set()

        def failing(card: MCPScorecard) -> set[tuple[str, str]]:
            return {(p.tool, p.rule) for p in card.probes or [] if p.severity == "error"}

        card_a, card_b = self.scorecards
        return failing(card_b) - failing(card_a), failing(card_a) - failing(card_b)

    @property
    def identical(self) -> bool:
        """Whether nothing differs (tools, lint, server, and scorecards when tested)."""
        same_cards = self.scorecards is None or (
            self.scorecards[0].grade == self.scorecards[1].grade
            and abs(self.scorecards[0].score - self.scorecards[1].score) < 1e-9
        )
        return (
            not self.added
            and not self.removed
            and not self.changed
            and not self.lint_new
            and not self.lint_resolved
            and not self.server_changes
            and same_cards
        )

    def fails(self, fail_on: str = "any") -> bool:
        """Whether the diff fails under ``fail_on`` (``any``, ``breaking``, ``none``)."""
        if fail_on not in DIFF_FAIL_MODES:
            raise ValueError(f"fail_on must be one of {DIFF_FAIL_MODES}, got {fail_on!r}")
        if fail_on == "none":
            return False
        if fail_on == "breaking":
            return bool(self.breaking)
        return not self.identical

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe report."""
        data: dict[str, Any] = {
            "a": self.a,
            "b": self.b,
            "identical": self.identical,
            "added": self.added,
            "removed": self.removed,
            "new_tool_capabilities": self.new_tool_capabilities,
            "changed": [
                {
                    "tool": c.tool,
                    "fields": c.fields,
                    "diffs": c.diffs,
                    "breaking": c.breaking,
                    "capabilities_added": c.capabilities_added,
                    "capabilities_removed": c.capabilities_removed,
                }
                for c in self.changed
            ],
            "lint_new": [_issue(i) for i in self.lint_new],
            "lint_resolved": [_issue(i) for i in self.lint_resolved],
            "server_changes": self.server_changes,
            "breaking": self.breaking,
            "scorecards": None,
        }
        if self.scorecards is not None:
            card_a, card_b = self.scorecards
            newly_failing, newly_passing = self.probe_deltas
            data["scorecards"] = {
                "a": {"grade": card_a.grade, "score": card_a.score},
                "b": {"grade": card_b.grade, "score": card_b.score},
                "score_delta": card_b.score - card_a.score,
                "rates": {
                    name: {"a": getattr(card_a, name), "b": getattr(card_b, name)}
                    for name in (
                        "happy_pass_rate",
                        "edge_resilience_rate",
                        "lint_score",
                        "effect_rate",
                    )
                },
                "probes_newly_failing": sorted(f"{t}:{r}" for t, r in newly_failing),
                "probes_newly_passing": sorted(f"{t}:{r}" for t, r in newly_passing),
            }
        return data


def _issue(issue: LintIssue) -> dict[str, Any]:
    return {
        "tool": issue.tool,
        "rule": issue.rule,
        "severity": issue.severity,
        "message": issue.message,
    }


def _schema_breaks(before: Any, after: Any) -> list[str]:
    """Breaking input-schema changes: removed or newly required parameters, changed types."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return []
    raw_old, raw_new = before.get("properties"), after.get("properties")
    old_props: dict[str, Any] = raw_old if isinstance(raw_old, dict) else {}
    new_props: dict[str, Any] = raw_new if isinstance(raw_new, dict) else {}
    req_old, req_new = before.get("required"), after.get("required")
    old_required = set(req_old) if isinstance(req_old, list) else set()
    new_required = set(req_new) if isinstance(req_new, list) else set()
    reasons = [f"parameter {name!r} removed" for name in sorted(set(old_props) - set(new_props))]
    reasons.extend(
        f"parameter {name!r} is now required" for name in sorted(new_required - old_required)
    )
    for name in sorted(set(old_props) & set(new_props)):
        old_type = old_props[name].get("type") if isinstance(old_props[name], dict) else None
        new_type = new_props[name].get("type") if isinstance(new_props[name], dict) else None
        if old_type != new_type:
            reasons.append(f"parameter {name!r} type {old_type} -> {new_type}")
    return reasons


def diff_snapshots(
    a: ServerSnapshot,
    b: ServerSnapshot,
    scorecards: tuple[MCPScorecard, MCPScorecard] | None = None,
) -> ServerDiff:
    """Compare two server snapshots.

    Args:
        a: The baseline (for example the released build).
        b: The candidate.
        scorecards: Scorecards of both sides, to compare grades and probes.

    Returns:
        The :class:`ServerDiff`.
    """
    from toolscore.mcp.harness import lint_tools

    diff = ServerDiff(a=a.label, b=b.label, scorecards=scorecards)
    tools_a, tools_b = a.tool_map, b.tool_map
    diff.added = sorted(tools_b.keys() - tools_a.keys())
    diff.removed = sorted(tools_a.keys() - tools_b.keys())
    diff.new_tool_capabilities = {
        name: list(tool_capabilities(tools_b[name])) for name in diff.added
    }
    for name in sorted(tools_a.keys() & tools_b.keys()):
        before, after = tool_definition(tools_a[name]), tool_definition(tools_b[name])
        caps_a = set(tool_capabilities(tools_a[name]))
        caps_b = set(tool_capabilities(tools_b[name]))
        if before == after and caps_a == caps_b:
            continue
        change = ToolChange(tool=name)
        for key in before:
            if before[key] == after[key]:
                continue
            change.fields.append(key)
            if isinstance(before[key], str) or isinstance(after[key], str):
                text = text_diff(before[key] or "", after[key] or "", f"a/{key}", f"b/{key}")
            else:
                text = text_diff(_pretty(before[key]), _pretty(after[key]), f"a/{key}", f"b/{key}")
            change.diffs[key] = text
        change.breaking.extend(_schema_breaks(before["inputSchema"], after["inputSchema"]))
        change.capabilities_added = sorted(caps_b - caps_a)
        change.capabilities_removed = sorted(caps_a - caps_b)
        change.breaking.extend(
            f"can now {cap}" for cap in change.capabilities_added if cap in RISKY_CAPABILITIES
        )
        diff.changed.append(change)

    def keyed(issues: list[LintIssue]) -> dict[tuple[str, str, str], LintIssue]:
        return {(i.tool, i.rule, i.message): i for i in issues}

    lint_a = keyed(lint_tools(a.tools, instructions=a.instructions))
    lint_b = keyed(lint_tools(b.tools, instructions=b.instructions))
    diff.lint_new = [lint_b[k] for k in sorted(lint_b.keys() - lint_a.keys())]
    diff.lint_resolved = [lint_a[k] for k in sorted(lint_a.keys() - lint_b.keys())]

    for key in ("name", "version"):
        old, new = str(a.server_info.get(key) or ""), str(b.server_info.get(key) or "")
        if old != new:
            diff.server_changes.append(f"server {key}: {old or '(none)'} -> {new or '(none)'}")
    if a.protocol_version and b.protocol_version and a.protocol_version != b.protocol_version:
        diff.server_changes.append(f"protocol: {a.protocol_version} -> {b.protocol_version}")
    if (a.instructions or "") != (b.instructions or ""):
        diff.server_changes.append(
            "instructions changed:\n"
            + text_diff(
                a.instructions or "", b.instructions or "", "a/instructions", "b/instructions"
            )
        )
    return diff


def render_diff(diff: ServerDiff, color: bool = True) -> str:
    """The diff as console markup (``color``) or plain text (for Markdown code blocks)."""
    from rich.markup import escape

    def esc(text: str) -> str:
        return escape(text) if color else text

    def style(text: str, name: str) -> str:
        return f"[{name}]{text}[/{name}]" if color else text

    lines = [f"{esc(diff.a)}  ->  {esc(diff.b)}"]
    if diff.identical:
        lines.append(style("No differences.", "green"))
        return "\n".join(lines)
    for name in diff.added:
        caps = ", ".join(diff.new_tool_capabilities.get(name, []))
        lines.append(style(f"+ {name}", "green") + f"  ({esc(caps)})")
    for name in diff.removed:
        lines.append(style(f"- {name}", "red") + "  (removed)")
    for change in diff.changed:
        lines.append(style(f"~ {change.tool}", "yellow") + f"  {', '.join(change.fields)}")
        if change.capabilities_added or change.capabilities_removed:
            lines.append(
                f"    capabilities: +{change.capabilities_added or []} "
                f"-{change.capabilities_removed or []}"
            )
        for text in change.diffs.values():
            for line in text.splitlines():
                tint = "green" if line.startswith("+") else "red" if line.startswith("-") else "dim"
                lines.append("    " + style(esc(line), tint))
    for issue in diff.lint_new:
        lines.append(style(f"+ lint {issue.severity}", "red" if issue.severity == "error" else "yellow")
                     + f" {esc(issue.tool)}: {esc(issue.message)} ({issue.rule})")  # fmt: skip
    for issue in diff.lint_resolved:
        lines.append(style("- lint resolved", "green") + f" {esc(issue.tool)}: {issue.rule}")
    for change_text in diff.server_changes:
        lines.append(esc(change_text))
    if diff.scorecards is not None:
        card_a, card_b = diff.scorecards
        lines.append(
            f"scorecard: {card_a.grade} ({card_a.score:.0%}) -> {card_b.grade} ({card_b.score:.0%})"
        )
        newly_failing, newly_passing = diff.probe_deltas
        for tool, rule in sorted(newly_failing):
            lines.append(style(f"  probe now fails: {tool} {rule}", "red"))
        for tool, rule in sorted(newly_passing):
            lines.append(style(f"  probe now passes: {tool} {rule}", "green"))
    if diff.breaking:
        lines.append(style(f"Breaking: {len(diff.breaking)}", "bold red"))
        lines.extend(f"  - {esc(reason)}" for reason in diff.breaking)
    return "\n".join(lines)
