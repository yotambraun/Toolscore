"""Effect probes: did the tool really do what it reported (1.11)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from toolscore.cli import main
from toolscore.mcp import MCPStdioClient, MCPToolDef
from toolscore.mcp.probes import (
    PROBE_RULES,
    Agreement,
    BoundRelation,
    CallSpec,
    ProbeConfig,
    ProbeResult,
    RoundTripPair,
    _reports_skip,
    builtin_relations,
    is_read_tool,
    load_probe_config,
    run_probes,
    write_basis,
)
from toolscore.mcp.scorecard import MCPScorecard, score_server, scorecard_to_json

PROBE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "probe_server.py"


def _sample(*bugs: str) -> list[str]:
    command = [sys.executable, "-m", "toolscore.mcp.sample_server"]
    for bug in bugs:
        command += ["--bug", bug]
    return command


def _probe_server(*bugs: str) -> list[str]:
    command = [sys.executable, str(PROBE_SERVER)]
    for bug in bugs:
        command += ["--bug", bug]
    return command


def _run(
    command: list[str], config: ProbeConfig | None = None, allow_writes: bool = True
) -> dict[tuple[str, str], ProbeResult]:
    with MCPStdioClient(command, timeout=20.0, protocol="legacy") as client:
        results = run_probes(client, client.list_tools(), config=config, allow_writes=allow_writes)
    return {
        (r.probe, r.tool) if not r.check else (r.probe, f"{r.tool}:{r.check}"): r for r in results
    }


# -- round trips on the sample server -------------------------------------------


def test_correct_sample_server_passes_the_round_trip() -> None:
    results = _run(_sample())
    trip = results[("round-trip", "create_note")]
    assert trip.status == "pass" and trip.confidence == "high"
    assert "search_notes" in trip.basis
    assert results[("bound", "list_notes:builtin-limit")].status == "pass"
    assert all(r.status != "fail" for r in results.values())


def test_silent_skip_is_reported_success_state_unchanged() -> None:
    trip = _run(_sample("silent-skip"))[("round-trip", "create_note")]
    assert (trip.status, trip.rule, trip.severity) == ("fail", "probe-silent-noop", "error")
    assert "state unchanged" in trip.message
    # The evidence holds every call the probe made, writes and reads.
    assert [e["tool"] for e in trip.evidence].count("create_note") == 2


def test_lost_records_after_a_write_are_reported() -> None:
    trip = _run(_sample("lose-on-write"))[("round-trip", "create_note")]
    assert (trip.status, trip.rule, trip.confidence) == ("fail", "probe-data-lost", "high")


def test_ignored_limit_is_a_medium_confidence_warning() -> None:
    bound = _run(_sample("limit-ignored"))[("bound", "list_notes:builtin-limit")]
    assert (bound.rule, bound.confidence, bound.severity) == (
        "probe-bound-exceeded",
        "medium",
        "warning",
    )
    assert not bound.graded


def test_write_probes_are_skipped_without_allow_writes() -> None:
    results = _run(_sample("silent-skip"), allow_writes=False)
    assert results[("round-trip", "create_note")].status == "skipped"
    assert all(e["tool"] != "create_note" for r in results.values() for e in r.evidence)


# -- bounds, agreements and idempotency on the probe test server ------------------


def test_head_zero_returning_the_whole_file_is_caught() -> None:
    builtin = _run(_probe_server("head-zero"))[("bound", "read_text:builtin-head")]
    assert (builtin.rule, builtin.confidence) == ("probe-bound-exceeded", "medium")
    assert "head=0 returned 5 lines" in builtin.message

    declared = ProbeConfig(
        relations=[BoundRelation("read_text", "head", [0, 2], "prefix", {"path": "/f"}, "lines")]
    )
    result = _run(_probe_server("head-zero"), declared)[("bound", "read_text:head")]
    assert (result.rule, result.severity) == ("probe-bound-exceeded", "error")


def test_tail_off_by_one_is_bound_short() -> None:
    config = ProbeConfig(
        builtins=False,
        relations=[BoundRelation("read_text", "tail", [2], "suffix", {"path": "/f"}, "lines")],
    )
    result = _run(_probe_server("tail-short"), config)[("bound", "read_text:tail")]
    assert result.rule == "probe-bound-short"
    assert "tail=2 returned 1 lines; 2 expected" in result.message


def test_correct_head_and_tail_pass() -> None:
    config = ProbeConfig(
        relations=[
            BoundRelation("read_text", "head", [0, 1, 3], "prefix", {"path": "/f"}, "lines"),
        ]
    )
    results = _run(_probe_server(), config)
    assert results[("bound", "read_text:head")].status == "pass"
    assert results[("bound", "read_text:builtin-tail")].status == "pass"


def test_declared_agreement_and_idempotency() -> None:
    config = ProbeConfig(
        builtins=False,
        agreements=[
            Agreement(
                left=CallSpec("search_items", {"query": "a"}),
                right=CallSpec("list_items", {}),
                id="search within list",
            )
        ],
        idempotent=[CallSpec("roll", {}), CallSpec("list_items", {"limit": 2})],
    )
    good = _run(_probe_server(), config, allow_writes=False)
    assert good[("agreement", "search_items:search within list")].status == "pass"
    assert good[("idempotent", "list_items")].status == "pass"
    assert good[("idempotent", "roll")].rule == "probe-not-idempotent"

    bad = _run(_probe_server("search-extra"), config, allow_writes=False)
    disagree = bad[("agreement", "search_items:search within list")]
    assert (disagree.rule, disagree.severity) == ("probe-paths-disagree", "error")
    assert "delta" in disagree.message


def test_a_reported_skip_is_honest_and_a_silent_one_is_not() -> None:
    honest = _run(_probe_server())[("round-trip", "add_entry")]
    assert honest.status == "pass"
    assert "reported as skipped" in honest.message

    silent = _run(_probe_server("skip-silent"))[("round-trip", "add_entry")]
    assert silent.rule == "probe-silent-noop"


def test_unseen_write_without_a_related_reader_is_only_a_warning() -> None:
    trip = _run(_probe_server())[("round-trip", "create_record")]
    assert (trip.rule, trip.confidence, trip.severity) == (
        "probe-write-not-observable",
        "low",
        "warning",
    )


def test_a_declared_pair_makes_an_unseen_write_an_error() -> None:
    config = ProbeConfig(
        builtins=False, pairs=[RoundTripPair(write="create_record", read="get_entries")]
    )
    trip = _run(_probe_server(), config)[("round-trip", "create_record")]
    assert (trip.rule, trip.severity) == ("probe-write-not-observable", "error")
    assert trip.basis == "declared pair create_record -> get_entries"


# -- heuristics ---------------------------------------------------------------


def _def(name: str, **annotations: bool) -> MCPToolDef:
    return MCPToolDef(name=name, description="", input_schema={}, annotations=annotations)


def test_write_and_read_heuristics_report_their_basis() -> None:
    assert write_basis(_def("create_entities")) == "its name says it stores ('create')"
    assert write_basis(_def("add_observations")) is not None
    assert write_basis(_def("delete_note")) is None
    assert write_basis(_def("send_email")) is None  # not a store verb: never probed by default
    assert write_basis(_def("get_settings")) is None
    assert write_basis(_def("save_note", readOnlyHint=True)) is None
    assert write_basis(_def("bookmark", readOnlyHint=False, destructiveHint=False)) == (
        "annotations readOnlyHint: false, destructiveHint: false"
    )
    assert is_read_tool(_def("search_nodes"))
    assert is_read_tool(_def("fetch", readOnlyHint=True))
    assert not is_read_tool(_def("list_and_purge", readOnlyHint=False))


def test_builtin_relations_are_conservative() -> None:
    tool = MCPToolDef(
        name="read_file",
        description="",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "head": {"type": "integer"},
                "limit": {"type": "integer"},
                "max_length": {"type": "integer"},
                "count": {"type": "integer"},
            },
            "required": ["path"],
        },
    )
    relations = {r.param: r for r in builtin_relations(tool, ProbeConfig().args)}
    assert set(relations) == {"head", "limit"}
    assert relations["head"].values == [0, 1, 2]
    assert relations["limit"].values == [1, 2]  # 0 can mean "no limit"
    write = MCPToolDef(name="write_file", description="", input_schema=tool.input_schema)
    assert builtin_relations(write, ProbeConfig().args) == []


def test_skip_reports_in_text_and_json() -> None:
    assert _reports_skip("Entity 'x' already exists")
    assert _reports_skip('{"created": [], "skipped": ["x"]}')
    assert not _reports_skip('{"created": [], "skipped": []}')
    assert not _reports_skip('[{"name": "x"}]')
    assert not _reports_skip("ok")


def test_every_rule_has_a_description() -> None:
    assert set(PROBE_RULES) == {
        "probe-write-not-observable",
        "probe-silent-noop",
        "probe-data-lost",
        "probe-bound-exceeded",
        "probe-bound-short",
        "probe-slice-mismatch",
        "probe-paths-disagree",
        "probe-not-idempotent",
    }


# -- configuration files ---------------------------------------------------------


def test_probe_config_from_json_and_yaml(tmp_path: Path) -> None:
    data = {
        "args": {"*": {"path": "/f"}},
        "pairs": [{"write": "create_record", "read": "get_entries", "read_args": {}}],
        "relations": [{"tool": "read_text", "param": "head", "values": [0, 1]}],
        "agreements": [
            {"left": {"tool": "search_items", "args": {"query": "a"}}, "right": {"tool": "x"}}
        ],
        "idempotent": [{"tool": "roll"}],
    }
    path = tmp_path / "probes.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    config = load_probe_config(path)
    assert config.pairs[0].read == "get_entries"
    assert config.relations[0].expect == "exact"
    assert config.args.shared == {"path": "/f"}

    pytest.importorskip("yaml")
    yaml_path = tmp_path / "probes.yaml"
    yaml_path.write_text(
        "relations:\n  - tool: read_text\n    param: tail\n    values: [1]\n    expect: suffix\n",
        encoding="utf-8",
    )
    assert load_probe_config(yaml_path).relations[0].expect == "suffix"


@pytest.mark.parametrize(
    "data",
    [
        {"nope": []},
        {"relations": [{"tool": "t", "param": "p", "values": [-1]}]},
        {"relations": [{"tool": "t", "param": "p", "values": [1], "expect": "maybe"}]},
        {"pairs": [{"write": "w"}]},
        {"agreements": [{"left": {"tool": "a"}}]},
        {"pairs": ["not a mapping"]},
    ],
)
def test_bad_probe_configs_are_rejected(data: object) -> None:
    with pytest.raises(ValueError):
        ProbeConfig.from_mapping(data)


# -- scorecard and CLI ------------------------------------------------------------


def test_passing_probes_leave_the_score_unchanged() -> None:
    with MCPStdioClient(_sample(), timeout=20.0) as client:
        plain = score_server(client)
    with MCPStdioClient(_sample(), timeout=20.0) as client:
        probed = score_server(client, probes=True, allow_writes=True)
    assert probed.effect_rate == 1.0
    assert probed.score == pytest.approx(plain.score)
    assert plain.effect_label == ""


def test_a_lying_tool_costs_like_a_tool_that_fails_its_happy_paths() -> None:
    with MCPStdioClient(_sample("silent-skip"), timeout=20.0) as client:
        card = score_server(client, probes=True, allow_writes=True)
    base = MCPScorecard(
        server_info=card.server_info, tools=card.tools, results=card.results, lint=card.lint
    )
    assert card.probe_failed_tools == {"create_note"}
    assert card.score == pytest.approx(base.score - 0.6 / len(card.tools))
    report = scorecard_to_json(card)
    assert report["scores"]["effect_rate"] == 0.0
    assert any(p["rule"] == "probe-silent-noop" for p in report["probes"])
    assert report["fixes"][0]["tool"] == "create_note"


def test_cli_probes_and_ci_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    command = " ".join(_sample("silent-skip"))
    out = tmp_path / "card.md"
    result = CliRunner().invoke(
        main,
        ["mcp", "test", command, "--probes", "--allow-writes", "--report", "md", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    markdown = out.read_text(encoding="utf-8")
    assert "## Effect probes" in markdown
    assert "`probe-silent-noop`" in markdown

    gated = CliRunner().invoke(main, ["mcp", "test", command, "--probes", "--allow-writes", "--ci"])
    assert gated.exit_code == 1
    assert "Effect probes" in gated.output

    skipped = CliRunner().invoke(main, ["mcp", "test", command, "--probes"])
    assert "add --allow-writes" in skipped.output


def test_cli_probe_config(tmp_path: Path) -> None:
    config = tmp_path / "probes.json"
    config.write_text(
        json.dumps(
            {
                "builtins": False,
                "relations": [
                    {
                        "tool": "read_text",
                        "param": "head",
                        "values": [0],
                        "expect": "prefix",
                        "args": {"path": "/f"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    command = " ".join(_probe_server("head-zero"))
    out = tmp_path / "card.json"
    result = CliRunner().invoke(
        main,
        ["mcp", "test", command, "--probe-config", str(config), "--report", "json", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    probes = json.loads(out.read_text(encoding="utf-8"))["probes"]
    assert [(p["tool"], p["rule"], p["severity"]) for p in probes if p["status"] != "skipped"] == [
        ("read_text", "probe-bound-exceeded", "error")
    ]

    bad = tmp_path / "bad.json"
    bad.write_text('{"relations": [{"tool": "x"}]}', encoding="utf-8")
    rejected = CliRunner().invoke(main, ["mcp", "test", command, "--probe-config", str(bad)])
    assert rejected.exit_code == 2
