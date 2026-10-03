"""`toolscore mcp record`: a transparent stdio proxy that records tool calls (1.10).

The tests put the recorder between a real MCP client (``MCPStdioClient``) and the
fake MCP server, exactly as an IDE or agent framework would be wired.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from toolscore import evaluate
from toolscore.core import load_trace
from toolscore.mcp import MCPStdioClient

FIXTURE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mcp_server.py"


def _recorder(output: Path, *server_flags: str) -> list[str]:
    server = shlex.join([sys.executable, str(FIXTURE_SERVER), *server_flags])
    return [
        sys.executable,
        "-c",
        "from toolscore.cli import main; main()",
        "mcp",
        "record",
        server,
        "-o",
        str(output),
    ]


def test_client_sees_the_server_unchanged_through_the_recorder(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    with MCPStdioClient(_recorder(out, "--resources"), timeout=20.0) as client:
        assert client.server_info == {"name": "fake-mcp", "version": "0.1.0"}
        assert {t.name for t in client.list_tools()} >= {"add", "flaky", "read_note"}
        assert client.call_tool("add", {"a": 2, "b": 3}).text == "5"
        assert client.call_tool("flaky", {}).is_error is True
        note = client.call_tool("read_note", {}).text

    assert "[resource file:///notes.md]" in note


def test_recorded_trace_scores_with_results_errors_and_durations(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    with MCPStdioClient(_recorder(out, "--resources"), timeout=20.0) as client:
        client.list_tools()
        client.call_tool("add", {"a": 2, "b": 3})
        client.call_tool("flaky", {})
        client.call_tool("flaky", {})
        client.call_tool("read_note", {})

    calls = load_trace(out, format="mcp")

    assert [(c.tool, c.args, c.is_error) for c in calls] == [
        ("add", {"a": 2, "b": 3}, False),
        ("flaky", {}, True),
        ("flaky", {}, True),
        ("read_note", {}, False),
    ]
    assert calls[0].result == "5"
    assert calls[3].result.endswith("# Notes\nStatus: draft\n")
    assert all(c.duration is not None and c.duration >= 0 for c in calls)

    as_dicts = [
        {"tool": c.tool, "args": c.args, "result": c.result, "is_error": c.is_error} for c in calls
    ]
    efficiency = evaluate(expected=[{"tool": "add"}], actual=as_dicts).metrics["efficiency_metrics"]
    assert efficiency["error_count"] == 2
    assert efficiency["retry_after_error_count"] == 1


def test_only_tool_calls_are_recorded(tmp_path: Path) -> None:
    """initialize, notifications and tools/list must not become phantom tool calls."""
    out = tmp_path / "trace.json"
    with MCPStdioClient(_recorder(out), timeout=20.0) as client:
        client.list_tools()
        client.call_tool("add", {"a": 1, "b": 1})

    record = json.loads(out.read_text())
    methods = [m.get("method") for m in record["messages"] if "method" in m]

    assert methods == ["tools/call"]
    assert record["format"] == "mcp"
    assert len(load_trace(out, format="mcp")) == 1


def test_recorded_file_is_auto_detected_as_mcp(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    with MCPStdioClient(_recorder(out), timeout=20.0) as client:
        client.call_tool("add", {"a": 1, "b": 2})

    calls = load_trace(out)  # format="auto"

    assert [(c.tool, c.result) for c in calls] == [("add", "3")]


def test_plain_json_rpc_log_list_is_auto_detected_as_mcp(tmp_path: Path) -> None:
    """A raw MCP log is a list of JSON-RPC messages; it used to load as zero calls."""
    log = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "add", "arguments": {"a": 1}},
        },
        {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "1"}]}},
    ]
    path = tmp_path / "log.json"
    path.write_text(json.dumps(log))

    calls = load_trace(path)

    assert [(c.tool, c.result) for c in calls] == [("add", "1")]


def test_openai_messages_are_still_detected_as_openai(tmp_path: Path) -> None:
    trace = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "search", "arguments": "{}"},
                    }
                ],
            }
        ]
    }
    path = tmp_path / "openai.json"
    path.write_text(json.dumps(trace))

    assert [c.tool for c in load_trace(path)] == ["search"]


def test_argv_form_keeps_arguments_with_spaces(tmp_path: Path) -> None:
    """MCP client configs pass the server command as an args array; keep it verbatim."""
    spaced = tmp_path / "my servers"
    spaced.mkdir()
    server = spaced / "fake server.py"
    server.write_text(FIXTURE_SERVER.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "trace.json"
    recorder = [
        sys.executable,
        "-c",
        "from toolscore.cli import main; main()",
        "mcp",
        "record",
        "-o",
        str(out),
        "--",
        sys.executable,
        str(server),
    ]

    with MCPStdioClient(recorder, timeout=20.0) as client:
        assert client.call_tool("add", {"a": 1, "b": 2}).text == "3"

    assert json.loads(out.read_text())["server_command"] == [sys.executable, str(server)]
