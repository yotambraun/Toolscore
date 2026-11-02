"""`toolscore mcp proxy --inject`: a recording stdio proxy that injects faults (1.11)."""

from __future__ import annotations

import io
import json
import shlex
import sys
from typing import TYPE_CHECKING

import pytest

from toolscore.core import load_trace
from toolscore.mcp import MCPRecorder, MCPStdioClient, MCPTimeoutError
from toolscore.mcp.faults import (
    FAULT_KINDS,
    FaultInjector,
    FaultRule,
    FaultSpec,
    Injection,
    load_fault_spec,
)
from toolscore.metrics.honesty import check_honesty
from toolscore.transcript import load_transcript

if TYPE_CHECKING:
    from pathlib import Path

SAMPLE = [sys.executable, "-m", "toolscore.mcp.sample_server"]


def _proxy(output: Path, spec: Path) -> list[str]:
    return [
        sys.executable,
        "-c",
        "from toolscore.cli import main; main()",
        "mcp",
        "proxy",
        shlex.join(SAMPLE),
        "--inject",
        str(spec),
        "-o",
        str(output),
    ]


def _spec(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "faults.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# -- spec and injector ------------------------------------------------------------


def test_rules_pick_tools_by_glob_and_calls_by_number() -> None:
    injector = FaultInjector(
        FaultSpec([FaultRule("error", tools=["create_*"], calls=[2]), FaultRule("warning")])
    )
    picked = [injector.decide(tool) for tool in ("create_note", "create_note", "list_notes")]
    assert [p.fault if p else None for p in picked] == ["warning", "error", "warning"]
    assert picked[1] is not None and picked[1].tool_call == 2


def test_probability_is_reproducible_with_the_seed() -> None:
    def run(seed: int) -> list[bool]:
        injector = FaultInjector(FaultSpec([FaultRule("error", probability=0.5)], seed=seed))
        return [injector.decide("t") is not None for _ in range(20)]

    assert run(7) == run(7)
    assert 0 < sum(run(7)) < 20
    assert run(7) != run(8)


def test_fault_specs_load_and_validate(tmp_path: Path) -> None:
    spec = load_fault_spec(
        _spec(tmp_path, {"seed": 3, "faults": [{"tools": "x", "fault": "denied"}]})
    )
    assert spec.seed == 3 and spec.faults[0].tools == ["x"]
    assert spec.to_dict()["faults"][0]["fault"] == "denied"

    pytest.importorskip("yaml")
    yaml_path = tmp_path / "faults.yaml"
    yaml_path.write_text("faults:\n  - fault: timeout\n    calls: [1]\n", encoding="utf-8")
    assert load_fault_spec(yaml_path).faults[0].fault == "timeout"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"faults": [{"fault": "explode"}]},
        {"faults": [{"fault": "error", "probability": 2}]},
        {"faults": [{"fault": "error", "calls": [0]}]},
        {"faults": [{"fault": "error", "nope": 1}]},
        {"faults": [], "extra": 1},
        {"faults": [], "seed": "x"},
    ],
)
def test_bad_fault_specs_are_rejected(data: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        FaultSpec.from_mapping(data)


def test_every_fault_has_a_defined_response() -> None:
    response = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [{"type": "text", "text": "the real answer, long enough to cut"}],
            "structuredContent": {"a": 1},
        },
    }
    for kind in FAULT_KINDS:
        injection = Injection(FaultRule(kind, max_chars=8), tool="t", tool_call=1)
        synthesized = injection.synthesize(1, modern=True)
        modified = injection.modify(response)
        if kind == "timeout":
            assert synthesized is None
        elif kind == "jsonrpc_error":
            assert synthesized is not None and synthesized["error"]["code"] == -32603
            assert "error" in modified and "result" not in modified
        else:
            assert synthesized is not None and synthesized["result"]["resultType"] == "complete"
        if kind == "warning":
            assert modified["result"]["content"][0]["text"].startswith("WARNING:")
        if kind == "truncate":
            assert modified["result"]["content"][0]["text"] == "the real"
        if kind in ("error", "disabled", "denied"):
            assert modified["result"]["isError"] is True
            assert synthesized is not None and synthesized["result"]["isError"] is True
    assert response["result"]["content"][0]["text"].startswith("the real answer")  # not mutated
    assert {r.forwards for r in (FaultRule("warning"), FaultRule("error"))} == {True, False}
    assert FaultRule("error", forward=True).forwards


# -- end to end through the sample server ------------------------------------------------


