"""toolscore doctor: preflight checks before any paid call (1.11)."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

from click.testing import CliRunner

from toolscore.cli import main
from toolscore.doctor import doctor_report, run_doctor, worst_status
from toolscore.mcp.config import MCPServerSpec

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

SAMPLE = [sys.executable, "-m", "toolscore.mcp.sample_server"]


def _spec(tmp_path: Path, **overrides: Any) -> Path:
    data: dict[str, Any] = {
        "name": "s",
        "server": {"command": SAMPLE},
        "verify": {"server_name": "notes-server"},
        "arms": [{"id": "luna", "provider": "openai", "model": "gpt-6-luna"}],
        "budget": {"max_usd": 5.0},
        "limits": {"max_turns": 4},
        "tasks": [{"id": "t", "prompt": "Save a note."}],
    }
    data.update(overrides)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _by_name(checks: list[Any]) -> dict[str, Any]:
    return {c.name: c for c in checks}


def test_keys_are_reported_by_name_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key-123")
    checks = _by_name(run_doctor(spec_path=_spec(tmp_path)))
    assert checks["package openai"].status in ("pass", "fail")  # depends on the environment
    key = checks["key OPENAI_API_KEY"]
    assert key.status == "pass" and "sk-test" not in key.detail
    assert checks["server"].status == "pass" and "tool(s)" in checks["server"].detail
    assert checks["build"].status == "pass"
    assert checks["price luna"].status == "pass"
    assert checks["budget"].status == "pass"

    monkeypatch.delenv("OPENAI_API_KEY")
    missing = _by_name(run_doctor(spec_path=_spec(tmp_path), start_server=False))
    assert missing["key OPENAI_API_KEY"].status == "fail"
    assert "server" not in missing


def test_unknown_price_budget_and_build(tmp_path: Path) -> None:
    spec = _spec(
        tmp_path,
        arms=[{"id": "x", "provider": "anthropic", "model": "claude-mystery-9"}],
        verify={"server_version": "9.9"},
    )
    checks = _by_name(run_doctor(spec_path=spec))
    assert checks["price x"].status == "fail"
    assert checks["budget"].status == "unknown"
    assert checks["build"].status == "fail"
    allowed = _by_name(run_doctor(spec_path=spec, allow_unknown_price=True, start_server=False))
    assert allowed["price x"].status == "warn"

    tight = _spec(tmp_path, budget={"max_usd": 0.000001})
    assert _by_name(run_doctor(spec_path=tight, start_server=False))["budget"].status == "warn"


def test_version_command_and_bad_files(tmp_path: Path) -> None:
    spec = _spec(
        tmp_path,
        verify={"command": [sys.executable, "-c", "print('2.0.1')"], "expect": "^2\\.0\\.1$"},
    )
    assert (
        _by_name(run_doctor(spec_path=spec, start_server=False))["version command"].status == "pass"
    )

    bad = tmp_path / "bad.json"
    bad.write_text('{"tasks": []}', encoding="utf-8")
    assert _by_name(run_doctor(spec_path=bad))["spec"].status == "fail"

    contract = tmp_path / "c.json"
    contract.write_text(json.dumps({"required": [{"tool": "x"}]}), encoding="utf-8")
    assert _by_name(run_doctor(contract_path=contract))["contract"].status == "pass"
    contract.write_text(json.dumps({"required": [{"nope": 1}]}), encoding="utf-8")
    assert _by_name(run_doctor(contract_path=contract))["contract"].status == "fail"
    gold = tmp_path / "g.json"
    gold.write_text(json.dumps([{"tool": "x"}]), encoding="utf-8")
    assert "gold file" in _by_name(run_doctor(contract_path=gold))["contract"].detail


def test_a_server_that_does_not_start(tmp_path: Path) -> None:
    del tmp_path
    dead = MCPServerSpec(name="dead", command=[sys.executable, "-c", "pass"])
    checks = _by_name(run_doctor(server=dead))
    assert checks["server"].status == "fail"
    report = doctor_report(list(checks.values()))
    assert report["ok"] is False and report["worst"] == "fail"
    assert worst_status([]) == "pass"


def test_cli_doctor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import toolscore.doctor

    monkeypatch.setattr(toolscore.doctor, "_installed", lambda module: True)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key-123")
    out = tmp_path / "doctor.json"
    result = CliRunner().invoke(
        main, ["doctor", "--spec", str(_spec(tmp_path)), "--json", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert "Preflight passed" in result.output and "sk-test" not in result.output
    assert json.loads(out.read_text(encoding="utf-8"))["ok"] is True
    failed = CliRunner().invoke(main, ["doctor", "--key", "TOOLSCORE_SURELY_UNSET_VAR"])
    assert failed.exit_code == 1 and "not set" in failed.output
    served = CliRunner().invoke(main, ["doctor", "--server", " ".join(SAMPLE)])
    assert served.exit_code == 0, served.output
