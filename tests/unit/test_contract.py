"""Contracts v2: required, optional and forbidden calls, and alternatives (1.11)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from toolscore import evaluate, evaluate_contract, evaluate_trace
from toolscore.cli import main
from toolscore.contract import (
    CONTRACT_SCHEMA_PATH,
    contract_from_mapping,
    is_contract,
    matcher_from_json,
    split_optional,
)
from toolscore.matchers import Matcher
from toolscore.receipts import regrade

if TYPE_CHECKING:
    from pathlib import Path

SEARCH = {"tool": "search", "args": {"q": "cats"}}
SAVE = {"tool": "save", "args": {"id": 1}}


def test_optional_calls_are_neither_missing_nor_extra() -> None:
    contract = {"required": [SEARCH, SAVE], "optional": [{"tool": "list"}]}
    without = evaluate_contract(contract, [SEARCH, SAVE])
    with_optional = evaluate_contract(contract, [SEARCH, {"tool": "list"}, SAVE])
    assert without.score == pytest.approx(1.0)
    assert with_optional.score == pytest.approx(1.0)
    assert with_optional.metrics["contract_metrics"]["optional_matched"] == [
        {"index": 1, "tool": "list"}
    ]
    # The plain gold evaluation counts the same call as extra.
    assert evaluate([SEARCH, SAVE], [SEARCH, {"tool": "list"}, SAVE]).score < 1.0
    # Every call is still in the record and seen by the trace checks.
    assert [c.tool for c in with_optional.trace_calls] == ["search", "list", "save"]


def test_an_optional_entry_still_fills_a_required_call() -> None:
    kept, dropped = split_optional(
        [{"tool": "search"}, {"tool": "search"}], [{"tool": "search"}], [{"tool": "search"}]
    )
    assert len(kept) == 1 and dropped == [1]


def test_optional_args_must_match() -> None:
    contract = {
        "required": [SEARCH],
        "optional": [{"tool": "list", "args": {"n": {"$type": "integer"}}}],
    }
    assert evaluate_contract(contract, [SEARCH, {"tool": "list", "args": {"n": 5}}]).score == 1.0
    assert evaluate_contract(contract, [SEARCH, {"tool": "list", "args": {"n": "5"}}]).score < 1.0


def test_alternatives_highest_composite_wins_ties_by_declaration_order() -> None:
    contract = {
        "required": [
            SEARCH,
            {
                "id": "store",
                "alternatives": [[{"tool": "create_note"}], [{"tool": "upsert_note"}]],
            },
        ]
    }
    second = evaluate_contract(contract, [SEARCH, {"tool": "upsert_note"}])
    assert second.score == pytest.approx(1.0)
    chosen = second.metrics["contract_metrics"]["alternatives"]["chosen"]
    assert chosen == {"store": {"option": 1, "calls": ["upsert_note"]}}
    neither = evaluate_contract(contract, [SEARCH])
    assert neither.metrics["contract_metrics"]["alternatives"]["chosen"]["store"]["option"] == 0
    combos = neither.metrics["contract_metrics"]["alternatives"]["combinations"]
    assert [c["choice"] for c in combos] == [{"store": 0}, {"store": 1}]


def test_top_level_alternatives_are_appended() -> None:
    contract = contract_from_mapping(
        {"required": [SEARCH], "alternatives": [{"alternatives": [SAVE, {"tool": "other"}]}]}
    )
    assert [len(calls) for calls, _ in contract.expansions()] == [2, 2]
    assert contract.groups[0].id == "alternatives-1"


def test_forbidden_calls_are_reported_not_scored() -> None:
    contract = {
        "required": [SEARCH],
        "forbidden": [{"tool": "rm", "args": {"p": {"$regex": "^/"}}}],
    }
    result = evaluate_contract(contract, [SEARCH, {"tool": "rm", "args": {"p": "/etc"}}])
    assert len(result.policy_violations) == 1
    statuses = {c["check"]: c["status"] for c in result.evidence["checks"]}
    assert statuses["forbidden-calls"] == "fail"


def test_json_matchers() -> None:
    assert isinstance(matcher_from_json({"$any": True}), Matcher)
    assert matcher_from_json({"$type": ["string", "null"]}).matches(None)  # type: ignore[union-attr]
    assert matcher_from_json({"$approx": {"value": 1.0, "abs": 0.1}}).matches(1.05)  # type: ignore[union-attr]
    assert matcher_from_json({"$regex": "a"}).matches("cat")  # type: ignore[union-attr]
    assert matcher_from_json({"plain": {"$any": True}})["plain"].matches(3)
    with pytest.raises(ValueError):
        matcher_from_json({"$type": "date"})


def test_contract_validation() -> None:
    for bad in (
        {"contract_version": 1, "required": []},
        {"required": [{"args": {}}]},
        {"required": [{"tool": "x", "extra": 1}]},
        {"required": [{"alternatives": [[SEARCH]]}]},
        {"surprise": True},
        {"required": [{"id": "a", "alternatives": [SEARCH, SAVE]},
                      {"id": "a", "alternatives": [SEARCH, SAVE]}]},
    ):  # fmt: skip
        with pytest.raises(ValueError):
            contract_from_mapping(bad)
    too_many = {"required": [{"alternatives": [SEARCH, SAVE]} for _ in range(9)]}
    with pytest.raises(ValueError, match="combinations"):
        contract_from_mapping(too_many).expansions()
    assert is_contract({"required": []}) and not is_contract([SEARCH])


def test_weights_and_min_score_in_the_contract() -> None:
    contract = {
        "required": [SEARCH, SAVE],
        "weights": {"required_call_recall": 1.0},
        "min_score": 0.5,
    }
    result = evaluate_contract(contract, [SEARCH])
    assert result._weights["required_call_recall"] > 0
    assert result.metrics["contract_metrics"]["min_score"] == 0.5


def test_files_cli_and_regrade(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps({"contract_version": 2, "required": [SEARCH], "optional": [{"tool": "list"}]}),
        encoding="utf-8",
    )
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps([SEARCH]), encoding="utf-8")
    trace = tmp_path / "trace.json"
    trace.write_text(
        json.dumps([{**SEARCH, "result": "ok"}, {"tool": "list", "result": "[]"}]), encoding="utf-8"
    )
    assert evaluate_trace(contract, trace).score == pytest.approx(1.0)
    assert evaluate_trace(gold, trace).score < 1.0

    result = CliRunner().invoke(
        main, ["eval", str(contract), str(trace), "-o", str(tmp_path / "o.json")]
    )
    assert result.exit_code == 0, result.output
    assert json.loads((tmp_path / "o.json").read_text("utf-8"))["summary"]["score"] == 1.0

    # Record once (graded against the gold file), re-score with the contract.
    assert regrade(trace, gold=contract).result.score == pytest.approx(1.0)


def test_the_schema_file_describes_the_keys() -> None:
    schema = json.loads(CONTRACT_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert set(schema["properties"]) == {
        "contract_version", "description", "required", "alternatives", "optional", "forbidden",
        "weights", "min_score",
    }  # fmt: skip


def test_optional_calls_stay_out_of_fix_lists_and_json_reports(tmp_path: Path) -> None:
    from toolscore.diff import build_eval_fix_list
    from toolscore.reports import generate_json_report

    contract = {
        "required": [{"tool": "search", "args": {"q": {"$regex": "cat"}}}],
        "optional": [{"tool": "list"}],
    }
    result = evaluate_contract(contract, [SEARCH, {"tool": "list"}])
    assert [c.tool for c in result.scored_calls] == ["search"]
    assert build_eval_fix_list(result.gold_calls, result.scored_calls) == []
    report = json.loads(generate_json_report(result, tmp_path / "r.json").read_text("utf-8"))
    assert "$regex" in report["gold_calls"][0]["args"]["q"]  # a matcher, written as its repr
