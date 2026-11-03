"""toolscore lint-config: instruction files and MCP host configs against real tools (1.11)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from click.testing import CliRunner

from toolscore.cli import main
from toolscore.config_lint import CONFIG_RULES, discover_files, lint_config

if TYPE_CHECKING:
    import pytest

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "lint_config"


def _repo(tmp_path: Path, claude_md: str, mcp: dict[str, object] | None = None) -> Path:
    (tmp_path / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    if mcp is not None:
        (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": mcp}), encoding="utf-8")
    return tmp_path


_NOTES = {"notes": {"command": sys.executable, "args": ["-m", "toolscore.mcp.sample_server"]}}


def _rules(report: object) -> list[str]:
    return [i.rule for i in report.issues]  # type: ignore[attr-defined]


def test_discovers_instruction_files_and_host_configs(tmp_path: Path) -> None:
    files = [
        "CLAUDE.md", "AGENTS.md", "pkg/CLAUDE.local.md", ".claude/skills/a/SKILL.md",
        "plugins/p/skills/b/SKILL.md", ".cursor/rules/style.mdc", ".cursorrules",
        ".github/copilot-instructions.md", ".github/instructions/py.instructions.md",
        ".mcp.json", ".cursor/mcp.json", ".vscode/mcp.json", "claude_desktop_config.json",
        "README.md", "node_modules/x/CLAUDE.md", ".venv/lib/AGENTS.md", "docs/mcp.json",
    ]  # fmt: skip
    for name in files:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if name.endswith(".json") else "# x\n", encoding="utf-8")
    instructions, configs = discover_files([tmp_path])
    rel = sorted(p.relative_to(tmp_path).as_posix() for p in instructions)
    assert rel == sorted(files[:9])
    assert sorted(p.relative_to(tmp_path).as_posix() for p in configs) == sorted(files[9:13])
    # an explicitly named Markdown file is always read
    assert discover_files([tmp_path / "README.md"])[0] == [tmp_path / "README.md"]


def test_example_finds_every_rule() -> None:
    report = lint_config([EXAMPLE], snapshots=[("notes", EXAMPLE / "notes.snapshot.json")])
    assert sorted(set(_rules(report))) == sorted(CONFIG_RULES)
    by_line = {(Path(i.path).name, i.line): i for i in report.issues}
    assert "purge_all" in by_line[("CLAUDE.md", 7)].message
    assert "readOnlyHint: true" in by_line[("CLAUDE.md", 6)].message
    assert "'jira'" in by_line[("CLAUDE.md", 8)].message
    assert "did you mean 'delete_note'" in by_line[("SKILL.md", 9)].message
    assert "destructiveHint" in by_line[("SKILL.md", 10)].message
    sse = next(i for i in report.issues if i.rule == "config-server-invalid")
    assert "SSE" in sse.message and sse.line is None
    # Built-in tools and prose never count, and known tools pass
    assert not any(("CLAUDE.md", n) in by_line for n in (3, 5, 9))
    assert report.errors == 3 and report.warnings == 3


def test_without_an_inventory_the_tool_rules_are_skipped_not_passed(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "Use `mcp__notes__purge_all` to clean up.\n", _NOTES)
    report = lint_config([repo])
    assert report.issues == []
    assert set(report.skipped_rules) == {"config-unknown-tool", "config-annotation-contradiction"}


def test_connect_lists_tools_from_the_configured_servers(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        "Use `mcp__notes__purge_all` to clean up.\nUse mcp__notes__list_notes to list notes.\n",
        _NOTES,
    )
    report = lint_config([repo], connect=True)
    assert _rules(report) == ["config-unknown-tool"]
    assert len(report.inventory["notes"]) == 5
    assert report.skipped_rules == {}


def test_foreign_servers_and_unset_env_are_not_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TS_UNSET_TOKEN", raising=False)
    repo = _repo(
        tmp_path,
        "Search with mcp__plugin_github_github__search_code or mcp__claude_ai_Gmail__search.\n",
        {
            "remote": {
                "url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer ${TS_UNSET_TOKEN}"},
            }
        },
    )
    report = lint_config([repo])
    assert report.issues == []
    assert "remote" in report.servers


def test_unknown_server_needs_a_config_to_compare_with(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "Use mcp__jira__create_issue to file bugs.\n")
    assert lint_config([repo]).issues == []


def test_quoted_names_far_from_any_tool_are_left_alone(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "Run the `format_code` tool before committing.\n", _NOTES)
    report = lint_config([repo], snapshots=[("notes", EXAMPLE / "notes.snapshot.json")])
    assert report.issues == []


def test_unreadable_host_config_is_an_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "# nothing\n")
    (repo / ".mcp.json").write_text("{not json", encoding="utf-8")
    report = lint_config([repo])
    assert _rules(report) == ["config-server-invalid"]


def test_cli_exit_codes_and_json(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "lint-config",
            str(EXAMPLE),
            "--snapshot",
            f"notes={EXAMPLE / 'notes.snapshot.json'}",
            "--json",
            str(out),
        ],
    )
    assert result.exit_code == 1, result.output
    assert "config-unknown-tool" in result.output and "3 error(s), 3 warning(s)" in result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"] == {"errors": 3, "warnings": 3}
    assert data["servers"]["notes"]["tools"][0] == "create_note"

    result = runner.invoke(
        main,
        [
            "lint-config",
            str(EXAMPLE),
            "--pin",
            str(EXAMPLE / "notes.snapshot.json"),
            "--fail-on",
            "never",
        ],
    )
    assert result.exit_code == 0
    # bound by the server's own name ("notes-server"), so mcp__notes__ tools are not checked
    assert "purge_all" not in result.output

    (tmp_path / "clean").mkdir()
    clean = _repo(tmp_path / "clean", "Use Bash to run tests.\n")
    result = runner.invoke(main, ["lint-config", str(clean), "--fail-on", "warning"])
    assert result.exit_code == 0 and "0 error(s), 0 warning(s)" in result.output
