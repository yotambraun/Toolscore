"""A high-confidence effect-probe failure caps the scorecard grade at C (1.11)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner
from rich.console import Console

from toolscore.cli import main
from toolscore.mcp import MCPToolDef
from toolscore.mcp.badge import badge_endpoint, badge_svg
from toolscore.mcp.probes import ProbeResult
from toolscore.mcp.scorecard import (
    PROBE_GRADE_CAP,
    MCPScorecard,
    print_scorecard,
    scorecard_to_json,
    scorecard_to_markdown,
)


def _card(probes: list[ProbeResult] | None, cap: bool = True, tools: int = 9) -> MCPScorecard:
    return MCPScorecard(
        server_info={"name": "memory-server", "version": "0.6.3"},
        tools=[MCPToolDef(name=f"tool_{i}", description="d", input_schema={}) for i in range(tools)],
        results=[],
        lint=[],
        probes=probes,
        probe_grade_cap=cap,
    )


_NOOP = ProbeResult("round-trip", "tool_0", "fail", "probe-silent-noop", "high", "no-op")


def test_a_high_confidence_failure_caps_an_a_at_c() -> None:
    card = _card([_NOOP])
    assert card.score == pytest.approx(1 - 0.6 / 9)
    assert card.uncapped_grade == "A"
    assert card.grade == PROBE_GRADE_CAP == "C"
    assert card.grade_capped
    assert card.grade_cap_reasons == ["probe-silent-noop on tool_0"]
    assert card.grade_cap_note == "capped because: probe-silent-noop on tool_0"


def test_the_cap_leaves_the_score_alone_and_can_be_turned_off() -> None:
    capped, uncapped = _card([_NOOP]), _card([_NOOP], cap=False)
    assert capped.score == uncapped.score
    assert uncapped.grade == "A" and not uncapped.grade_capped
    assert uncapped.grade_cap_note == ""


@pytest.mark.parametrize(
    "probe",
    [
        ProbeResult("bound", "tool_0", "fail", "probe-bound-short", "medium", "warn"),
        ProbeResult("round-trip", "tool_0", "pass", "", "high", "ok"),
        ProbeResult("round-trip", "tool_0", "inconclusive", "", "", "could not run"),
    ],
)
def test_warnings_passes_and_inconclusive_probes_do_not_cap(probe: ProbeResult) -> None:
    card = _card([probe])
    assert card.grade == "A" and not card.grade_capped


def test_a_grade_already_at_or_below_the_cap_is_not_marked_capped() -> None:
    card = _card([_NOOP], tools=1)  # the penalty alone takes it to D or worse
    assert card.uncapped_grade in ("D", "F")
    assert card.grade == card.uncapped_grade
    assert card.grade_cap_reasons == []


def test_reasons_are_listed_once_per_rule_and_tool() -> None:
    lost = ProbeResult("round-trip", "tool_1", "fail", "probe-data-lost", "high", "gone")
    card = _card([_NOOP, _NOOP, lost])
    assert card.grade_cap_reasons == ["probe-silent-noop on tool_0", "probe-data-lost on tool_1"]


def test_every_report_says_why() -> None:
    card = _card([_NOOP])
    note = "capped because: probe-silent-noop on tool_0"

    console = Console(record=True, width=120)
    print_scorecard(card, console=console)
    text = console.export_text()
    assert "Grade C" in text and "Grade A by score" in text and note in text

    markdown = scorecard_to_markdown(card)
    assert "**Grade: C**" in markdown and note in markdown

    report = scorecard_to_json(card)
    assert report["grade"] == "C"
    assert report["grade_cap"] == {
        "enabled": True,
        "capped": True,
        "cap": "C",
        "uncapped_grade": "A",
        "reasons": ["probe-silent-noop on tool_0"],
        "note": note,
    }

    svg = badge_svg(card.grade, card.grade_cap_note)
    assert "C (capped) · Toolscore" in svg and note in svg
    assert badge_endpoint(card.grade, card.grade_cap_note)["message"] == "C (capped) · Toolscore"
    assert badge_endpoint("A")["message"] == "A · Toolscore"


def test_cli_caps_the_grade_and_the_flag_turns_it_off(tmp_path: Path) -> None:
    server = Path(__file__).resolve().parents[1] / "fixtures" / "probe_server.py"
    command = f"{sys.executable} {server} --bug skip-silent"
    capped_json, badge = tmp_path / "capped.json", tmp_path / "badge.json"
    result = CliRunner().invoke(
        main,
        [
            "mcp", "test", command, "--probes", "--allow-writes", "--report", "json",
            "-o", str(capped_json), "--badge-json", str(badge),
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    report = json.loads(capped_json.read_text(encoding="utf-8"))
    assert report["grade_cap"]["reasons"] == ["probe-silent-noop on add_entry"]
    assert report["grade"] == "C"
    assert "capped because: probe-silent-noop on add_entry" in result.output
    assert json.loads(badge.read_text(encoding="utf-8"))["message"] == "C (capped) · Toolscore"

    gated = CliRunner().invoke(
        main, ["mcp", "test", command, "--probes", "--allow-writes", "--fail-under", "B"]
    )
    assert gated.exit_code == 1

    plain_json = tmp_path / "plain.json"
    uncapped = CliRunner().invoke(
        main,
        [
            "mcp", "test", command, "--probes", "--allow-writes", "--no-probe-grade-cap",
            "--report", "json", "-o", str(plain_json),
        ],
    )  # fmt: skip
    assert uncapped.exit_code == 0, uncapped.output
    plain = json.loads(plain_json.read_text(encoding="utf-8"))
    assert plain["score"] == report["score"]
    assert plain["grade"] == plain["grade_cap"]["uncapped_grade"]
    assert plain["grade_cap"]["enabled"] is False and plain["grade_cap"]["reasons"] == []
