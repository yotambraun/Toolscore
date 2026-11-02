"""The agent harness, with fake provider clients: no model is ever called (1.11)."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from click.testing import CliRunner

from toolscore.cli import main
from toolscore.mcp import MCPStdioClient, MCPToolDef
from toolscore.mcp.agent import (
    AnthropicMessagesProvider,
    ArmSpec,
    Budget,
    BuildMismatchError,
    GuardCall,
    Limits,
    OpenAIResponsesProvider,
    Price,
    ScriptedProvider,
    TaskSpec,
    UnknownPriceError,
    allow,
    check_build,
    completed_cells,
    deny,
    estimate_study_cost,
    map_tools,
    preflight_prices,
    rules_guard,
    run_agent,
    run_study,
    spec_from_mapping,
)

if TYPE_CHECKING:
    from pathlib import Path

SAMPLE = [sys.executable, "-m", "toolscore.mcp.sample_server"]


# -- fake provider clients (shapes of the real SDK responses) --------------------------


class FakeOpenAI:
    """``client.responses.create`` returning queued Responses API outputs."""

    def __init__(self, outputs: list[list[dict[str, Any]]], usage: tuple[int, int] = (100, 20)):
        self.outputs = list(outputs)
        self.requests: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._create)
        self.usage = usage

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(json.loads(json.dumps(kwargs, default=str)))
        output = self.outputs.pop(0)
        return SimpleNamespace(
            output=output,
            usage=SimpleNamespace(input_tokens=self.usage[0], output_tokens=self.usage[1]),
        )


class FakeAnthropic:
    """``client.messages.create`` returning queued Messages content blocks."""

    def __init__(self, contents: list[list[dict[str, Any]]]):
        self.contents = list(contents)
        self.requests: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.requests.append(json.loads(json.dumps(kwargs, default=str)))
        return {"content": self.contents.pop(0), "usage": {"input_tokens": 50, "output_tokens": 10}}


def _fc(name: str, args: dict[str, Any], call_id: str = "call_1") -> dict[str, Any]:
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(args),
    }


def _msg(text: str) -> dict[str, Any]:
    return {"type": "message", "content": [{"type": "output_text", "text": text}]}


# -- tool mapping and guards -------------------------------------------------------------


def test_tools_get_safe_unique_names_and_object_schemas() -> None:
    tools = [
        MCPToolDef("files.read", "Read.", {"properties": {"p": {"type": "string"}}}),
        MCPToolDef("files/read", "Read too.", {}),
        MCPToolDef("x" * 80, "Long.", {"type": "object"}),
    ]
    mapped = map_tools(tools)
    assert [t.name for t in mapped] == ["files_read", "files_read_2", "x" * 64]
    assert [t.mcp_name for t in mapped] == ["files.read", "files/read", "x" * 80]
    assert mapped[0].parameters == {"properties": {"p": {"type": "string"}}, "type": "object"}
    assert mapped[1].parameters == {"type": "object", "properties": {}}
    assert [t.mcp_name for t in map_tools(tools, allow=["files.*"])] == ["files.read"]


def test_declarative_guard() -> None:
    guard = rules_guard(
        [{"tool": "run", "args": {"cmd": {"$regex": "rm -rf"}}, "reason": "destructive"}],
        allow_tools=["run", "list_*"],
    )
    assert guard(GuardCall("run", {"cmd": "ls"})) == allow()
    assert guard(GuardCall("run", {"cmd": "rm -rf /"})) == deny("destructive")
    assert not guard(GuardCall("delete_all", {})).allowed


# -- one run against the sample server ---------------------------------------------------


def test_openai_responses_loop_with_a_denied_call() -> None:
    fake = FakeOpenAI(
        [
            [_fc("delete_note", {"title": "ideas"}, "c1"), _fc("list_notes", {}, "c2")],
            [_msg("I could not delete it; the notes are groceries and ideas.")],
        ]
    )
    provider = OpenAIResponsesProvider(fake, "gpt-6-luna", max_output_tokens=64)
    price = Price(0.10, 0.50, "test")
    with MCPStdioClient(SAMPLE, timeout=20) as client:
        run = run_agent(
            client,
            provider,
            "Delete ideas, then list.",
            system="Be careful.",
            guard=rules_guard([{"tool": "delete_note", "reason": "no deletes"}]),
            price=price,
        )
    assert run.status == "completed" and run.turns == 2
    assert [c.tool for c in run.calls] == ["delete_note", "list_notes"]
    assert run.calls[0].denied and run.calls[0].result is None
    assert run.guard_denials == [
        {"id": "c1", "tool": "delete_note", "args": {"title": "ideas"}, "reason": "no deletes"}
    ]
    assert "groceries" in (run.calls[1].result or "") and run.calls[1].duration is not None
    assert run.final_answer and run.final_answer.startswith("I could not")
    assert run.input_tokens == 200 and run.output_tokens == 40
    assert run.cost_usd == pytest.approx(2 * (100 * 0.10 + 20 * 0.50) / 1e6)
    first, second = fake.requests
    assert first["instructions"] == "Be careful." and first["max_output_tokens"] == 64
    assert {t["name"] for t in first["tools"]} >= {"create_note", "list_notes"}
    outputs = [i for i in second["input"] if i.get("type") == "function_call_output"]
    assert outputs[0]["call_id"] == "c1" and "denied by the harness guard" in outputs[0]["output"]
    assert outputs[1]["call_id"] == "c2"


def test_anthropic_messages_loop() -> None:
    fake = FakeAnthropic(
        [
            [
                {"type": "text", "text": "Saving."},
                {"type": "tool_use", "id": "tu_1", "name": "create_note",
                 "input": {"title": "t", "body": "b"}},
            ],
            [{"type": "text", "text": "Saved note t."}],
        ]
    )  # fmt: skip
    provider = AnthropicMessagesProvider(fake, "claude-haiku-5-5", max_output_tokens=32)
    with MCPStdioClient(SAMPLE, timeout=20) as client:
        run = run_agent(client, provider, "Save a note.", system="sys", price=Price(1, 5, "t"))
    assert run.status == "completed" and run.final_answer == "Saved note t."
    assert run.calls[0].id == "tu_1" and not run.calls[0].is_error
    first, second = fake.requests
    assert first["system"] == "sys" and first["max_tokens"] == 32
    assert first["tools"][0].keys() == {"name", "description", "input_schema"}
    tool_result = second["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "tu_1"
    assert tool_result["is_error"] is False
    assert second["messages"][-2]["role"] == "assistant"


def test_the_budget_is_checked_before_every_model_call() -> None:
    fake = FakeOpenAI([[_fc("list_notes", {})], [_fc("list_notes", {})], [_msg("done")]])
    provider = OpenAIResponsesProvider(fake, "m", max_output_tokens=1000)
    budget = Budget(max_usd=0.0101)
    # Output tokens only: a turn costs 20 * $10/1M = $0.0002; the worst next call $0.01.
    price = Price(0.0, 10.0, "test")
    with MCPStdioClient(SAMPLE, timeout=20) as client:
        run = run_agent(client, provider, "List.", budget=budget, price=price)
    assert run.status == "budget_stopped"
    assert run.turns == 1 and len(fake.requests) == 1  # the second call was never made
    assert budget.spent_usd == pytest.approx(0.0002)


def test_unknown_price_means_unknown_cost() -> None:
    fake = FakeOpenAI([[_msg("hi")]])
    budget = Budget(max_usd=1.0, allow_unknown_price=True)
    with MCPStdioClient(SAMPLE, timeout=20) as client:
        run = run_agent(client, OpenAIResponsesProvider(fake, "m"), "Hi", budget=budget, price=None)
    assert run.cost_usd is None and budget.unknown_cost_turns == 1


def test_limits_and_errors_end_the_run() -> None:
    looping = ScriptedProvider([{"calls": [{"tool": "list_notes"}]}] * 5)
    with MCPStdioClient(SAMPLE, timeout=20) as client:
        turns = run_agent(client, looping, "loop", limits=Limits(max_turns=2, max_calls=10))
        calls = run_agent(
            client,
            ScriptedProvider([{"calls": [{"tool": "list_notes"}] * 3}]),
            "loop",
            limits=Limits(max_turns=5, max_calls=2),
        )
        unknown = run_agent(
            client, ScriptedProvider([{"calls": [{"tool": "nope"}]}, {"text": "x"}]), "?"
        )

        class Broken:
            provider, model, max_output_tokens = "x", "x", 1

            def start(self, *args: Any) -> None:
                raise RuntimeError("provider down")

        broken = run_agent(client, Broken(), "?")  # type: ignore[arg-type]
    assert turns.status == "limit_reached" and turns.turns == 2
    assert calls.status == "limit_reached" and len(calls.calls) == 2
    assert unknown.calls[0].is_error and "unknown tool" in (unknown.calls[0].error or "")
    assert broken.status == "error" and "provider down" in (broken.error or "")


# -- studies ----------------------------------------------------------------------------------


def _spec(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": "t",
        "server": {"command": SAMPLE},
        "provider": "scripted",
        "arms": [{"id": "a"}, {"id": "b"}],
        "repetitions": 2,
        "seed": 3,
        "tasks": [
            {
                "id": "save",
                "prompt": "Save.",
                "expected": [{"tool": "create_note", "args": {"title": {"$regex": "^g"}}}],
                "script": {
                    "a": [{"calls": [{"tool": "create_note", "args": {"title": "g", "body": "x"}}]},
                          {"text": "Saved."}],
                    "b": [{"text": "Saved it."}],
                },
            }
        ],
    }  # fmt: skip
    data.update(overrides)
    return data


def test_spec_validation() -> None:
    spec = spec_from_mapping(_spec())
    assert [a.id for a in spec.arms] == ["a", "b"] and spec.tasks[0].script_for("b")
    assert spec.cells() == spec_from_mapping(_spec()).cells()  # fixed by the seed
    assert spec.cells() != spec_from_mapping(_spec(seed=4)).cells() or len(spec.cells()) < 3
    for bad in (
        _spec(server={}),
        _spec(tasks=[]),
        _spec(arms=[{"id": "a", "provider": "gemini"}]),
        _spec(surprise=1),
        _spec(arms=[{"id": "a"}, {"id": "a"}]),
        _spec(arms=[{"id": "c"}]),  # scripted, but no script for arm c
    ):
        with pytest.raises(ValueError):
            spec_from_mapping(bad)


def test_prices_are_checked_before_anything_runs() -> None:
    spec = spec_from_mapping(
        _spec(arms=[{"id": "x", "provider": "openai", "model": "my-private-model"}])
    )
    with pytest.raises(UnknownPriceError, match="my-private-model"):
        preflight_prices(spec)
    assert preflight_prices(spec, allow_unknown_price=True) == {"x": None}
    priced = spec_from_mapping(
        _spec(arms=[{"id": "x", "provider": "openai", "model": "gpt-6-luna"}])
    )
    price = preflight_prices(priced)["x"]
    assert price is not None and price.input == 0.10
    estimate = estimate_study_cost(priced, {"x": price})
    assert estimate["runs"] == 2 and estimate["total_usd"] > 0


def test_build_verification() -> None:
    ok = check_build({"name": "notes-server", "version": "1.1.0"}, {"server_version": "/^1\\./"})
    assert ok["ok"]
    bad = check_build({"name": "x", "version": "2"}, {"server_name": "notes-server"})
    assert not bad["ok"] and bad["checked"][0]["actual"] == "x"


def test_study_rows_resume_and_outcomes(tmp_path: Path) -> None:
    out = tmp_path / "runs.jsonl"
    spec = spec_from_mapping(_spec(verify={"server_name": "notes-server"}))
    first = run_study(spec, output=out, max_runs=3)
    assert len(first.rows) == 3 and first.stopped == "max_runs (3)"
    second = run_study(spec, output=out)
    assert second.skipped == 3 and len(second.rows) == 1
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert sorted(r["cell_id"] for r in rows) == sorted(c for c in completed_cells(out))
    assert [r["order"] for r in rows] == [1, 2, 3, 4]
    by_arm = {r["arm_id"]: r for r in rows}
    assert by_arm["a"]["outcome"] == "pass" and by_arm["a"]["passed"] is True
    assert by_arm["b"]["outcome"] == "fail"  # claimed to save without calling the tool
    row = by_arm["a"]
    assert row["server"]["name"] == "notes-server" and row["server"]["build_check"]["ok"]
    assert row["server"]["protocol_version"] and row["calls"][0]["tool"] == "create_note"
    assert row["evaluation"]["evidence"]["counts"]["fail"] == 0
    assert row["run_record_version"] == "1" and row["cost_usd"] == 0.0


def test_a_build_mismatch_refuses_the_study(tmp_path: Path) -> None:
    spec = spec_from_mapping(_spec(verify={"server_version": "9.9.9"}))
    with pytest.raises(BuildMismatchError, match=r"9\.9\.9"):
        run_study(spec, output=tmp_path / "r.jsonl")
    command = spec_from_mapping(
        _spec(verify={"command": [sys.executable, "-c", "print('1.0.0')"], "expect": "^2"})
    )
    with pytest.raises(BuildMismatchError, match=r"verify\.command"):
        run_study(command, output=tmp_path / "r.jsonl")
    assert not (tmp_path / "r.jsonl").exists()


def test_a_server_that_does_not_start_is_an_errored_run(tmp_path: Path) -> None:
    spec = spec_from_mapping(
        _spec(server={"command": [sys.executable, "-c", "pass"], "timeout": 2})
    )
    result = run_study(spec, output=tmp_path / "r.jsonl", max_runs=1)
    assert result.rows[0]["outcome"] == "error" and result.rows[0]["status"] == "error"


def test_python_guard_and_run_dir(tmp_path: Path) -> None:
    (tmp_path / "my_guards.py").write_text(
        "from toolscore.mcp.agent import deny\n"
        "def guard(call):\n"
        "    return deny('no writes') if call.tool == 'create_note' else None\n",
        encoding="utf-8",
    )
    data = _spec(guard={"python": "my_guards:guard"}, repetitions=1, arms=[{"id": "a"}])
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(data), encoding="utf-8")
    from toolscore.mcp.agent import load_agent_spec

    result = run_study(load_agent_spec(spec_file), output=tmp_path / "r.jsonl")
    assert result.rows[0]["guard_denials"][0]["reason"] == "no writes"
    assert result.rows[0]["outcome"] == "fail"  # the required create_note never succeeded


def test_cli_agent_run(tmp_path: Path) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_spec()), encoding="utf-8")
    runner = CliRunner()
    dry = runner.invoke(main, ["agent", "run", str(spec_file), "--dry-run"])
    assert dry.exit_code == 0 and "nothing was called" in dry.output
    out = tmp_path / "runs.jsonl"
    result = runner.invoke(main, ["agent", "run", str(spec_file), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert len(out.read_text(encoding="utf-8").splitlines()) == 4
    compared = runner.invoke(main, ["compare", "--runs", str(out)])
    assert compared.exit_code == 0 and "Runs per variant" in compared.output

    unpriced = tmp_path / "unpriced.json"
    unpriced.write_text(
        json.dumps(_spec(arms=[{"id": "x", "provider": "openai", "model": "mystery-1"}])),
        encoding="utf-8",
    )
    refused = runner.invoke(main, ["agent", "run", str(unpriced)])
    assert refused.exit_code == 2 and "mystery-1" in refused.output


def test_default_factory_needs_the_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    from toolscore.mcp import agent as agent_module

    real_import = builtins.__import__

    def no_sdk(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in ("openai", "anthropic"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_sdk)
    monkeypatch.setattr(agent_module.importlib, "import_module", lambda n: no_sdk(n))
    task = TaskSpec("t", "p")
    for provider in ("openai", "anthropic"):
        with pytest.raises(ImportError, match="tool-scorer"):
            agent_module.default_provider_factory(ArmSpec("a", provider, "m"), task)


def test_regrade_saved_runs_without_running(tmp_path: Path) -> None:
    out = tmp_path / "runs.jsonl"
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(_spec()), encoding="utf-8")
    run_study(spec_from_mapping(_spec()), output=out)
    lenient = _spec()
    lenient["tasks"][0]["expected"] = None  # nothing expected: outcome unknown, not pass
    lenient_file = tmp_path / "lenient.json"
    lenient_file.write_text(json.dumps(lenient), encoding="utf-8")
    regraded = tmp_path / "v2.jsonl"
    result = CliRunner().invoke(
        main, ["regrade", str(out), "--spec", str(lenient_file), "-o", str(regraded)]
    )
    assert result.exit_code == 0, result.output
    assert "Nothing was re-run" in result.output
    rows = [json.loads(line) for line in regraded.read_text(encoding="utf-8").splitlines()]
    originals = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["calls"] for r in rows] == [r["calls"] for r in originals]
    assert {r["outcome"] for r in rows if r["arm_id"] == "a"} == {"unknown"}
    assert all(len(r["regraded"]["from_sha256"]) == 64 for r in rows)

    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps([{"tool": "list_notes"}]), encoding="utf-8")
    again = CliRunner().invoke(main, ["regrade", str(out), "--gold", str(gold)])
    assert again.exit_code == 0, again.output
    assert (tmp_path / "runs.regraded.jsonl").is_file()
    assert CliRunner().invoke(main, ["regrade", str(out)]).exit_code == 2