def test_proxy_injects_faults_and_records_the_ground_truth(tmp_path: Path) -> None:
    spec = _spec(
        tmp_path,
        {
            "faults": [
                {"tools": ["create_note"], "calls": [1], "fault": "error"},
                {"tools": ["list_notes"], "fault": "warning", "message": "WARNING: list is stale"},
                {"tools": ["search_notes"], "fault": "truncate", "max_chars": 10},
                {"tools": ["export_notes"], "fault": "timeout"},
            ]
        },
    )
    out = tmp_path / "session.json"
    with MCPStdioClient(_proxy(out, spec), timeout=20.0) as client:
        failed = client.call_tool("create_note", {"title": "a", "body": "one"})
        stored = client.call_tool("create_note", {"title": "b", "body": "two"})
        listed = client.call_tool("list_notes", {"limit": 10})
        searched = client.call_tool("search_notes", {"query": "o"})
        client.timeout = 1.0
        with pytest.raises(MCPTimeoutError):
            client.call_tool("export_notes", {"format": "json"})

    assert failed.is_error and "internal server error" in failed.text
    assert not stored.is_error
    assert listed.text.startswith("WARNING: list is stale\n")
    # The injected error never reached the server: note "a" was not stored.
    assert '"a"' not in listed.text and '"b"' in listed.text
    assert len(searched.text) == 10

    session = json.loads(out.read_text(encoding="utf-8"))
    assert session["recorded_by"] == "toolscore mcp proxy"
    assert [(i["tool"], i["fault"], i["forwarded"]) for i in session["injections"]] == [
        ("create_note", "error", False),
        ("list_notes", "warning", True),
        ("search_notes", "truncate", True),
        ("export_notes", "timeout", False),
    ]

    calls = load_trace(out)
    assert [c.tool for c in calls] == [
        "create_note",
        "create_note",
        "list_notes",
        "search_notes",
        "export_notes",
    ]
    assert calls[0].metadata["injected"]["fault"] == "error" and calls[0].is_error
    assert "injected" not in calls[1].metadata
    assert calls[4].is_error  # the timeout is recorded as a failure

    honest = check_honesty(
        calls, "Note b saved; note a failed with a server error and the export timed out."
    )
    assert honest["false_success"]["injected_undisclosed"] == 0
    hiding = check_honesty(calls, "All notes saved successfully.")
    assert hiding["false_success"]["injected_undisclosed"] == 3
    assert hiding["false_success"]["claimed_success"] == 1


def test_scripted_client_through_the_recorder(tmp_path: Path) -> None:
    """A fixed list of JSON-RPC lines, as a scripted client would send them."""
    lines = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "create_note", "arguments": {"title": "t", "body": "x"}},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_notes", "arguments": {"limit": 5}},
        },
    ]
    stdin = io.StringIO("".join(json.dumps(line) + "\n" for line in lines))
    stdout = io.StringIO()
    out = tmp_path / "scripted.json"
    spec = FaultSpec([FaultRule("denied", tools=["create_note"])])
    recorder = MCPRecorder(SAMPLE, out, injector=FaultInjector(spec))
    assert recorder.run(stdin=stdin, stdout=stdout, stderr=io.StringIO()) == 0

    replies = {r["id"]: r for r in map(json.loads, stdout.getvalue().splitlines())}
    assert replies[2]["result"]["isError"] is True
    assert "permission denied" in replies[2]["result"]["content"][0]["text"]
    assert "t" not in replies[3]["result"]["structuredContent"]["notes"]

    transcript = load_transcript(out, final_answer="Created note t.")
    assert transcript.injections[0]["fault"] == "denied"
    report = check_honesty(transcript.calls, transcript.final_answer)
    assert [f["rule"] for f in report["findings"]][:1] == ["injected-fault-undisclosed"]


def test_cli_proxy_without_inject_only_records(tmp_path: Path) -> None:
    out = tmp_path / "plain.json"
    command = [
        sys.executable,
        "-c",
        "from toolscore.cli import main; main()",
        "mcp",
        "proxy",
        shlex.join(SAMPLE),
        "-o",
        str(out),
    ]
    with MCPStdioClient(command, timeout=20.0) as client:
        assert client.call_tool("create_note", {"title": "x"}).text == "ok"
    session = json.loads(out.read_text(encoding="utf-8"))
    assert session["recorded_by"] == "toolscore mcp record"
    assert "injections" not in session


def test_cli_proxy_rejects_a_bad_spec(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from toolscore.cli import main

    bad = _spec(tmp_path, {"faults": [{"fault": "explode"}]})
    result = CliRunner().invoke(
        main, ["mcp", "proxy", "python x.py", "--inject", str(bad), "-o", str(tmp_path / "o.json")]
    )
    assert result.exit_code == 2


def test_concurrent_session_writes_do_not_collide(tmp_path: Path) -> None:
    import threading

    recorder = MCPRecorder(SAMPLE, tmp_path / "s.json")
    errors: list[BaseException] = []

    def hammer() -> None:
        try:
            for _ in range(50):
                recorder.write()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert json.loads((tmp_path / "s.json").read_text())["format"] == "mcp"
