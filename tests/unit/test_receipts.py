"""Receipts, regrade, and unknown (never 0) latency and cost in reports (1.11)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner
from rich.console import Console

from toolscore import evaluate
from toolscore.adapters.base import ToolCall
from toolscore.cli import main
from toolscore.core import evaluate_trace
from toolscore.metrics.cost import calculate_cost_attribution, calculate_latency, format_measure
from toolscore.receipts import (
    ReceiptMismatchError,
    build_receipt,
    canonical_json,
    load_receipt,
    regrade,
    verify_receipt,
    write_receipt,
)
from toolscore.reports import (
    generate_csv_report,
    generate_html_report,
    generate_json_report,
    generate_markdown_report,
    print_evaluation_summary,
)

if TYPE_CHECKING:
    from pathlib import Path

GOLD = [{"tool": "search", "args": {"q": "cats"}}, {"tool": "save", "args": {"id": 1}}]


# -- unknown, never 0 ------------------------------------------------------------


def test_latency_and_cost_are_unknown_without_data() -> None:
    calls = [ToolCall("search"), ToolCall("save")]
    latency, cost = calculate_latency(calls), calculate_cost_attribution(calls)
    assert latency["status"] == cost["status"] == "unknown"
    assert latency["total_duration"] is None and cost["total_cost"] is None
    assert format_measure(latency, "total_duration") == "unknown"
    assert format_measure(cost, "total_cost", unit="$") == "unknown"


def test_partial_coverage_is_labelled() -> None:
    calls = [ToolCall("search", duration=0.5, cost=0.002), ToolCall("save")]
    latency = calculate_latency(calls)
    assert latency["status"] == "partial" and latency["measured_calls"] == 1
    assert format_measure(latency, "total_duration") == "0.500s (1 of 2 calls)"
    assert format_measure(calculate_cost_attribution(calls), "total_cost", "$") == (
        "$0.0020 (1 of 2 calls)"
    )


def test_a_measured_zero_is_zero_and_no_calls_cost_nothing() -> None:
    measured = calculate_latency([ToolCall("search", duration=0.0)])
    assert measured["status"] == "measured" and measured["total_duration"] == 0.0
    assert format_measure(measured, "total_duration") == "0.000s"
    assert calculate_latency([])["total_duration"] == 0.0


def test_every_report_says_unknown(tmp_path: Path) -> None:
    result = evaluate(GOLD, [{"tool": "search", "args": {"q": "cats"}}])
    assert result.metrics["latency_metrics"]["status"] == "unknown"

    console = Console(record=True, width=120)
    print_evaluation_summary(result, console=console, verbose=True)
    text = console.export_text()
    assert "Total Duration" in text and "unknown" in text and "0.000s" not in text

    markdown = generate_markdown_report(result, tmp_path / "r.md").read_text(encoding="utf-8")
    assert "| Total Duration | unknown |" in markdown
    assert "| Total Cost | unknown |" in markdown

    html = generate_html_report(result, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "unknown" in html and "0.00s" not in html

    csv = generate_csv_report(result, tmp_path / "r.csv").read_text(encoding="utf-8")
    assert "total_duration,unknown" in csv

    report = json.loads(generate_json_report(result, tmp_path / "r.json").read_text("utf-8"))
    assert report["summary"]["total_duration"] is None
    assert report["summary"]["latency_status"] == "unknown"
    assert report["summary"]["score"] == result.score
    assert report["summary"]["weights"] == result.to_dict()["weights"]


def test_records_keep_call_ids() -> None:
    result = evaluate(GOLD, [{"tool": "search", "args": {"q": "cats"}, "id": "call_1"}])
    assert result.trace_calls[0].id == "call_1"
    assert result.to_dict()["calls"]["actual"][0]["id"] == "call_1"
    assert ToolCall("t", metadata={"jsonrpc_id": 7}).id == "7"


# -- receipts --------------------------------------------------------------------


def _files(tmp_path: Path) -> tuple[Path, Path]:
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps(GOLD), encoding="utf-8")
    trace = tmp_path / "trace.json"
    trace.write_text(
        json.dumps(
            [
                {"tool": "search", "args": {"q": "cats"}, "result": "3 cats"},
                {"tool": "search", "args": {"q": "cats"}, "result": "3 cats"},
            ]
        ),
        encoding="utf-8",
    )
    return gold, trace


def test_canonical_json_ignores_key_order() -> None:
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1})


def test_a_receipt_hashes_its_inputs_and_itself(tmp_path: Path) -> None:
    gold, trace = _files(tmp_path)
    result = evaluate_trace(gold, trace)
    receipt = build_receipt(result, inputs={"gold": gold, "trace": trace, "forbidden": None})
    assert set(receipt["inputs"]) == {"gold", "trace"}
    assert receipt["result"]["score"] == result.score
    assert len(receipt["receipt_sha256"]) == 64
    assert verify_receipt(receipt) == []

    # The same evaluation hashes the same.
    again = build_receipt(evaluate_trace(gold, trace), inputs={"gold": gold, "trace": trace})
    assert again["result"]["record_sha256"] == receipt["result"]["record_sha256"]
    assert again["contract_sha256"] == receipt["contract_sha256"]

    tampered = dict(receipt, result={**receipt["result"], "score": 1.0})
    assert any("receipt_sha256" in p for p in verify_receipt(tampered))

    trace.write_text("[]", encoding="utf-8")
    assert any("trace" in p and "changed" in p for p in verify_receipt(receipt))


def test_regrade_rescored_with_a_new_contract_and_weights(tmp_path: Path) -> None:
    gold, trace = _files(tmp_path)
    original = evaluate_trace(gold, trace)
    path = write_receipt(
        tmp_path / "run.receipt.json",
        build_receipt(original, inputs={"gold": gold, "trace": trace}, settings={"format": "auto"}),
    )
    assert load_receipt(path)["result"]["grade"] == original.grade

    same = regrade(path)
    assert same.result.score == pytest.approx(original.score)
    assert same.score_delta == pytest.approx(0.0)

    weighted = regrade(path, weights={"required_call_recall": 1.0})
    assert weighted.result.score < original.score  # the required save never happened

    lenient = tmp_path / "lenient.json"
    lenient.write_text(json.dumps([{"tool": "search"}, {"tool": "search"}]), encoding="utf-8")
    regraded = regrade(path, gold=lenient)
    assert regraded.result.score == pytest.approx(1.0)
    assert regraded.receipt["settings"]["regraded_from"] == load_receipt(path)["receipt_sha256"]


def test_regrade_refuses_a_changed_trace(tmp_path: Path) -> None:
    gold, trace = _files(tmp_path)
    path = write_receipt(
        tmp_path / "r.json",
        build_receipt(evaluate_trace(gold, trace), {"gold": gold, "trace": trace}),
    )
    trace.write_text(json.dumps([{"tool": "search", "args": {"q": "dogs"}}]), encoding="utf-8")
    with pytest.raises(ReceiptMismatchError, match="trace"):
        regrade(path)
    forced = regrade(path, verify=False)
    assert forced.problems and "changed" in forced.problems[0]


def test_regrade_a_bare_trace_needs_gold(tmp_path: Path) -> None:
    gold, trace = _files(tmp_path)
    with pytest.raises(ValueError, match="gold"):
        regrade(trace)
    assert regrade(trace, gold=gold).previous is None


def test_cli_eval_receipt_and_regrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _gold, trace = _files(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        main, ["eval", "gold.json", "trace.json", "-o", "out.json", "--receipt", "r.receipt.json"]
    )
    assert result.exit_code == 0, result.output
    receipt = load_receipt(tmp_path / "r.receipt.json")
    assert receipt["inputs"]["trace"]["path"] == "trace.json"

    out = runner.invoke(
        main,
        ["regrade", "r.receipt.json", "--weight", "required_call_recall=1", "--json", "rg.json",
         "--receipt-dir", "new"],
    )  # fmt: skip
    assert out.exit_code == 0, out.output
    assert "Nothing was re-run" in out.output
    rows = json.loads((tmp_path / "rg.json").read_text(encoding="utf-8"))
    assert rows[0]["delta"] < 0
    assert (tmp_path / "new" / "r.receipt.receipt.json").is_file()

    trace.write_text("[]", encoding="utf-8")
    refused = runner.invoke(main, ["regrade", "r.receipt.json"])
    assert refused.exit_code == 1
    assert "not regraded" in refused.output
