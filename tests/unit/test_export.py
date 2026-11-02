"""Neutral run records: toolscore export --format aef (1.11)."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

from click.testing import CliRunner

from toolscore.cli import main
from toolscore.export import SCHEMA_PATH, export_records, validate_record, write_export
from toolscore.mcp.agent import run_study, spec_from_mapping
from toolscore.receipts import sha256_hex
from toolscore.stats import load_runs

if TYPE_CHECKING:
    from pathlib import Path


def _runs(tmp_path: Path) -> Path:
    out = tmp_path / "runs.jsonl"
    spec = spec_from_mapping(
        {
            "name": "x",
            "server": {"command": [sys.executable, "-m", "toolscore.mcp.sample_server"]},
            "provider": "scripted",
            "arms": [{"id": "a"}],
            "guard": {"deny": [{"tool": "delete_note"}]},
            "tasks": [
                {
                    "id": "t",
                    "prompt": "p",
                    "expected": [{"tool": "list_notes"}],
                    "script": [
                        {
                            "calls": [
                                {"tool": "delete_note", "args": {"title": "x"}},
                                {"tool": "list_notes", "args": {}},
                            ]
                        },
                        {"text": "Listed; the delete was refused."},
                    ],
                }
            ],
        }
    )
    run_study(spec, output=out)
    return out


def test_agent_runs_become_valid_records(tmp_path: Path) -> None:
    records = export_records([_runs(tmp_path)])
    assert len(records) == 1
    record = records[0]
    assert validate_record(record) == []
    assert record["schema"] == "toolscore.run-record" and record["schema_version"] == "1"
    requested, completed = record["requested_calls"], record["completed_calls"]
    assert [r["call_id"] for r in requested] == [c["call_id"] for c in completed]
    assert requested[0]["denied"] and completed[0]["status"] == "denied"
    assert completed[1]["status"] == "ok" and len(completed[1]["result_sha256"]) == 64
    assert record["coverage"]["unknown"] == []  # the denied call never ran: no duration to miss
    assert record["final_answer"]["status"] == "known"
    assert record["evaluation"]["evidence_counts"]["fail"] >= 1  # a call failed (denied)
    assert record["source"]["kind"] == "agent-run" and record["source"]["line"] == 1


def test_a_bare_trace_has_explicit_unknown_coverage(tmp_path: Path) -> None:
    trace = tmp_path / "trace.json"
    trace.write_text(json.dumps([{"tool": "search", "args": {"q": "x"}}]), encoding="utf-8")
    record = export_records([trace])[0]
    assert validate_record(record) == []
    assert record["call_id_source"] == "synthesized"
    assert record["requested_calls"][0]["call_id"] == "call-1"
    assert record["completed_calls"][0]["status"] == "unknown"
    assert record["coverage"]["unknown"] == ["results", "durations", "cost", "final_answer"]
    assert record["cost"] == {"usd": None, "status": "unknown"}
    assert record["outcome"] == "unknown"  # nothing to check against


def test_traces_with_gold_and_receipts(tmp_path: Path) -> None:
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps([{"tool": "search", "args": {"q": "x"}}]), encoding="utf-8")
    trace = tmp_path / "trace.json"
    trace.write_text(
        json.dumps(
            [{"tool": "search", "args": {"q": "x"}, "result": "1 hit", "duration": 0.2, "id": "c"}]
        ),
        encoding="utf-8",
    )
    graded = export_records([trace], gold=gold, variant="v1")[0]
    assert graded["outcome"] == "pass" and graded["variant"] == "v1"
    assert graded["evaluation"]["score"] == 1.0 and graded["call_id_source"] == "trace"

    receipt = tmp_path / "r.json"
    result = CliRunner().invoke(
        main,
        ["eval", str(gold), str(trace), "-o", str(tmp_path / "o.json"), "--receipt", str(receipt)],
    )
    assert result.exit_code == 0, result.output
    from_receipt = export_records([receipt])[0]
    assert from_receipt["source"]["kind"] == "receipt"
    assert from_receipt["source"]["trace"]["sha256"] == sha256_hex(trace.read_bytes())
    assert from_receipt["outcome"] == "pass"


def test_tampering_breaks_the_record_hash(tmp_path: Path) -> None:
    record = export_records([_runs(tmp_path)])[0]
    record["outcome"] = "pass" if record["outcome"] != "pass" else "fail"
    assert "record_sha256" in " ".join(validate_record(record))


def test_cli_export_manifest_and_compare(tmp_path: Path) -> None:
    runs = _runs(tmp_path)
    out = tmp_path / "export.jsonl"
    result = CliRunner().invoke(main, ["export", "--format", "aef", str(runs), "-o", str(out)])
    assert result.exit_code == 0, result.output
    manifest = json.loads((tmp_path / "export.jsonl.manifest.json").read_text(encoding="utf-8"))
    assert manifest["records"] == 1
    assert manifest["output"]["sha256"] == sha256_hex(out.read_bytes())
    assert manifest["sources"][0]["sha256"] == sha256_hex(runs.read_bytes())
    # Exported records are runs that toolscore compare reads too.
    assert load_runs([out])[0].variant == "a"
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["title"] == "Toolscore run record"


def test_write_export_is_deterministic(tmp_path: Path) -> None:
    records = export_records([_runs(tmp_path)])
    first, _ = write_export(tmp_path / "a.jsonl", records, [])
    second, _ = write_export(tmp_path / "b.jsonl", records, [])
    assert first.read_bytes() == second.read_bytes()
