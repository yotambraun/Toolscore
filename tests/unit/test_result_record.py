"""required_call_recall and the versioned result record (1.10)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from toolscore import Regex, evaluate
from toolscore.core import evaluate_trace

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
    }
    assert record["required_call_recall"] == 1.0
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
