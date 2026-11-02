"""Streamable HTTP transport and URL config entries.

Runs :class:`toolscore.mcp.MCPHttpClient` against an in-process HTTP server
(see ``tests/fixtures/http_mcp_server.py``) in both protocol eras, with JSON
and server-sent-event responses, and checks that header values never appear
in errors or reprs.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("httpx")

from tests.fixtures.http_mcp_server import FakeHTTPServer
from toolscore.mcp import (
    MCPError,
    MCPHttpClient,
    MCPHTTPStatusError,
    MCPServerSpec,
    MCPStdioClient,
    load_mcp_config,
    open_client,
)
from toolscore.mcp.client import encode_header_value
from toolscore.mcp.config import expand_env, parse_header

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def modern() -> Iterator[FakeHTTPServer]:
    with FakeHTTPServer(era="modern") as server:
        yield server


def test_modern_http_server(modern: FakeHTTPServer) -> None:
    with MCPHttpClient(modern.url, timeout=10.0) as client:
        assert client.era == "modern"
        assert client.server_info == {"name": "http-modern", "version": "1.0"}
        names = [t.name for t in client.list_tools()]
        assert "echo_region" in names
        assert client.call_tool("add", {"a": 2, "b": 5}).text == "7"
        # The fake rejects a missing or wrong Mcp-Param-Region header with -32020,
        # so a clean answer means the x-mcp-header parameter was mirrored.
        echoed = client.call_tool("echo_region", {"region": "us-west1", "query": "q"})
        assert not echoed.is_error
        assert echoed.text == "us-west1"
    call = modern.requests[-1]["headers"]
    assert call["mcp-method"] == "tools/call"
    assert call["mcp-name"] == "echo_region"
    assert call["mcp-protocol-version"] == "2026-07-28"
    assert "mcp-session-id" not in call


def test_modern_http_server_with_event_stream() -> None:
    with FakeHTTPServer(era="modern", sse=True) as server, MCPHttpClient(server.url) as client:
        assert client.call_tool("add", {"a": 1, "b": 1}).text == "2"
        assert any(m.get("method") == "notifications/progress" for m in client.server_messages)


def test_legacy_http_server_uses_a_session() -> None:
    with FakeHTTPServer(era="legacy") as server:
        with MCPHttpClient(server.url, timeout=10.0) as client:
            assert client.era == "legacy"
            assert client.protocol_version == "2025-11-25"
            assert client.server_instructions == "Legacy over HTTP."
            assert client.call_tool("add", {"a": 3, "b": 4}).text == "7"
        last = server.requests[-1]["headers"]
        assert last["mcp-session-id"] == "session-1"
        assert last["mcp-protocol-version"] == "2025-11-25"
        # The session is ended with DELETE on close.
        assert server.deleted == ["session-1"]


def test_legacy_http_server_with_event_stream() -> None:
    with FakeHTTPServer(era="legacy", sse=True) as server, MCPHttpClient(server.url) as client:
        assert client.era == "legacy"
        assert client.call_tool("add", {"a": 1, "b": 2}).text == "3"


def test_bearer_token_is_sent_and_never_shown() -> None:
    secret = "s3cr3t-token-value"
    with FakeHTTPServer(era="modern", token=secret) as server:
        with MCPHttpClient(server.url, headers={"Authorization": f"Bearer {secret}"}) as client:
            assert client.call_tool("add", {"a": 1, "b": 1}).text == "2"
            assert secret not in repr(client)

        unauthorized = MCPHttpClient(server.url, headers={"Authorization": "Bearer wrong"})
        with pytest.raises(MCPHTTPStatusError) as caught:
            unauthorized.start()
        assert caught.value.status == 401
        assert "authorization" in str(caught.value)
        assert "wrong" not in str(caught.value)


def test_unreachable_server_is_a_clear_error() -> None:
    client = MCPHttpClient("http://127.0.0.1:9/mcp", timeout=2.0)
    with pytest.raises(MCPError, match="failed"):
        client.start()


def test_url_must_be_http() -> None:
    with pytest.raises(ValueError, match="http"):
        MCPHttpClient("ftp://example.com/mcp")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("us-west1", "us-west1"),
        ("Hello, 世界", "=?base64?SGVsbG8sIOS4lueVjA==?="),
        (" padded ", "=?base64?IHBhZGRlZCA=?="),
        ("line1\nline2", "=?base64?bGluZTEKbGluZTI=?="),
        ("=?base64?literal?=", "=?base64?PT9iYXNlNjQ/bGl0ZXJhbD89?="),
    ],
)
def test_header_value_encoding_matches_the_spec_examples(value: str, expected: str) -> None:
    assert encode_header_value(value) == expected


# -- config entries -----------------------------------------------------------


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_vscode_servers_layout_with_http_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TS_TEST_TOKEN", "abc123")
    path = _write(
        tmp_path,
        {
            "servers": {
                "remote": {
                    "type": "http",
                    "url": "https://example.com/mcp",
                    "headers": {"Authorization": "Bearer ${env:TS_TEST_TOKEN}"},
                }
            }
        },
    )
    spec = load_mcp_config(path)
    assert spec.transport == "http"
    assert spec.url == "https://example.com/mcp"
    assert spec.headers == {"Authorization": "Bearer abc123"}
    assert "abc123" not in repr(spec)
    assert isinstance(open_client(spec), MCPHttpClient)


def test_cursor_style_url_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TS_TEST_HOST", "example.org")
    path = _write(tmp_path, {"mcpServers": {"r": {"url": "https://${TS_TEST_HOST}/mcp"}}})
    assert load_mcp_config(path).url == "https://example.org/mcp"


def test_windsurf_server_url_entry(tmp_path: Path) -> None:
    path = _write(tmp_path, {"mcpServers": {"r": {"serverUrl": "https://example.com/mcp"}}})
    assert load_mcp_config(path).url == "https://example.com/mcp"


def test_missing_env_var_names_the_variable_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TS_TEST_MISSING", raising=False)
    path = _write(
        tmp_path,
        {"mcpServers": {"r": {"url": "https://x.dev/mcp", "headers": {"X": "${TS_TEST_MISSING}"}}}},
    )
    with pytest.raises(ValueError, match="TS_TEST_MISSING is not set"):
        load_mcp_config(path)


def test_sse_entries_are_rejected_with_a_reason(tmp_path: Path) -> None:
    path = _write(tmp_path, {"mcpServers": {"old": {"type": "sse", "url": "https://x.dev/sse"}}})
    with pytest.raises(ValueError, match="deprecated"):
        load_mcp_config(path)


def test_http_entry_needs_a_url(tmp_path: Path) -> None:
    path = _write(tmp_path, {"servers": {"r": {"type": "http"}}})
    with pytest.raises(ValueError, match="'url'"):
        load_mcp_config(path)


def test_stdio_spec_opens_a_stdio_client() -> None:
    client = open_client(MCPServerSpec(name="s", command=["python", "server.py"]))
    assert isinstance(client, MCPStdioClient)


def test_parse_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TS_TEST_TOKEN", "abc")
    assert parse_header("Authorization: Bearer ${TS_TEST_TOKEN}") == ("Authorization", "Bearer abc")
    with pytest.raises(ValueError, match="Name: value"):
        parse_header("no-colon-here")


def test_expand_env_leaves_plain_text_alone() -> None:
    assert expand_env("no references") == "no references"


# -- credentials never reach messages or reprs ---------------------------------


def test_safe_url_drops_credentials_query_and_fragment() -> None:
    from toolscore.mcp.client import safe_url

    assert (
        safe_url("https://user:pw@example.com:8443/mcp?token=abc#x")
        == "https://example.com:8443/mcp"
    )


def test_url_secrets_stay_out_of_errors_and_reprs() -> None:
    client = MCPHttpClient("http://user:s3cret@127.0.0.1:9/mcp?token=s3cret", timeout=2.0)
    assert "s3cret" not in repr(client)
    with pytest.raises(MCPError) as caught:
        client.start()
    assert "s3cret" not in str(caught.value)
    spec = MCPServerSpec(
        name="r", command=[], url="https://x.dev/mcp?token=s3cret", env={"K": "s3cret"}
    )
    assert "s3cret" not in repr(spec)


def test_bad_header_option_does_not_echo_its_value() -> None:
    with pytest.raises(ValueError) as caught:
        parse_header("Authorization Bearer sk-live-secret")
    assert "sk-live" not in str(caught.value)


def test_trailing_newline_is_base64_encoded() -> None:
    assert encode_header_value("abc\n") == "=?base64?YWJjCg==?="


def test_http_probe_waits_the_full_timeout_by_default() -> None:
    assert MCPHttpClient("https://example.com/mcp", timeout=30.0).probe_timeout == 30.0


def test_error_panel_shows_brackets_literally() -> None:
    from rich.console import Console

    from toolscore.reports import print_error

    console = Console(record=True, width=80)
    print_error("server said [/var/www/app] not found", console)
    assert "[/var/www/app]" in console.export_text()


def test_huge_integers_do_not_overflow_the_bounds_check() -> None:
    from toolscore.mcp.output_schema import validate_instance

    assert validate_instance(10**400, {"type": "integer", "minimum": 0}) == []
    assert validate_instance(-(10**400), {"type": "integer", "minimum": 0})


def test_a_ping_on_the_event_stream_is_answered() -> None:
    """Legacy Streamable HTTP: a server request on the SSE stream gets a POSTed answer."""
    with (
        FakeHTTPServer(era="legacy", sse=True, ping=True) as server,
        MCPHttpClient(server.url) as client,
    ):
        assert client.call_tool("add", {"a": 2, "b": 3}).text == "5"
        assert {"jsonrpc": "2.0", "id": "srv-ping", "result": {}} in server.client_responses
        answer = next(r for r in server.requests if r["body"].get("id") == "srv-ping")
        assert answer["headers"].get("mcp-session-id")
