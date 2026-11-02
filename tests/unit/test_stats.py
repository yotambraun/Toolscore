"""Light statistics over repeated runs, selection and pre-declared rules (1.11)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from toolscore.cli import main
from toolscore.stats import (
    Objective,
    Run,
    compare_runs,
    evaluate_protocol,
    fisher_exact,
    load_runs,
    pareto_front,
    pass_hat_k,
    run_from_row,
    runs_from_traces,
    select_variant,
    wilson_interval,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_wilson_interval_matches_the_formula() -> None:
    low, high = wilson_interval(7, 10)
    assert low == pytest.approx(0.3968, abs=1e-4) and high == pytest.approx(0.8922, abs=1e-4)
    assert wilson_interval(0, 0) == (0.0, 1.0)
    assert wilson_interval(10, 10)[1] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        wilson_interval(11, 10)


def test_fisher_exact_two_sided() -> None:
    # Reference values from scipy.stats.fisher_exact.
    assert fisher_exact(1, 9, 11, 3) == pytest.approx(0.0027594, rel=1e-4)
    assert fisher_exact(3, 1, 1, 3) == pytest.approx(0.4857143, rel=1e-6)
    assert fisher_exact(5, 5, 5, 5) == pytest.approx(1.0)
    assert fisher_exact(0, 0, 0, 0) == 1.0


def test_pass_hat_k_is_the_unbiased_estimator() -> None:
    assert pass_hat_k(3, 5, 2) == pytest.approx(3 / 10)
    assert pass_hat_k(5, 5, 3) == 1.0
    assert pass_hat_k(0, 4, 1) == 0.0
    assert pass_hat_k(2, 2, 3) is None
    with pytest.raises(ValueError):
        pass_hat_k(1, 1, 0)


def _runs(variant: str, passes: int, n: int, task: str = "t", **extra: object) -> list[Run]:
    return [
        Run(variant, task, "pass" if i < passes else "fail", **extra)  # type: ignore[arg-type]
        for i in range(n)
    ]


def test_complete_populations_keep_errors_in_n() -> None:
    runs = [*_runs("a", 6, 8), Run("a", "t", "error"), Run("a", "t", "unknown")]
    stats = compare_runs(runs).variants[0]
    assert stats.n == 10 and stats.counts == {"pass": 6, "fail": 2, "error": 1, "unknown": 1}
    assert stats.pass_rate == pytest.approx(0.6)
    assert compare_runs(runs).notes[0].startswith("Errored runs")


def test_small_or_overlapping_samples_are_not_distinguishable() -> None:
    small = compare_runs(_runs("a", 2, 5) + _runs("b", 5, 5))
    assert not small.pairs[0].distinguishable and "fewer than 10" in small.pairs[0].verdict
    overlap = compare_runs(_runs("a", 7, 10) + _runs("b", 9, 10))
    assert not overlap.pairs[0].distinguishable and "overlap" in overlap.pairs[0].verdict
    clear = compare_runs(_runs("a", 2, 30) + _runs("b", 28, 30))
    assert clear.pairs[0].distinguishable and clear.pairs[0].verdict.startswith("b has")


def test_pass_hat_k_per_task_and_short_tasks() -> None:
    runs = _runs("a", 3, 5, task="x") + _runs("a", 2, 2, task="y") + _runs("a", 1, 1, task="z")
    stats = compare_runs(runs, k=2).variants[0]
    assert stats.pass_hat_k == pytest.approx((0.3 + 1.0) / 2)
    assert stats.tasks == 3 and stats.tasks_short == 1


def test_costs_are_unknown_not_zero() -> None:
    runs = [Run("a", "t", "pass", cost=0.02), Run("a", "t", "pass"), *_runs("b", 1, 2)]
    by_name = compare_runs(runs).by_name()
    assert by_name["a"].cost == pytest.approx(0.02) and by_name["a"].cost_known == 1
    assert by_name["b"].cost is None


def test_rows_from_the_harness_and_exports() -> None:
    harness = run_from_row({"arm_id": "a", "task_id": "t", "outcome": "pass", "cost_usd": 0.1})
    assert (harness.variant, harness.outcome, harness.cost) == ("a", "pass", 0.1)
    exported = run_from_row({"variant": "b", "task": "t", "passed": False, "cost": {"usd": None}})
    assert (exported.variant, exported.outcome, exported.cost) == ("b", "fail", None)
    errored = run_from_row({"model": "m", "status": "error"})
    assert errored.outcome == "error"
    assert run_from_row({"arm": "x", "variant": "y"}, variant_key="arm").variant == "x"
    with pytest.raises(ValueError):
        run_from_row({"task_id": "t"})


def test_selection_policies_and_the_pareto_front() -> None:
    runs = (
        _runs("cheap", 7, 10, cost=0.01)
        + _runs("strong", 9, 10, cost=0.10)
        + _runs("worse", 6, 10, cost=0.20)
    )
    comparison = compare_runs(runs)
    objectives = ["pass_rate:max", "cost:min"]
    front = pareto_front(comparison.variants, [Objective.parse(o) for o in objectives])
    assert sorted(front) == ["cheap", "strong"]
    lex = select_variant(comparison, "lexicographic", objectives)
    assert lex.chosen == "strong" and lex.pareto_front == front
    by_cost = select_variant(comparison, "lexicographic", ["cost:min", "pass_rate"])
    assert by_cost.chosen == "cheap"
    weighted = select_variant(comparison, "weighted", objectives, {"cost": 3.0})
    assert weighted.chosen == "cheap" and set(weighted.scores) == {"cheap", "strong", "worse"}
    pareto = select_variant(comparison, "pareto", objectives)
    assert pareto.chosen == "strong" and "Pareto front" in pareto.reason
    with pytest.raises(ValueError):
        select_variant(comparison, "random")
    with pytest.raises(ValueError):
        Objective.parse("vibes:max")


def test_unknown_values_rank_worst() -> None:
    comparison = compare_runs(_runs("a", 9, 10) + _runs("b", 9, 10, cost=0.5))
    selection = select_variant(comparison, "lexicographic", ["pass_rate", "cost"])
    assert selection.chosen == "b" and selection.unknown == {"a": ["cost"]}


def test_protocol_rules_are_tri_state() -> None:
    comparison = compare_runs(_runs("base", 4, 20, cost=0.01) + _runs("cand", 18, 20, cost=0.02))
    protocol = {
        "protocol_version": 1,
        "title": "cand beats base",
        "baseline": "base",
        "candidate": "cand",
        "min_runs": 20,
        "rules": [
            {"id": "better", "metric": "pass_rate", "expect": "candidate_better"},
            {"id": "cost-cap", "metric": "cost", "max": 0.05},
            {"id": "latency", "metric": "latency", "max": 1.0},
        ],
    }
    result = evaluate_protocol(protocol, comparison)
    assert [r.status for r in result.rules] == ["pass", "pass", "unknown"]
    assert result.decision == "undecided" and len(result.protocol_sha256) == 64

    protocol["rules"] = [*protocol["rules"][:2], {"metric": "cost", "expect": "not_worse"}]
    rejected = evaluate_protocol(protocol, comparison)
    assert rejected.decision == "reject" and rejected.rules[2].status == "fail"

    protocol["min_runs"] = 30
    assert {r.status for r in evaluate_protocol(protocol, comparison).rules} == {"unknown"}
    for bad in ({"baseline": "nope", "candidate": "cand"}, {"surprise": 1}):
        with pytest.raises(ValueError):
            evaluate_protocol(bad, comparison)


def _write_runs(path: Path) -> None:
    rows = [
        {"arm_id": arm, "task_id": f"t{i % 3}", "outcome": "pass" if i < passes else "fail",
         "cost_usd": cost, "duration_s": 1.5}
        for arm, passes, cost in (("A", 6, 0.002), ("B", 19, 0.004))
        for i in range(20)
    ]  # fmt: skip
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_load_runs_reports_bad_lines(tmp_path: Path) -> None:
    good = tmp_path / "runs.jsonl"
    _write_runs(good)
    assert len(load_runs([good])) == 40
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"arm_id": "a"}\nnot json\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad.jsonl:2"):
        load_runs([bad])


def test_cli_compare_runs_select_and_protocol(tmp_path: Path) -> None:
    runs = tmp_path / "runs.jsonl"
    _write_runs(runs)
    protocol = tmp_path / "protocol.json"
    protocol.write_text(
        json.dumps(
            {
                "baseline": "A",
                "candidate": "B",
                "rules": [{"id": "better", "metric": "pass_rate", "expect": "candidate_better"}],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "stats.json"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "compare",
            "--runs",
            str(runs),
            "--k",
            "2",
            "--protocol",
            str(protocol),
            "--json",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(out.read_text(encoding="utf-8"))
    assert [v["n"] for v in report["variants"]] == [20, 20]
    assert report["pairs"][0]["distinguishable"] is True
    assert report["protocol"]["decision"] == "adopt"
    assert "Agent Eval Flow" in result.output

    chosen = runner.invoke(
        main,
        ["select", "--runs", str(runs), "--policy", "pareto", "--objective", "cost:min",
         "--objective", "pass_rate", "--json", str(tmp_path / "sel.json")],
    )  # fmt: skip
    assert chosen.exit_code == 0, chosen.output
    assert json.loads((tmp_path / "sel.json").read_text("utf-8"))["pareto_front"] == ["A", "B"]

    assert runner.invoke(main, ["compare", "--variant", "bad"]).exit_code == 2


def test_trace_directories(tmp_path: Path) -> None:
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps([{"tool": "search", "args": {"q": "x"}}]), encoding="utf-8")
    for variant, args in (("good", {"q": "x"}), ("bad", {"q": "y"})):
        directory = tmp_path / variant
        directory.mkdir()
        for i in range(3):
            (directory / f"search-{i}.json").write_text(
                json.dumps([{"tool": "search", "args": args, "result": "ok"}]), encoding="utf-8"
            )
        (directory / "broken-0.json").write_text("{not json", encoding="utf-8")
    runs = runs_from_traces("good", tmp_path / "good", gold)
    assert [r.outcome for r in runs] == ["error", "pass", "pass", "pass"]
    assert {r.task for r in runs} == {"broken", "search"}

    result = CliRunner().invoke(
        main,
        ["compare", str(gold), "--variant", f"good={tmp_path / 'good'}",
         "--variant", f"bad={tmp_path / 'bad'}", "--min-n", "2"],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "Runs per variant" in result.output
