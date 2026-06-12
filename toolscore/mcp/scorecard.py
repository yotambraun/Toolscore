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

Letter grades follow the usual bands: ``>= 0.9`` → A, ``>= 0.8`` → B,
``>= 0.7`` → C, ``>= 0.6`` → D, otherwise F. All rates guard against division by
zero, so a server with zero scenarios still scores cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from toolscore.mcp.client import MCPToolDef
    from toolscore.mcp.harness import LintIssue, ScenarioResult

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

#: Grade thresholds, highest first.
_GRADE_BANDS: tuple[tuple[float, str], ...] = (
    (0.9, "A"),
    (0.8, "B"),
    (0.7, "C"),
    (0.6, "D"),
)

#: Ordering of grades from best to worst, used for ``--fail-under`` comparisons.
GRADE_ORDER: tuple[str, ...] = ("A", "B", "C", "D", "F")

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
        lint: The lint issues found in the tool schemas.
    """

    server_info: dict[str, Any]
    tools: list[MCPToolDef]
    results: list[ScenarioResult]
    lint: list[LintIssue]

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

    # -- aggregate ---------------------------------------------------------

    @property
    def score(self) -> float:
        """The overall blended score in ``[0, 1]``."""
        return (
            _WEIGHT_HAPPY * self.happy_pass_rate
            + _WEIGHT_EDGE * self.edge_resilience_rate
            + _WEIGHT_LINT * self.lint_score
        )

    @property
    def grade(self) -> str:
        """The letter grade (``"A"`` … ``"F"``) for :attr:`score`."""
        score = self.score
        for threshold, letter in _GRADE_BANDS:
            if score >= threshold:
                return letter
        return "F"


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
    header.append(
        f"happy {card.happy_pass_rate:.0%}  |  "
        f"edge {card.edge_resilience_rate:.0%}  |  "
        f"lint {card.lint_score:.0%}",
        style="dim",
    )
    console.print(Panel(header, border_style=color, expand=False))

    table = Table(title="Tools", header_style="bold magenta", title_style="bold")
    table.add_column("Tool", style="cyan")
    table.add_column("Scenarios", justify="right")
    table.add_column("Avg latency", justify="right")
    for summary in _tool_summaries(card):
        passed = summary["passed"]
        total = summary["total"]
        status_color = "green" if total and passed == total else "yellow" if passed else "red"
        table.add_row(
            summary["name"],
            Text(f"{passed}/{total}", style=status_color),
            f"{summary['avg_latency_ms']:.1f} ms",
        )
    console.print(table)

    if card.lint:
        lint_table = Table(
            title=(f"Lint ({card.lint_error_count} errors, {card.lint_warning_count} warnings)"),
            header_style="bold magenta",
            title_style="bold",
        )
        lint_table.add_column("Severity")
        lint_table.add_column("Tool", style="cyan")
        lint_table.add_column("Message")
        for issue in card.lint:
            severity_color = "red" if issue.severity == "error" else "yellow"
            lint_table.add_row(
                Text(issue.severity, style=severity_color),
                issue.tool,
                issue.message,
            )
        console.print(lint_table)
    else:
        console.print("[green]No lint issues.[/green]")


def scorecard_to_markdown(card: MCPScorecard) -> str:
    """Render the scorecard as Markdown for READMEs or PR comments.

    Args:
        card: The scorecard to render.

    Returns:
        A Markdown document with a grade badge line, a per-tool summary table,
        and a bulleted lint list.
    """
    name = str(card.server_info.get("name", "unknown server"))
    version = str(card.server_info.get("version", ""))
    title = f"{name} {version}".strip()

    lines: list[str] = []
    lines.append(f"# MCP Scorecard: {title}")
    lines.append("")
    lines.append(f"**Grade: {card.grade}** &middot; Score {card.score:.0%}")
    lines.append("")
    lines.append(
        f"- Happy-path pass rate: {card.happy_pass_rate:.0%}\n"
        f"- Edge-case resilience: {card.edge_resilience_rate:.0%}\n"
        f"- Lint score: {card.lint_score:.0%} "
        f"({card.lint_error_count} errors, {card.lint_warning_count} warnings)"
    )
    lines.append("")

    lines.append("## Tools")
    lines.append("")
    lines.append("| Tool | Scenarios | Avg latency |")
    lines.append("| --- | --- | --- |")
    for summary in _tool_summaries(card):
        lines.append(
            f"| `{summary['name']}` | {summary['passed']}/{summary['total']} | "
            f"{summary['avg_latency_ms']:.1f} ms |"
        )
    lines.append("")

    lines.append("## Lint")
    lines.append("")
    if card.lint:
        for issue in card.lint:
            marker = "**error**" if issue.severity == "error" else "warning"
            lines.append(f"- {marker} &middot; `{issue.tool}`: {issue.message}")
    else:
        lines.append("- No lint issues.")
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
        "scores": {
            "happy_pass_rate": card.happy_pass_rate,
            "edge_resilience_rate": card.edge_resilience_rate,
            "lint_score": card.lint_score,
        },
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
        "lint": [{"tool": i.tool, "severity": i.severity, "message": i.message} for i in card.lint],
    }
