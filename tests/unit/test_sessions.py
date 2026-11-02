"""Coding-agent sessions: Claude Code transcripts and Codex CLI rollouts (1.11).

All sessions here are synthetic, written in the line formats documented in
:mod:`toolscore.adapters.sessions`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from toolscore.adapters.sessions import (
    ClaudeCodeSessionAdapter,
    CodexSessionAdapter,
    looks_like_claude_code,
    looks_like_codex,
    shell_exit_error,
)
from toolscore.cli import main
from toolscore.core import adapter_for, load_trace, read_trace_data
from toolscore.sessions import export_session, find_session_files, parse_since, summarize_session
from toolscore.transcript import load_transcript

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "coding_sessions"
# Built so no secret scanner flags this file: the token only exists at run time.
FAKE_TOKEN = "ghp_" + "A1b2C3d4" * 4 + "Zz9Y"


def _cc(kind: str, content: Any, **extra: Any) -> dict[str, Any]:
    line = {
        "type": kind,
        "sessionId": "s-1",
        "uuid": f"u-{len(json.dumps(content))}",
        "cwd": "/work/app",
        "timestamp": "2026-11-01T10:00:00.000Z",
        "isSidechain": False,
        "message": {"role": kind, "content": content},
    }
    line.update(extra)
    return line


def _claude_session() -> list[dict[str, Any]]:
    return [
        {"type": "summary", "summary": "Run tests", "leafUuid": "x"},
        _cc("user", "Run the tests."),
        _cc("user", "<command-name>/clear</command-name>", isMeta=True),
        _cc(
            "assistant",
            [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest"}}],
        ),
        _cc(
            "user",
            [{"type": "tool_result", "tool_use_id": "t1", "content": "1 failed", "is_error": True}],
        ),
        _cc(
            "assistant",
            [{"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "a.py"}}],
            isSidechain=True,
        ),
        _cc(
            "user", [{"type": "tool_result", "tool_use_id": "t2", "content": "x"}], isSidechain=True
        ),
        _cc("assistant", [{"type": "text", "text": "All tests pass."}]),
    ]


def _codex(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"timestamp": "2026-11-01T10:00:00.000Z", "type": kind, "payload": payload}


def _codex_rollout() -> list[dict[str, Any]]:
    return [
        _codex(
            "session_meta", {"id": "r-1", "timestamp": "2026-11-01T10:00:00Z", "cwd": "/work/cli"}
        ),
        _codex("turn_context", {"cwd": "/work/cli", "model": "gpt-6-luna"}),
        _codex(
            "response_item",
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "lint"}],
            },
        ),
        _codex(
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "arguments": '{"cmd": "ruff check ."}',
                "call_id": "c1",
            },
        ),
        _codex("event_msg", {"type": "exec_command_end", "call_id": "c1"}),
        _codex(
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "c1",
                "output": "Process exited with code 1\nOutput:\nF401",
            },
        ),
        _codex(
            "response_item",
            {
                "type": "local_shell_call",
                "call_id": "c2",
                "status": "completed",
                "action": {"type": "exec", "command": ["bash", "-lc", "ls"]},
            },
        ),
        _codex(
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "c2",
                "output": "Exit code: 0\nOutput:\na.py",
            },
        ),
        _codex(
            "response_item",
            {
                "type": "custom_tool_call",
                "name": "apply_patch",
                "input": "*** Begin Patch",
                "call_id": "c3",
            },
        ),
        _codex(
            "response_item",
            {"type": "custom_tool_call_output", "call_id": "c3", "output": "Success."},
        ),
        _codex(
            "response_item",
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Lint is clean."}],
            },
        ),
    ]


def _write_jsonl(path: Path, lines: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return path


def test_jsonl_files_load_line_by_line_and_skip_bad_lines(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text('{"a": 1}\n\nnot json\n{"b": 2', encoding="utf-8")
    assert read_trace_data(path) == [{"a": 1}]
    bad = tmp_path / "bad.json"
    bad.write_text("nothing here", encoding="utf-8")
    with pytest.raises(ValueError, match="neither JSON nor JSON Lines"):
        read_trace_data(bad)


def test_claude_code_main_thread_calls_results_and_final_answer(tmp_path: Path) -> None:
    lines = _claude_session()
    assert looks_like_claude_code(lines)
    assert not looks_like_codex(lines)
    assert isinstance(adapter_for(lines), ClaudeCodeSessionAdapter)
    calls = ClaudeCodeSessionAdapter().parse(lines)
    assert [c.tool for c in calls] == ["Bash"]
    assert calls[0].is_error and calls[0].metadata["error"] == "1 failed"
    assert [c.tool for c in ClaudeCodeSessionAdapter(sidechains=True).parse(lines)] == [
        "Bash",
        "Read",
    ]

    transcript = load_transcript(_write_jsonl(tmp_path / "s.jsonl", lines))
    assert transcript.final_answer == "All tests pass."
    assert transcript.final_source == "Claude Code session"


def test_codex_calls_outputs_shell_failures_and_final_answer(tmp_path: Path) -> None:
    lines = _codex_rollout()
    assert looks_like_codex(lines)
    assert isinstance(adapter_for(lines), CodexSessionAdapter)
    calls = CodexSessionAdapter().parse(lines)
    assert [c.tool for c in calls] == ["exec_command", "local_shell", "apply_patch"]
    assert calls[0].args == {"cmd": "ruff check ."}
    assert calls[0].is_error and "exit code 1" in calls[0].metadata["error"]
    assert calls[1].args["command"] == ["bash", "-lc", "ls"] and not calls[1].is_error
    assert calls[2].result == "Success." and not calls[2].is_error

    path = _write_jsonl(tmp_path / "rollout-1.jsonl", lines)
    assert [c.tool for c in load_trace(path)] == ["exec_command", "local_shell", "apply_patch"]
    transcript = load_transcript(path)
    assert transcript.final_answer == "Lint is clean."
    assert transcript.final_source == "Codex session"


@pytest.mark.parametrize(
    ("output", "failed"),
    [
        ("Process exited with code 2\nOutput:\nboom", True),
        ("Exit code: 0\nWall time: 0.1 seconds\nOutput:\nok", False),
        (
            json.dumps({"output": "nope", "metadata": {"exit_code": 1, "duration_seconds": 0.2}}),
            True,
        ),
        (json.dumps({"output": "fine", "metadata": {"exit_code": 0}}), False),
        ([{"type": "input_text", "text": "Process exited with code 127"}], True),
        ("the docs say: Exit code: 1 means failure", False),
        (None, False),
    ],
)
def test_shell_exit_error(output: Any, failed: bool) -> None:
    assert (shell_exit_error(output) is not None) is failed


def test_session_detection_leaves_other_jsonl_and_chat_formats_alone() -> None:
    chat = [
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "1", "name": "x", "input": {}}],
        }
    ]
    assert not looks_like_claude_code(chat)
    assert not looks_like_codex(chat)
    assert not looks_like_codex([_codex("session_meta", {"id": "r"})])  # no response items


def test_honesty_and_eval_read_session_files_directly() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["honesty", str(EXAMPLES / "claude-code-session.jsonl")])
    assert result.exit_code == 0, result.output
    assert "claimed-success" in result.output
    assert "no later call to it succeeded" in " ".join(result.output.split())
    result = runner.invoke(
        main, ["honesty", str(EXAMPLES / "codex-rollout.jsonl"), "--fail-on-findings"]
    )
    assert result.exit_code == 1
    assert "exec_command failed" in result.output

    gold = EXAMPLES / "gold.json"
    result = runner.invoke(main, ["eval", str(gold), str(EXAMPLES / "codex-rollout.jsonl")])
    assert result.exit_code in (0, 1), result.output
    assert "exec_command" in result.output


def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    claude = _write_jsonl(
        tmp_path / ".claude" / "projects" / "-work-app" / "s-1.jsonl", _claude_session()
    )
    codex = _write_jsonl(
        tmp_path
        / ".codex"
        / "sessions"
        / "2026"
        / "11"
        / "01"
        / "rollout-2026-11-01T10-00-00-r-1.jsonl",
        _codex_rollout(),
    )
    return claude, codex


def test_find_and_summarize_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude, codex = _home(tmp_path, monkeypatch)
    found = {p: a for a, p in find_session_files()}
    assert found == {claude: "claude-code", codex: "codex"}
    assert [p for _, p in find_session_files(agent="codex")] == [codex]
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert find_session_files(since=future) == []

    summary = summarize_session(claude, agent="claude-code")
    assert (summary.agent, summary.session_id, summary.cwd) == ("claude-code", "s-1", "/work/app")
    assert (summary.calls, summary.failed, summary.flagged) == (1, 1, True)
    assert summary.findings["done-after-error"] == 1
    codex_summary = summarize_session(codex)
    assert (codex_summary.agent, codex_summary.session_id) == ("codex", "r-1")
    assert codex_summary.flagged is True  # "Lint is clean." after a failed ruff check


def test_config_dir_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "nowhere"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cc"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "cx"))
    a = _write_jsonl(tmp_path / "cc" / "projects" / "p" / "a.jsonl", _claude_session())
    b = _write_jsonl(tmp_path / "cx" / "sessions" / "rollout-b.jsonl", _codex_rollout())
    assert {p for _, p in find_session_files()} == {a, b}


def test_sessions_list_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    claude, _ = _home(tmp_path, monkeypatch)
    out = tmp_path / "out.json"
    result = CliRunner().invoke(main, ["sessions", "list", "--json", str(out)])
    assert result.exit_code == 0, result.output
    assert (
        "FLAGGED" in result.output and "claude-code" in result.output and "codex" in result.output
    )
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert {r["agent"] for r in rows} == {"claude-code", "codex"}

    result = CliRunner().invoke(
        main, ["sessions", "list", "--agent", "codex", "--project", "nomatch"]
    )
    assert result.exit_code == 0 and "No sessions found" in result.output
    result = CliRunner().invoke(main, ["sessions", "list", "--since", "yesterday-ish"])
    assert result.exit_code == 2

    other = tmp_path / "elsewhere"
    _write_jsonl(other / "x.jsonl", _claude_session())
    (other / "notes.jsonl").write_text('{"hello": 1}\n', encoding="utf-8")
    result = CliRunner().invoke(main, ["sessions", "list", "--root", str(other)])
    assert (
        result.exit_code == 0 and "x.jsonl" in result.output and "notes.jsonl" not in result.output
    )
    assert claude.read_text(encoding="utf-8")  # never modified or removed


def test_parse_since() -> None:
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    assert parse_since("1d", now) == now - timedelta(days=1)
    assert parse_since("30m", now) == now - timedelta(minutes=30)
    assert parse_since("2026-11-01", now) == datetime(2026, 11, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        parse_since("soon", now)


def test_export_redacts_credentials_and_round_trips(tmp_path: Path) -> None:
    lines = _claude_session()
    lines.insert(
        3,
        _cc(
            "assistant",
            [
                {
                    "type": "tool_use",
                    "id": "t0",
                    "name": "Bash",
                    "input": {"command": f"export GH={FAKE_TOKEN}"},
                }
            ],
        ),
    )
    session = _write_jsonl(tmp_path / "s.jsonl", lines)
    before = session.read_text(encoding="utf-8")
    out = tmp_path / "trace.json"
    result = CliRunner().invoke(main, ["sessions", "export", str(session), "-o", str(out)])
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert FAKE_TOKEN not in text and "REDACTED" in text
    assert session.read_text(encoding="utf-8") == before
    trace = json.loads(text)
    assert trace["final_answer"] == "All tests pass."
    assert [c.tool for c in load_trace(out)] == ["Bash", "Bash"]
    assert load_trace(out)[1].is_error

    long = export_session(session, tmp_path / "short.json", max_result_chars=3)
    assert long["calls"][0]["args"]["command"].startswith("export GH=[REDACTED")
