"""The pre-commit hooks manifest (.pre-commit-hooks.yaml) points at working commands."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from toolscore.cli import main

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
HOOKS = {h["id"]: h for h in yaml.safe_load((ROOT / ".pre-commit-hooks.yaml").read_text())}


def test_every_hook_is_complete_and_runs_a_toolscore_command() -> None:
    assert set(HOOKS) == {"toolscore-lint-config", "toolscore-verify-pin", "toolscore-mcp-lint"}
    for hook in HOOKS.values():
        assert {"id", "name", "entry", "language", "description"} <= set(hook)
        assert hook["language"] == "python" and hook["pass_filenames"] is False
        program, *command = shlex.split(hook["entry"])
        assert program == "toolscore"
        result = CliRunner().invoke(main, [*command, "--help"])
        assert result.exit_code == 0, hook["id"]


@pytest.mark.parametrize(
    ("path", "hook", "matches"),
    [
        ("CLAUDE.md", "toolscore-lint-config", True),
        ("docs/AGENTS.md", "toolscore-lint-config", True),
        (".claude/skills/tidy/SKILL.md", "toolscore-lint-config", True),
        (".cursor/rules/tools.mdc", "toolscore-lint-config", True),
        (".github/copilot-instructions.md", "toolscore-lint-config", True),
        (".vscode/mcp.json", "toolscore-lint-config", True),
        ("pins/notes.lock.json", "toolscore-lint-config", True),
        ("README.md", "toolscore-lint-config", False),
        ("src/app.py", "toolscore-lint-config", False),
        ("pins/notes.lock.json", "toolscore-verify-pin", True),
        ("notes.snapshot.json", "toolscore-verify-pin", True),
        ("package.json", "toolscore-verify-pin", False),
    ],
)
def test_file_patterns(path: str, hook: str, matches: bool) -> None:
    assert bool(re.search(HOOKS[hook]["files"], path)) is matches


def test_the_documented_hook_arguments_work(monkeypatch: Any) -> None:
    examples = ROOT / "examples"
    pin = CliRunner().invoke(
        main,
        [
            "mcp", "verify-pin", str(examples / "pinning" / "notes-snapshot.json"),
            "--lock", str(examples / "pinning" / "notes.lock.json"),
        ],
    )  # fmt: skip
    assert pin.exit_code == 0, pin.output
    monkeypatch.chdir(examples / "lint_config")
    lint = CliRunner().invoke(main, ["lint-config", "--snapshot", "notes=notes.snapshot.json"])
    assert lint.exit_code == 1 and "config-unknown-tool" in lint.output
