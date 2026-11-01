"""Known-good argument values (``--arg``, ``--args-file``) and the sample server's state (1.11)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from toolscore.cli import main
from toolscore.mcp import MCPStdioClient, MCPToolDef, generate_scenarios
from toolscore.mcp.fixtures import ArgumentFixtures, load_fixtures, parse_arg
from toolscore.mcp.sample_server import NotesStore

FIXTURE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mcp_server.py"


def _tool(name: str, **properties: dict[str, object]) -> MCPToolDef:
    return MCPToolDef(
        name=name,
        description="A tool for testing argument fixtures.",
        input_schema={"type": "object", "properties": properties, "required": list(properties)},
    )


def test_parse_arg_reads_json_values_and_tool_scopes() -> None:
    assert parse_arg("path=/tmp/x") == (None, "path", "/tmp/x")
    assert parse_arg("limit=5") == (None, "limit", 5)
    assert parse_arg("read_file:path=/a=b") == ("read_file", "path", "/a=b")
    assert parse_arg("id=007") == (None, "id", "007")
    assert parse_arg('tags=["a"]') == (None, "tags", ["a"])
    for bad in ("novalue", "=x", ":path=x", "tool:=x"):
        with pytest.raises(ValueError):
            parse_arg(bad)


def test_shared_values_apply_only_where_declared_and_per_tool_always() -> None:
    fixtures = ArgumentFixtures.from_options(["path=/sandbox/a.txt", "search:query=hello"])
    read = _tool("read_file", path={"type": "string"})
    search = _tool("search", query={"type": "string"})

    assert fixtures.for_tool(read) == {"path": "/sandbox/a.txt"}
    assert fixtures.for_tool(search) == {"query": "hello"}
    # A number given for a string parameter is passed as text.
    assert ArgumentFixtures.from_options(["query=123"]).for_tool(search) == {"query": "123"}


def test_fixtures_replace_generated_values_in_happy_paths_only() -> None:
    tool = _tool("read_file", path={"type": "string"})
    fixtures = ArgumentFixtures(shared={"path": "/sandbox/a.txt"})

    plain = generate_scenarios([tool])
    fixed = generate_scenarios([tool], fixtures=fixtures)

    assert [s.kind for s in plain] == [s.kind for s in fixed]
    assert all(s.arguments == {"path": "/sandbox/a.txt"} for s in fixed if s.kind == "happy")
    edge = [s.arguments for s in fixed if s.kind == "edge"]
    assert edge == [s.arguments for s in plain if s.kind == "edge"]


def test_fixture_files_are_json_or_yaml(tmp_path: Path) -> None:
    data = {"*": {"path": "/sandbox"}, "list_directory": {"depth": 1}}
    as_json = tmp_path / "args.json"
    as_json.write_text(json.dumps(data), encoding="utf-8")
    assert load_fixtures(as_json) == ArgumentFixtures(
        shared={"path": "/sandbox"}, per_tool={"list_directory": {"depth": 1}}
    )

    pytest.importorskip("yaml")
    as_yaml = tmp_path / "args.yaml"
    as_yaml.write_text("'*':\n  path: /sandbox\nlist_directory:\n  depth: 1\n", encoding="utf-8")
    assert load_fixtures(as_yaml) == load_fixtures(as_json)

    bad = tmp_path / "bad.json"
    bad.write_text('{"*": [1]}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_fixtures(bad)


def test_mcp_test_uses_arg_values(tmp_path: Path) -> None:
    """The fake server's echo tool reports what it received, so the report shows the value."""
    out = tmp_path / "report.json"
    command = f"{sys.executable} {FIXTURE_SERVER}"
    result = CliRunner().invoke(
        main,
        ["mcp", "test", command, "--arg", "add:a=40", "--report", "json", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(out.read_text(encoding="utf-8"))
    happy_add = [r for r in report["results"] if r["tool"] == "add" and r["kind"] == "happy"]
    assert happy_add and all(r["arguments"]["a"] == 40 for r in happy_add)


def test_mcp_test_rejects_malformed_arg() -> None:
    result = CliRunner().invoke(main, ["mcp", "test", "python x.py", "--arg", "oops"])
    assert result.exit_code == 2
    assert "NAME=VALUE" in result.output


# -- the sample server's state and bug modes -----------------------------------


def test_sample_store_is_correct_by_default() -> None:
    store = NotesStore()
    store.create("a", "one")
    store.create("a", "two")
    store.create("b", "three")
    assert store.titles(None) == ["b", "a", "groceries", "ideas"]
    assert store.titles(2) == ["b", "a"]
    assert store.search("two") == [{"title": "a", "body": "two"}]


def test_sample_store_bug_modes() -> None:
    skip = NotesStore({"silent-skip"})
    skip.create("a", "one")
    skip.create("a", "two")
    assert skip.search("one") == [{"title": "a", "body": "one"}]
    assert skip.search("two") == []

    lose = NotesStore({"lose-on-write"})
    lose.create("a", "one")
    lose.create("b", "two")
    assert lose.titles(None) == ["b"]

    ignored = NotesStore({"limit-ignored"})
    assert ignored.titles(1) == ["groceries", "ideas"]

    with pytest.raises(ValueError):
        NotesStore({"no-such-bug"})


def test_sample_server_keeps_notes_between_calls() -> None:
    command = [sys.executable, "-m", "toolscore.mcp.sample_server", "--bug", "silent-skip"]
    with MCPStdioClient(command, timeout=20.0) as client:
        assert client.call_tool("create_note", {"title": "t", "body": "first"}).text == "ok"
        assert client.call_tool("create_note", {"title": "t", "body": "second"}).text == "ok"
        found = json.loads(client.call_tool("search_notes", {"query": "t"}).text)
        listed = client.call_tool("list_notes", {"limit": 1}).structured_content
    assert {"title": "t", "body": "first"} in found["notes"]
    assert listed == {"notes": ["t"], "count": 1}
