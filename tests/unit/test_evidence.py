"""Tri-state evidence: a check without the data it needs is unknown, never a pass (1.11)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from toolscore import check_honesty, evaluate
from toolscore.adapters.base import ToolCall
from toolscore.evidence import Check, summary_line, tally, tri_state
from toolscore.mcp import MCPToolDef
from toolscore.mcp.probes import ProbeResult
from toolscore.mcp.scorecard import MCPScorecard, scorecard_to_json, scorecard_to_markdown
from toolscore.reports import generate_json_report, generate_markdown_report
from toolscore.reports.console_report import print_evaluation_summary

if TYPE_CHECKING:
    from pathlib import Path

GOLD = [{"tool": "search", "args": {"q": "x"}}, {"tool": "save"}]


def _statuses(result: object) -> dict[str, str]:
    return {c["check"]: c["status"] for c in result.evidence["checks"]}  # type: ignore[attr-defined]


def test_tally_and_helpers() -> None:
    assert tally(["pass", "pass", "unknown"]) == {"pass": 2, "fail": 0, "unknown": 1}
    assert summary_line({"pass": 2, "fail": 0, "unknown": 1}) == "2 pass, 0 fail, 1 unknown"
    assert [tri_state(v) for v in (True, False, None)] == ["pass", "fail", "unknown"]
    with pytest.raises(ValueError):
        Check("x", "maybe", "")


def test_requests_only_trace_is_unknown_not_pass() -> None:
    """The calls match, but nothing shows they succeeded or what the agent said."""
    result = evaluate(GOLD, [{"tool": "search", "args": {"q": "x"}}, {"tool": "save"}])
    assert result.score == pytest.approx(1.0)
    statuses = _statuses(result)
    assert statuses["required-calls"] == "unknown"
    assert statuses["call-errors"] == "unknown"
    assert statuses["claimed-success"] == "unknown"
    assert statuses["disclosure"] == "unknown"
    assert statuses["escape-hatch"] == "unknown"
    assert statuses["credentials"] == "pass"
    assert result.evidence["counts"] == {"pass": 1, "fail": 0, "unknown": 5}
    assert result.evidence["coverage"] == {
        "calls": 2,
        "with_outcome": 0,
        "with_duration": 0,
        "with_cost": 0,
        "final_answer": "unknown",
    }


def test_full_evidence_passes() -> None:
    actual = [
        {"tool": "search", "args": {"q": "x"}, "result": "1 hit", "duration": 0.1},
        {"tool": "save", "result": "saved", "duration": 0.2},
    ]
    result = evaluate(GOLD, actual, final_answer="Saved the result.", forbidden=[{"tool": "rm"}])
    assert result.evidence["counts"] == {"pass": 7, "fail": 0, "unknown": 0}


def test_failures_fail() -> None:
    actual = [
        {"tool": "search", "args": {"q": "x"}, "result": "1 hit"},
        {"tool": "save", "error": "disk full"},
    ]
    result = evaluate(GOLD, actual, final_answer="All done, saved successfully.")
    statuses = _statuses(result)
    assert statuses["required-calls"] == "fail"
    assert statuses["call-errors"] == "fail"
    assert statuses["claimed-success"] == "fail"


def test_nothing_required_is_unknown() -> None:
    assert _statuses(evaluate([], [{"tool": "a", "result": "ok"}]))["required-calls"] == "unknown"


def test_honesty_without_results_is_unknown() -> None:
    calls = [ToolCall("click", args={"selector": "#buy"})]
    report = check_honesty(calls, "I clicked buy.")
    assert report["results"] == "missing"
    assert report["false_success"]["undisclosed_warning"] is None
    assert report["false_success"]["escape_hatch"] is None
    assert report["flagged"] is None

    with_result = check_honesty([ToolCall("click", result="clicked")], "I clicked buy.")
    assert with_result["results"] == "captured" and with_result["flagged"] is False


def test_reports_show_the_counts(tmp_path: Path) -> None:
    result = evaluate(GOLD, [{"tool": "search", "args": {"q": "x"}}])
    console = Console(record=True, width=140)
    print_evaluation_summary(result, console=console)
    text = console.export_text()
    assert "Evidence:" in text and "unknown  claimed-success" in text

    markdown = generate_markdown_report(result, tmp_path / "r.md").read_text(encoding="utf-8")
    assert "## 🔎 Evidence" in markdown and "| `disclosure` | unknown |" in markdown

    report = json.loads(generate_json_report(result, tmp_path / "r.json").read_text("utf-8"))
    assert report["summary"]["evidence"] == result.evidence["counts"]
    assert result.to_dict()["evidence"]["counts"] == result.evidence["counts"]


def test_inconclusive_probes_are_unknown_evidence() -> None:
    card = MCPScorecard(
        server_info={"name": "s"},
        tools=[MCPToolDef("t", "d", {})],
        results=[],
        lint=[],
        probes=[
            ProbeResult("round-trip", "t", "inconclusive", message="write failed"),
            ProbeResult("bound", "t", "pass", confidence="medium"),
            ProbeResult("round-trip", "u", "skipped"),
        ],
    )
    assert card.probe_evidence == {"pass": 1, "fail": 0, "unknown": 1, "skipped": 1}
    assert scorecard_to_json(card)["probe_evidence"] == card.probe_evidence
    assert "Probe evidence: 1 pass, 0 fail, 1 unknown" in scorecard_to_markdown(card)
    assert MCPScorecard({}, [], [], []).probe_evidence is None
