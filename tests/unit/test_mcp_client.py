"""Tests for the zero-dependency MCP stdio client and config loader.

These tests spawn the real fake MCP server fixture as a subprocess (no network,
fast) and exercise the full handshake, tool listing, tool calls, error paths,
timeouts, crash diagnostics, and config parsing.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from toolscore.mcp import (
    MCPError,
    MCPServerSpec,
    MCPStdioClient,
    MCPTimeoutError,
    MCPToolDef,
    load_mcp_config,
)

FIXTURE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mcp_server.py"


def _server_command(*extra: str) -> list[str]:
    """Build the command vector that launches the fake MCP server.

    Args:
        *extra: Additional argv flags to append (e.g. ``"--sleep", "2"``).

    Returns:
        The command vector using the current Python interpreter.
    """
    return [sys.executable, str(FIXTURE_SERVER), *extra]


@pytest.fixture
def client() -> Iterator[MCPStdioClient]:
    """Provide a started client wired to the fake server, closed on teardown."""
    c = MCPStdioClient(_server_command(), timeout=10.0)
    c.start()
    try:
        yield c
    finally:
        c.close()


# -- handshake ------------------------------------------------------------


def test_start_returns_server_info(client: MCPStdioClient) -> None:
    assert client.server_info == {"name": "fake-mcp", "version": "0.1.0"}
    assert client.protocol_version == "2025-06-18"


def test_start_twice_raises() -> None:
    c = MCPStdioClient(_server_command())
    c.start()
    try:
        with pytest.raises(MCPError, match="already started"):
            c.start()
    finally:
        c.close()


# -- list_tools -----------------------------------------------------------


def test_list_tools_returns_three_defs(client: MCPStdioClient) -> None:
    tools = client.list_tools()
    assert [t.name for t in tools] == ["add", "flaky", "bad_schema"]
    assert all(isinstance(t, MCPToolDef) for t in tools)


def test_list_tools_add_schema(client: MCPStdioClient) -> None:
    add = next(t for t in client.list_tools() if t.name == "add")
    assert add.description == "Add two numbers and return the sum."
    assert add.input_schema["type"] == "object"
    assert set(add.input_schema["properties"]) == {"a", "b"}
    assert add.input_schema["required"] == ["a", "b"]


def test_list_tools_bad_schema_is_tolerated(client: MCPStdioClient) -> None:
    bad = next(t for t in client.list_tools() if t.name == "bad_schema")
    assert bad.description == ""
    assert "type" not in bad.input_schema
    assert "properties" not in bad.input_schema


# -- call_tool ------------------------------------------------------------


def test_call_tool_add(client: MCPStdioClient) -> None:
    result = client.call_tool("add", {"a": 2, "b": 3})
    assert result.is_error is False
    assert result.content == [{"type": "text", "text": "5"}]
    assert result.duration > 0
    assert result.raw["result"]["content"] == result.content


def test_call_tool_flaky_is_error(client: MCPStdioClient) -> None:
    result = client.call_tool("flaky", {"x": "anything"})
    assert result.is_error is True
    assert result.duration > 0


def test_call_unknown_tool_is_jsonrpc_error(client: MCPStdioClient) -> None:
    result = client.call_tool("does_not_exist", {})
    assert result.is_error is True
    assert "error" in result.raw
    assert result.raw["error"]["code"] == -32602
    # On the error path, content carries the JSON-RPC error object.
    assert result.content["code"] == -32602


# -- timeout --------------------------------------------------------------


def test_call_tool_timeout() -> None:
    c = MCPStdioClient(_server_command("--sleep", "2"), timeout=0.5)
    c.start()
    try:
        start = time.monotonic()
        with pytest.raises(MCPTimeoutError, match="Timed out"):
            c.call_tool("add", {"a": 1, "b": 1})
        # Should give up around the timeout, well before the 2s server sleep.
        assert time.monotonic() - start < 1.5
    finally:
        c.close()


# -- crash diagnostics ----------------------------------------------------


def test_process_crash_raises_with_diagnostics() -> None:
    c = MCPStdioClient(_server_command(), timeout=5.0)
    c.start()
    try:
        assert c._process is not None
        c._process.kill()
        c._process.wait(timeout=5.0)
        # Give the reader thread a moment to observe EOF.
        time.sleep(0.2)
        with pytest.raises(MCPError) as exc_info:
            c.call_tool("add", {"a": 1, "b": 1})
        message = str(exc_info.value)
        assert "exited" in message or "returncode" in message
    finally:
        c.close()


# -- context manager ------------------------------------------------------


def test_context_manager_closes_process() -> None:
    with MCPStdioClient(_server_command(), timeout=5.0) as c:
        process = c._process
        assert process is not None
        assert process.poll() is None
        assert c.call_tool("add", {"a": 1, "b": 1}).content == [{"type": "text", "text": "2"}]
    # After exiting the context, the process must have terminated.
    assert process.poll() is not None


def test_close_is_idempotent() -> None:
    c = MCPStdioClient(_server_command(), timeout=5.0)
    c.start()
    c.close()
    # Second close must not raise.
    c.close()


# -- config loader --------------------------------------------------------


def _write_config(tmp_path: Path, data: dict[str, object]) -> Path:
    """Write a JSON config file under ``tmp_path``.

    Args:
        tmp_path: The pytest temporary directory.
        data: The configuration payload to serialize.

    Returns:
        The path to the written config file.
    """
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps(data), encoding="utf-8")
    return config_path


def test_load_config_single_server(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        {
            "mcpServers": {
                "fs": {
                    "command": "npx",
                    "args": ["-y", "server-filesystem", "/tmp"],
                    "env": {"DEBUG": "1"},
                }
            }
        },
    )
    spec = load_mcp_config(config_path)
    assert isinstance(spec, MCPServerSpec)
    assert spec.name == "fs"
    assert spec.command == ["npx", "-y", "server-filesystem", "/tmp"]
    assert spec.env == {"DEBUG": "1"}


def test_load_config_named_server(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        {
            "mcpServers": {
                "a": {"command": "cmd-a"},
                "b": {"command": "cmd-b", "args": ["x"]},
            }
        },
    )
    spec = load_mcp_config(config_path, server="b")
    assert spec.name == "b"
    assert spec.command == ["cmd-b", "x"]
    assert spec.env == {}


def test_load_config_ambiguous_raises(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        {"mcpServers": {"a": {"command": "cmd-a"}, "b": {"command": "cmd-b"}}},
    )
    with pytest.raises(ValueError, match="Multiple MCP servers") as exc_info:
        load_mcp_config(config_path)
    assert "a" in str(exc_info.value) and "b" in str(exc_info.value)


def test_load_config_unknown_server_raises(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"mcpServers": {"a": {"command": "cmd-a"}}})
    with pytest.raises(ValueError, match="not found"):
        load_mcp_config(config_path, server="missing")


def test_load_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        load_mcp_config(tmp_path / "nope.json")


def test_load_config_missing_key_raises(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"somethingElse": {}})
    with pytest.raises(ValueError, match="mcpServers"):
        load_mcp_config(config_path)


def test_load_config_invalid_json_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_mcp_config(config_path)


def test_load_config_missing_command_raises(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"mcpServers": {"a": {"args": ["x"]}}})
    with pytest.raises(ValueError, match="command"):
        load_mcp_config(config_path)
