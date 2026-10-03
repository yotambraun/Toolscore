"""required_call_recall and the versioned result record (1.10)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner
from rich.console import Console

from toolscore import Regex, evaluate
from toolscore.cli import main
from toolscore.core import evaluate_trace
from toolscore.reports import print_evaluation_summary

if TYPE_CHECKING:
    from pathlib import Path


def test_required_call_recall_counts_every_required_call() -> None:
    """A repeated required call that never happened is missed; name-set metrics cannot see it."""
    result = evaluate(
        expected=[{"tool": "search"}, {"tool": "search"}, {"tool": "read_file"}],
        actual=[{"tool": "search", "args": {}}, {"tool": "read_file", "args": {}}],
    )

    assert result.required_call_recall == 2 / 3
    assert result.metrics["required_call_recall"] == 2 / 3
    assert result.metrics["tool_correctness_metrics"]["tool_correctness"] == 1.0


def test_required_call_recall_is_none_without_requirements() -> None:
    result = evaluate(expected=[], actual=[{"tool": "search", "args": {}}])

    assert result.required_call_recall is None


def test_a_required_call_that_failed_is_not_completed() -> None:
    """A failed attempt does not meet the requirement; a later successful retry does."""
    failed = {"tool": "read_file", "args": {"path": "/srv/a"}, "is_error": True}
    succeeded = {"tool": "read_file", "args": {"path": "/srv/a"}}

    assert evaluate(expected=[{"tool": "read_file"}], actual=[failed]).required_call_recall == 0.0
    retried = evaluate(expected=[{"tool": "read_file"}], actual=[failed, succeeded])
    assert retried.required_call_recall == 1.0


def test_required_call_recall_weight_is_opt_in() -> None:
    """By default the score ignores skipped calls; weighting recall makes it count."""
    expected = [{"tool": "list_dir"}, {"tool": "read_file"}]
    actual = [{"tool": "read_file", "args": {"path": "/srv/a"}, "is_error": True}]

    default = evaluate(expected=expected, actual=actual)
    weighted = evaluate(expected=expected, actual=actual, weights={"required_call_recall": 1.0})

    # Unchanged default: 0.4 * selection + 0.3 * args + 0.2 * sequence + 0.1 * (1 - redundant).
    assert default.score == pytest.approx(0.4 * 1.0 + 0.3 * 1.0 + 0.2 * 0.5 + 0.1 * 1.0)
    assert default.required_call_recall == 0.0
    # Recall gets half of the renormalized weight, and it is zero.
    assert weighted.score == pytest.approx(default.score / 2)

    console = Console(record=True, width=120)
    print_evaluation_summary(default, console=console)
    assert "Required calls completed: 0 of 2" in console.export_text()

    complete = evaluate(expected=expected, actual=[{"tool": "list_dir"}, {"tool": "read_file"}])
    console = Console(record=True, width=120)
    print_evaluation_summary(complete, console=console)
    assert "Required calls completed" not in console.export_text()


def test_file_based_evaluation_reports_the_same_metric(tmp_path: Path) -> None:
    gold = tmp_path / "gold.json"
    trace = tmp_path / "trace.json"
    gold.write_text(json.dumps([{"tool": "search"}, {"tool": "search"}]))
    trace.write_text(json.dumps([{"tool": "search", "args": {}}]))

    result = evaluate_trace(gold, trace, format="custom")

    assert result.required_call_recall == 0.5


def test_to_dict_is_a_complete_versioned_record() -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "<Opaque>"

    result = evaluate(
        expected=[{"tool": "search", "args": {"q": Regex(r"^cats")}}, {"tool": "write"}],
        actual=[
            {"tool": "search", "args": {"q": "cats"}, "result": Opaque(), "duration": 0.5},
            {"tool": "write", "args": {"path": "a"}, "error": "permission denied", "cost": 0.01},
        ],
        weights={
            "selection_accuracy": 1.0,
            "argument_f1": 0.0,
            "sequence_accuracy": 0.0,
            "redundant_rate": 0.0,
        },
    )

    record = result.to_dict()
    json.dumps(record)  # always JSON-safe

    assert record["schema_version"] == "2"
    assert record["weights"] == {
        "selection_accuracy": 1.0,
        "argument_f1": 0.0,
        "sequence_accuracy": 0.0,
        "redundant_rate": 0.0,
        "required_call_recall": 0.0,
    }
    # The required write failed, so only one of the two required calls was completed.
    assert record["required_call_recall"] == 0.5
    assert record["calls"]["actual"][0] == {
        "tool": "search",
        "args": {"q": "cats"},
        "result": "<Opaque>",
        "is_error": False,
        "error": None,
        "duration": 0.5,
        "cost": None,
    }
    assert record["calls"]["actual"][1]["is_error"] is True
    assert record["calls"]["actual"][1]["error"] == "permission denied"
    assert record["calls"]["expected"][0]["tool"] == "search"
    assert "Regex" in record["calls"]["expected"][0]["args"]["q"]
    # Keys that existing consumers read are unchanged.
    assert record["score"] == result.score
    assert record["grade"] == result.grade
    assert record["gold_calls_count"] == 2
    assert record["trace_calls_count"] == 2


def test_cli_weight_option_and_file_based_weights(tmp_path: Path) -> None:
    gold, trace, out = tmp_path / "gold.json", tmp_path / "trace.json", tmp_path / "out.json"
    gold.write_text(json.dumps([{"tool": "list_dir"}, {"tool": "read_file"}]))
    trace.write_text(json.dumps([{"tool": "read_file", "args": {}, "is_error": True}]))

    weighted = evaluate_trace(gold, trace, format="custom", weights={"required_call_recall": 1.0})
    assert weighted.score == pytest.approx(evaluate_trace(gold, trace, format="custom").score / 2)

    ran = CliRunner().invoke(
        main,
        ["eval", str(gold), str(trace), "-o", str(out), "--weight", "required_call_recall=1"],
    )
    assert ran.exit_code == 0, ran.output
    summary = json.loads(out.read_text())["summary"]
    assert summary["score"] == pytest.approx(weighted.score)
    assert summary["weights"]["required_call_recall"] == pytest.approx(0.5)
    assert summary["required_call_recall"] == 0.0
    assert summary["failed_calls"] == 1

    bad = CliRunner().invoke(main, ["eval", str(gold), str(trace), "--weight", "oops"])
    assert bad.exit_code != 0
    assert "NAME=VALUE" in bad.output
