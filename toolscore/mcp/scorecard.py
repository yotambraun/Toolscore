"""Scoring and reporting for the MCP Scorecard.

This module aggregates the raw outputs of :mod:`toolscore.mcp.harness` -- the
server's tools, the executed :class:`~toolscore.mcp.harness.ScenarioResult`
list, and the :class:`~toolscore.mcp.harness.LintIssue` list -- into a single
:class:`MCPScorecard` with an A--F letter grade, and renders it as a rich
console panel, as PR-comment-friendly Markdown, or as a JSON dict.

Scoring
-------
The overall score is a weighted blend in ``[0, 1]``::

    score = 0.6 * happy_pass_rate
          + 0.2 * edge_resilience_rate
          + 0.2 * lint_score

where

* ``happy_pass_rate`` is the fraction of *happy* scenarios that passed (a tool
  that does what it advertises). With no happy scenarios this term is ``1.0``
  (full credit -- there is nothing to fail).
* ``edge_resilience_rate`` is the fraction of *edge* scenarios where the server
  responded without crashing or timing out. With no edge scenarios this term is
  ``1.0``.
* ``lint_score`` rewards clean schemas::

      lint_score = max(0, 1 - (errors * 0.25 + warnings * 0.1) / max(num_tools, 1))

When effect probes ran (``mcp test --probes``), a tool with a high-confidence
probe failure (it reported success and did not do it) costs as much as a tool
that fails all of its happy paths::

    score = max(0, score - 0.6 * tools_failing_probes / max(num_tools, 1))

so a run whose probes all pass, or that ran no probes, scores exactly as before.
Medium- and low-confidence probe findings are warnings and never change the
score.

Grade cap
---------
A tool that reports success and does nothing is a correctness bug, whatever the
other tools do. On a server with many tools the score penalty above is small
(``0.6 / 9`` on the official memory server, which still scored 93%), so any
high-confidence probe failure also **caps the letter grade at C**
(:data:`PROBE_GRADE_CAP`). The score is unchanged; the grade, the badge and every
report say ``capped because: probe-silent-noop on create_entities``. Turn the
cap off with ``probe_grade_cap=False`` (``--no-probe-grade-cap``).

Letter grades follow the usual bands: ``>= 0.9`` → A, ``>= 0.8`` → B,
``>= 0.7`` → C, ``>= 0.6`` → D, otherwise F. All rates guard against division by
zero, so a server with zero scenarios still scores cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from toolscore.mcp.harness import (
    estimate_tokens,
    generate_scenarios,
    lint_tools,
    output_schema_issues,
    run_scenarios,
    tool_definition_tokens,
)
from toolscore.verdict import GRADE_ORDER, FixSuggestion, letter_grade

#: The best grade a server with a high-confidence effect-probe failure can get.
PROBE_GRADE_CAP = "C"

if TYPE_CHECKING:
    from toolscore.mcp.client import MCPClient, MCPToolDef
    from toolscore.mcp.fixtures import ArgumentFixtures
    from toolscore.mcp.harness import LintIssue, ScenarioResult
    from toolscore.mcp.probes import ProbeConfig, ProbeResult

#: Weight of the happy-path pass rate in the overall score.
_WEIGHT_HAPPY = 0.6
#: Weight of the edge-case resilience rate in the overall score.
_WEIGHT_EDGE = 0.2
#: Weight of the lint score in the overall score.
_WEIGHT_LINT = 0.2

#: Per-error penalty applied to the lint score.
_LINT_ERROR_PENALTY = 0.25
#: Per-warning penalty applied to the lint score.
_LINT_WARNING_PENALTY = 0.1

#: Rich color per grade for console rendering.
_GRADE_COLORS: dict[str, str] = {
    "A": "bright_green",
    "B": "green",
    "C": "yellow",
    "D": "orange3",
    "F": "red",
}


@dataclass
class MCPScorecard:
    """An aggregated quality report for a single MCP server.

    Attributes:
        server_info: The ``serverInfo`` dict reported during the handshake.
        tools: The tools advertised by the server.
        results: The executed scenario results.
        lint: The lint issues found in the tool schemas and the text a model reads.
        instructions: The server ``instructions`` from the handshake, if any.
            MCP clients send them to the model with every session, so they count
            toward the context cost.
        protocol_version: The MCP protocol version the run used, if known.
        era: ``"modern"`` (per-request ``_meta``, 2026-07-28) or ``"legacy"``
            (``initialize`` handshake), if known.
        probes: Effect-probe results, or ``None`` when probes did not run
            (see :mod:`toolscore.mcp.probes`).
        probe_grade_cap: Cap the grade at :data:`PROBE_GRADE_CAP` when a
            high-confidence probe failed (the default). The score is unchanged.
    """

    server_info: dict[str, Any]
    tools: list[MCPToolDef]
    results: list[ScenarioResult]
    lint: list[LintIssue]
    instructions: str | None = None
    protocol_version: str | None = None
    era: str | None = None
    probes: list[ProbeResult] | None = None
    probe_grade_cap: bool = True

    # -- component rates ---------------------------------------------------

    @property
    def happy_pass_rate(self) -> float:
        """Fraction of happy-path scenarios that passed (``1.0`` if none)."""
        happy = [r for r in self.results if r.scenario.kind == "happy"]
        if not happy:
            return 1.0
        return sum(1 for r in happy if r.ok) / len(happy)

    @property
    def edge_resilience_rate(self) -> float:
        """Fraction of edge scenarios the server survived (``1.0`` if none)."""
        edge = [r for r in self.results if r.scenario.kind == "edge"]
        if not edge:
            return 1.0
        return sum(1 for r in edge if r.ok) / len(edge)

    @property
    def lint_error_count(self) -> int:
        """Number of ``error``-severity lint issues."""
        return sum(1 for i in self.lint if i.severity == "error")

    @property
    def lint_warning_count(self) -> int:
        """Number of ``warning``-severity lint issues."""
        return sum(1 for i in self.lint if i.severity == "warning")

    @property
    def lint_score(self) -> float:
        """Schema cleanliness score in ``[0, 1]`` (1.0 is spotless)."""
        denominator = max(len(self.tools), 1)
        penalty = (
            self.lint_error_count * _LINT_ERROR_PENALTY
            + self.lint_warning_count * _LINT_WARNING_PENALTY
        ) / denominator
        return max(0.0, 1.0 - penalty)

    @property
    def effect_rate(self) -> float | None:
        """Share of high-confidence probe checks that passed.

        ``None`` when probes did not run or none of their checks was
        high-confidence (nothing to grade).
        """
        graded = [p for p in self.probes or [] if p.graded]
        if not graded:
            return None
        return sum(1 for p in graded if p.status == "pass") / len(graded)

    @property
    def effect_label(self) -> str:
        """The effect rate for display: ``"75%"``, ``"n/a"`` (nothing graded) or ``""`` (no probes)."""
        if self.probes is None:
            return ""
        rate = self.effect_rate
        return "n/a" if rate is None else f"{rate:.0%}"

    @property
    def probe_evidence(self) -> dict[str, int] | None:
        """Probe outcomes as tri-state evidence, or ``None`` when probes did not run.

        ``pass`` and ``fail`` (any confidence); ``unknown`` counts inconclusive
        probes (they could not run, so they are not a pass); ``skipped`` counts
        probes that were not run (writes not allowed).
        """
        if self.probes is None:
            return None
        from toolscore.evidence import tally

        counts = tally(
            [
                "unknown" if p.status == "inconclusive" else p.status
                for p in self.probes
                if p.status != "skipped"
            ]
        )
        counts["skipped"] = sum(1 for p in self.probes if p.status == "skipped")
        return counts

    @property
    def probe_failed_tools(self) -> set[str]:
        """Tools with a high-confidence probe failure."""
        return {p.tool for p in self.probes or [] if p.severity == "error"}

    @property
    def probe_error_count(self) -> int:
        """High-confidence probe failures (they lower the grade)."""
        return sum(1 for p in self.probes or [] if p.severity == "error")

    @property
    def probe_warning_count(self) -> int:
        """Medium- and low-confidence probe failures (warnings only)."""
        return sum(1 for p in self.probes or [] if p.severity == "warning")

    # -- aggregate ---------------------------------------------------------

    @property
    def score(self) -> float:
        """The overall blended score in ``[0, 1]``."""
        base = (
            _WEIGHT_HAPPY * self.happy_pass_rate
            + _WEIGHT_EDGE * self.edge_resilience_rate
            + _WEIGHT_LINT * self.lint_score
        )
        failed = len(self.probe_failed_tools)
        if not failed:
            return base
        return max(0.0, base - _WEIGHT_HAPPY * failed / max(len(self.tools), 1))

    @property
    def uncapped_grade(self) -> str:
        """The letter grade the score alone earns (before any cap)."""
        return letter_grade(self.score)

    @property
    def grade_cap_reasons(self) -> list[str]:
        """Why the grade is capped, e.g. ``["probe-silent-noop on create_entities"]``.

        Empty when the cap is off, no high-confidence probe failed, or the score
        already earns :data:`PROBE_GRADE_CAP` or worse.
        """
        if not self.probe_grade_cap or grade_meets(PROBE_GRADE_CAP, self.uncapped_grade):
            return []
        reasons: list[str] = []
        for probe in self.probes or []:
            if probe.severity == "error":
                reason = f"{probe.rule} on {probe.tool}"
                if reason not in reasons:
                    reasons.append(reason)
        return reasons

    @property
    def grade_capped(self) -> bool:
        """Whether :attr:`grade` is lower than :attr:`uncapped_grade` because of the cap."""
        return bool(self.grade_cap_reasons)

    @property
    def grade_cap_note(self) -> str:
        """``"capped because: probe-silent-noop on create_entities"``, or ``""``."""
        reasons = self.grade_cap_reasons
        return f"capped because: {', '.join(reasons)}" if reasons else ""

    @property
    def grade(self) -> str:
        """The letter grade (``"A"`` … ``"F"``) for :attr:`score`, after the probe cap."""
        return PROBE_GRADE_CAP if self.grade_capped else self.uncapped_grade

    @property
    def total_tool_tokens(self) -> int:
        """Estimated total context tokens consumed by all tool definitions.

        Tool definitions are sent to the model on every request, so this is a
        proxy for how much of the context window the server's tools occupy.
        """
        return sum(tool_definition_tokens(t) for t in self.tools)

    @property
    def instructions_tokens(self) -> int:
        """Estimated context tokens of the server ``instructions`` (``0`` if none)."""
        return estimate_tokens(self.instructions) if self.instructions else 0

    @property
    def context_tokens(self) -> int:
        """Estimated context the server costs on every request: tools plus instructions."""
        return self.total_tool_tokens + self.instructions_tokens


def score_server(
    client: MCPClient,
    cases_per_tool: int = 3,
    include_edge_cases: bool = True,
    fixtures: ArgumentFixtures | None = None,
    probes: ProbeConfig | bool | None = None,
    allow_writes: bool = False,
    probe_grade_cap: bool = True,
) -> MCPScorecard:
    """Run the full scorecard against a started client.

    Lists the tools, generates and runs scenarios, lints the definitions and
    checks successful results against each tool's ``outputSchema``.

    Args:
        client: A started :class:`~toolscore.mcp.client.MCPClient` (stdio or HTTP).
        cases_per_tool: Happy-path scenarios per tool.
        include_edge_cases: Whether to run edge-case scenarios.
        fixtures: Known-good argument values (``--arg``) for the happy paths,
            for servers that only accept values from a sandbox.
        probes: Run the effect probes: ``True`` with heuristics only, or a
            :class:`~toolscore.mcp.probes.ProbeConfig`. ``None``/``False`` skips them.
        allow_writes: Let probes call write tools (round trips). Writes leave
            marker records on the server.
        probe_grade_cap: Cap the grade at C when a high-confidence probe
            fails (see the module docstring).

    Returns:
        The scorecard.
    """
    tools = client.list_tools()
    scenarios = generate_scenarios(
        tools,
        cases_per_tool=cases_per_tool,
        include_edge_cases=include_edge_cases,
        fixtures=fixtures,
    )
    results = run_scenarios(client, scenarios)
    lint = lint_tools(tools, instructions=client.server_instructions)
    lint.extend(output_schema_issues(tools, results))
    probe_results = None
    if probes:
        from toolscore.mcp.probes import ProbeConfig, run_probes

        config = probes if isinstance(probes, ProbeConfig) else None
        probe_results = run_probes(
            client, tools, config=config, allow_writes=allow_writes, fixtures=fixtures
        )
    return MCPScorecard(
        server_info=client.server_info,
        tools=tools,
        results=results,
        lint=lint,
        instructions=client.server_instructions,
        protocol_version=client.protocol_version,
        era=client.era,
        probes=probe_results,
        probe_grade_cap=probe_grade_cap,
    )


def protocol_label(card: MCPScorecard) -> str:
    """A short description of the protocol the run used, e.g. ``"MCP 2026-07-28 (stateless)"``."""
    if not card.protocol_version:
        return ""
    how = {"modern": "stateless", "legacy": "initialize handshake"}.get(card.era or "", "")
    return f"MCP {card.protocol_version}" + (f" ({how})" if how else "")


def _tool_summaries(card: MCPScorecard) -> list[dict[str, Any]]:
    """Summarize per-tool scenario outcomes.

    Args:
        card: The scorecard to summarize.

    Returns:
        One dict per tool with scenario pass counts and average latency, in the
        order the tools were advertised.
    """
    summaries: list[dict[str, Any]] = []
    for tool in card.tools:
        results = [r for r in card.results if r.scenario.tool == tool.name]
        total = len(results)
        passed = sum(1 for r in results if r.ok)
        durations = [r.duration for r in results]
        avg_latency = sum(durations) / len(durations) if durations else 0.0
        summaries.append(
            {
                "name": tool.name,
                "passed": passed,
                "total": total,
                "avg_latency_ms": round(avg_latency * 1000.0, 1),
                "tokens": tool_definition_tokens(tool),
            }
        )
    return summaries


def grade_meets(grade: str, threshold: str) -> bool:
    """Report whether ``grade`` is at least as good as ``threshold``.

    Args:
        grade: The achieved grade (case-insensitive).
        threshold: The minimum acceptable grade (case-insensitive).

    Returns:
        ``True`` if ``grade`` ranks the same as or better than ``threshold``.
        Unknown grades are treated as the worst possible.
    """
    order = {letter: rank for rank, letter in enumerate(GRADE_ORDER)}
    worst = len(GRADE_ORDER)
    return order.get(grade.upper(), worst) <= order.get(threshold.upper(), worst)


#: Priority bands for fix suggestions (lower numbers are more urgent).
_PRIORITY_HAPPY_FAIL = 0
_PRIORITY_EDGE_CRASH = 1
_PRIORITY_LINT_ERROR = 2
_PRIORITY_LINT_WARNING = 3

#: Rich color per fix priority, worst-first.
_PRIORITY_COLORS: dict[int, str] = {
    _PRIORITY_HAPPY_FAIL: "bold red",
    _PRIORITY_EDGE_CRASH: "red",
    _PRIORITY_LINT_ERROR: "yellow",
    _PRIORITY_LINT_WARNING: "dim",
}

#: Max number of fix items rendered in the console verdict before truncating.
_MAX_FIXES_SHOWN = 8


def build_fix_list(card: MCPScorecard, limit: int | None = None) -> list[FixSuggestion]:
    """Merge scenario failures and lint issues into one ranked, actionable list.

    The ranking, worst first:

    1. tools that **fail on valid input** (a happy-path scenario errored) and
       high-confidence **effect-probe failures** (the tool did not do what it reported),
    2. tools that **crash on bad input** (an edge scenario timed out / crashed),
    3. schema **errors**, then
    4. schema **warnings** and medium/low-confidence probe findings.

    Scenario failures are de-duplicated per tool (one entry per tool per kind),
    since a tool that fails one happy path usually fails them all.

    Args:
        card: The scorecard to analyze.
        limit: If given, return at most this many suggestions.

    Returns:
        The suggestions, sorted by priority then tool name.
    """
    suggestions: list[FixSuggestion] = []
    happy_seen: set[str] = set()
    edge_seen: set[str] = set()

    for result in card.results:
        if result.ok:
            continue
        tool = result.scenario.tool
        detail = result.detail or "no detail"
        if result.scenario.kind == "happy" and tool not in happy_seen:
            happy_seen.add(tool)
            suggestions.append(
                FixSuggestion(
                    tool=tool,
                    problem=f"fails on valid input ({detail})",
                    fix=(
                        "The tool errors on well-formed arguments - check the handler and that "
                        "the input schema matches what the tool actually accepts."
                    ),
                    priority=_PRIORITY_HAPPY_FAIL,
                )
            )
        elif result.scenario.kind == "edge" and tool not in edge_seen:
            edge_seen.add(tool)
            suggestions.append(
                FixSuggestion(
                    tool=tool,
                    problem=f"crashes on bad input ({detail})",
                    fix=(
                        "Validate and guard arguments so the tool returns a clean error result "
                        "instead of crashing or timing out."
                    ),
                    priority=_PRIORITY_EDGE_CRASH,
                )
            )

    for probe in card.probes or []:
        if probe.status != "fail":
            continue
        priority = _PRIORITY_HAPPY_FAIL if probe.severity == "error" else _PRIORITY_LINT_WARNING
        note = "" if probe.severity == "error" else f" ({probe.confidence} confidence)"
        suggestions.append(
            FixSuggestion(
                tool=probe.tool,
                problem=f"{probe.message} ({probe.rule}){note}",
                fix=probe.fix or "Check what the tool really does.",
                priority=priority,
            )
        )

    for issue in card.lint:
        priority = _PRIORITY_LINT_ERROR if issue.severity == "error" else _PRIORITY_LINT_WARNING
        suggestions.append(
            FixSuggestion(
                tool=issue.tool,
                problem=issue.message,
                fix=issue.fix or "Review the tool's schema and description.",
                priority=priority,
            )
        )

    suggestions.sort(key=lambda s: (s.priority, s.tool))
    if limit is not None:
        suggestions = suggestions[:limit]
    return suggestions


def print_scorecard(card: MCPScorecard, console: Console | None = None) -> None:
    """Render the scorecard to a rich console.

    Prints a header panel (server name/version and the big letter grade), a
    per-tool table (scenarios passed/total and average latency), and a lint
    section listing any issues.

    Args:
        card: The scorecard to render.
        console: The console to print to; a fresh one is created if omitted.
    """
    console = console or Console()

    name = str(card.server_info.get("name", "unknown server"))
    version = str(card.server_info.get("version", ""))
    title = f"{name} {version}".strip()
    color = _GRADE_COLORS.get(card.grade, "white")

    header = Text()
    header.append(f"MCP Scorecard: {title}\n", style="bold")
    header.append("Grade ", style="dim")
    header.append(card.grade, style=f"bold {color}")
    header.append(f"   Score {card.score:.0%}\n", style="dim")
    if card.grade_capped:
        header.append(
            f"Grade {card.uncapped_grade} by score, {card.grade_cap_note}\n", style="bold red"
        )
    header.append(
        f"happy {card.happy_pass_rate:.0%}  |  "
        f"edge {card.edge_resilience_rate:.0%}  |  "
        f"lint {card.lint_score:.0%}"
        + (f"  |  effect {card.effect_label}" if card.effect_label else ""),
        style="dim",
    )
    if protocol_label(card):
        header.append(f"\n{protocol_label(card)}", style="dim")
    console.print(Panel(header, border_style=color, expand=False))

    table = Table(title="Tools", header_style="bold magenta", title_style="bold")
    table.add_column("Tool", style="cyan")
    table.add_column("Scenarios", justify="right")
    table.add_column("Avg latency", justify="right")
    table.add_column("Def. tokens", justify="right")
    for summary in _tool_summaries(card):
        passed = summary["passed"]
        total = summary["total"]
        status_color = "green" if total and passed == total else "yellow" if passed else "red"
        table.add_row(
            summary["name"],
            Text(f"{passed}/{total}", style=status_color),
            f"{summary['avg_latency_ms']:.1f} ms",
            str(summary["tokens"]),
        )
    console.print(table)
    console.print(
        f"[dim]Tool definitions cost ~{card.total_tool_tokens} estimated tokens of context "
        f"across {len(card.tools)} tool(s).[/dim]"
    )
    if card.instructions:
        console.print(
            f"[dim]Server instructions add ~{card.instructions_tokens} tokens "
            f"(~{card.context_tokens} in total, sent with every request).[/dim]"
        )

    if card.probes is not None:
        _print_probes(card.probes, console)

    fixes = build_fix_list(card)
    if not fixes:
        console.print(
            "\n[green]No issues found - an LLM should be able to use this server cleanly.[/green]"
        )
        return

    console.print("\n[bold]Top issues to fix[/bold]")
    for index, suggestion in enumerate(fixes[:_MAX_FIXES_SHOWN], start=1):
        issue_color = _PRIORITY_COLORS.get(suggestion.priority, "white")
        console.print(
            f"  [bold]{index}.[/bold] [{issue_color}]{escape(suggestion.tool)}[/{issue_color}]  "
            f"{escape(suggestion.problem)}"
        )
        console.print(f"     [dim]-> {escape(suggestion.fix)}[/dim]")
    remaining = len(fixes) - min(len(fixes), _MAX_FIXES_SHOWN)
    if remaining > 0:
        console.print(f"  [dim]... and {remaining} more issue(s).[/dim]")


_PROBE_STATUS_STYLE = {
    "pass": "green",
    "fail": "red",
    "inconclusive": "yellow",
    "skipped": "dim",
}


def _probe_status(probe: ProbeResult) -> str:
    """``pass``, ``FAIL`` (grade-affecting), ``warn`` (other failures), ``inconclusive``..."""
    if probe.status == "fail":
        return "FAIL" if probe.severity == "error" else "warn"
    return probe.status


def _print_probes(probes: list[ProbeResult], console: Console) -> None:
    """Print the effect-probe table (skipped probes as one line)."""
    shown = [p for p in probes if p.status != "skipped"]
    skipped = [p for p in probes if p.status == "skipped"]
    if shown:
        table = Table(title="Effect probes", header_style="bold magenta", title_style="bold")
        table.add_column("Probe")
        table.add_column("Tool", style="cyan")
        table.add_column("Result")
        table.add_column("Confidence", style="dim")
        table.add_column("Detail")
        for probe in shown:
            style = _PROBE_STATUS_STYLE.get(probe.status, "white")
            if probe.status == "fail" and probe.severity == "warning":
                style = "yellow"
            detail = escape(probe.message) + (f" [dim]({probe.rule})[/dim]" if probe.rule else "")
            table.add_row(
                probe.probe,
                escape(probe.tool),
                Text(_probe_status(probe), style=style),
                probe.confidence if probe.status in ("pass", "fail") else "",
                detail,
            )
        console.print(table)
    counts = {
        "pass": sum(1 for p in probes if p.status == "pass"),
        "fail": sum(1 for p in probes if p.status == "fail"),
        "unknown": sum(1 for p in probes if p.status == "inconclusive"),
    }
    console.print(
        f"[dim]Probe evidence: {counts['pass']} pass, {counts['fail']} fail, "
        f"{counts['unknown']} unknown (inconclusive is never a pass).[/dim]"
    )
    if skipped:
        names = ", ".join(sorted({p.tool for p in skipped}))
        console.print(
            f"[dim]{len(skipped)} probe(s) skipped because they write ({names}); "
            "add --allow-writes to run them against a disposable server.[/dim]"
        )


def _probe_json(probe: ProbeResult) -> dict[str, Any]:
    return {
        "probe": probe.probe,
        "tool": probe.tool,
        "check": probe.check,
        "status": probe.status,
        "rule": probe.rule,
        "severity": probe.severity,
        "confidence": probe.confidence,
        "message": probe.message,
        "basis": probe.basis,
        "fix": probe.fix,
        "evidence": probe.evidence,
    }


def scorecard_to_markdown(card: MCPScorecard) -> str:
    """Render the scorecard as Markdown for READMEs or PR comments.

    Args:
        card: The scorecard to render.

    Returns:
        A Markdown document with a grade line, component scores (including the
        tool-definition token cost), a per-tool summary table, and a ranked
        "Top issues to fix" list.
    """
    name = str(card.server_info.get("name", "unknown server"))
    version = str(card.server_info.get("version", ""))
    title = f"{name} {version}".strip()

    lines: list[str] = []
    lines.append(f"# MCP Scorecard: {title}")
    lines.append("")
    lines.append(f"**Grade: {card.grade}** &middot; Score {card.score:.0%}")
    if card.grade_capped:
        lines.append("")
        lines.append(
            f"**Grade {card.uncapped_grade} by score, {card.grade_cap_note}** "
            f"(a tool reported success and did not do it)."
        )
    lines.append("")
    lines.append(
        f"- Happy-path pass rate: {card.happy_pass_rate:.0%}\n"
        f"- Edge-case resilience: {card.edge_resilience_rate:.0%}\n"
        f"- Lint score: {card.lint_score:.0%} "
        f"({card.lint_error_count} errors, {card.lint_warning_count} warnings)\n"
        f"- Tool-definition tokens (estimated): ~{card.total_tool_tokens} "
        f"across {len(card.tools)} tool(s)"
    )
    if card.instructions:
        lines.append(
            f"- Server instructions (estimated): ~{card.instructions_tokens} tokens "
            f"(~{card.context_tokens} in total, sent with every request)"
        )
    if card.effect_label:
        lines.append(
            f"- Effect probes: {card.effect_label} of high-confidence checks passed "
            f"({card.probe_error_count} failures, {card.probe_warning_count} warnings)"
        )
    if card.probe_evidence is not None:
        ev = card.probe_evidence
        lines.append(
            f"- Probe evidence: {ev['pass']} pass, {ev['fail']} fail, {ev['unknown']} unknown "
            f"(inconclusive), {ev['skipped']} skipped"
        )
    if protocol_label(card):
        lines.append(f"- Protocol: {protocol_label(card)}")
    lines.append("")

    lines.append("## Tools")
    lines.append("")
    lines.append("| Tool | Scenarios | Avg latency | Def. tokens |")
    lines.append("| --- | --- | --- | --- |")
    for summary in _tool_summaries(card):
        lines.append(
            f"| `{summary['name']}` | {summary['passed']}/{summary['total']} | "
            f"{summary['avg_latency_ms']:.1f} ms | {summary['tokens']} |"
        )
    lines.append("")

    probes = [p for p in card.probes or [] if p.status != "skipped"]
    if probes:
        lines.append("## Effect probes")
        lines.append("")
        lines.append("| Probe | Tool | Result | Confidence | Detail |")
        lines.append("| --- | --- | --- | --- | --- |")
        for probe in probes:
            rule = f" (`{probe.rule}`)" if probe.rule else ""
            confidence = probe.confidence if probe.status in ("pass", "fail") else ""
            message = " ".join(probe.message.split()).replace("|", "\\|")
            lines.append(
                f"| {probe.probe} | `{probe.tool}` | {_probe_status(probe)} | {confidence} | "
                f"{message}{rule} |"
            )
        lines.append("")

    lines.append("## Top issues to fix")
    lines.append("")
    fixes = build_fix_list(card)
    if fixes:
        for suggestion in fixes:
            lines.append(
                f"- **`{suggestion.tool}`** — {suggestion.problem}. _Fix:_ {suggestion.fix}"
            )
    else:
        lines.append("- No issues found — an LLM should be able to use this server cleanly.")
    lines.append("")

    return "\n".join(lines)


def scorecard_to_json(card: MCPScorecard) -> dict[str, Any]:
    """Render the scorecard as a JSON-serializable dict.

    Args:
        card: The scorecard to render.

    Returns:
        A plain dict (lists/dicts/strings/numbers only) capturing the grade,
        component scores, per-tool summaries, every scenario result, and every
        lint issue.
    """
    return {
        "server": {
            "name": card.server_info.get("name", ""),
            "version": card.server_info.get("version", ""),
        },
        "grade": card.grade,
        "score": card.score,
        "grade_cap": {
            "enabled": card.probe_grade_cap,
            "capped": card.grade_capped,
            "cap": PROBE_GRADE_CAP,
            "uncapped_grade": card.uncapped_grade,
            "reasons": card.grade_cap_reasons,
            "note": card.grade_cap_note,
        },
        "protocol": {"version": card.protocol_version, "era": card.era},
        "total_tool_tokens": card.total_tool_tokens,
        "instructions_tokens": card.instructions_tokens,
        "context_tokens": card.context_tokens,
        "scores": {
            "happy_pass_rate": card.happy_pass_rate,
            "edge_resilience_rate": card.edge_resilience_rate,
            "lint_score": card.lint_score,
            "effect_rate": card.effect_rate,
        },
        "probes": None if card.probes is None else [_probe_json(p) for p in card.probes],
        "probe_evidence": card.probe_evidence,
        "tools": _tool_summaries(card),
        "results": [
            {
                "tool": r.scenario.tool,
                "kind": r.scenario.kind,
                "description": r.scenario.description,
                "arguments": r.scenario.arguments,
                "ok": r.ok,
                "is_error": r.is_error,
                "duration": r.duration,
                "detail": r.detail,
            }
            for r in card.results
        ],
        "lint": [
            {
                "tool": i.tool,
                "rule": i.rule,
                "severity": i.severity,
                "message": i.message,
                "fix": i.fix,
            }
            for i in card.lint
        ],
        "fixes": [
            {"tool": s.tool, "problem": s.problem, "fix": s.fix, "priority": s.priority}
            for s in build_fix_list(card)
        ],
    }
