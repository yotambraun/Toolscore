"""Protocol-era detection: MCP 2026-07-28 (stateless) and the legacy handshake.

The client probes with ``server/discover`` and falls back to ``initialize``
(2025-11-25) when the server is legacy, following the specification's stdio
backward-compatibility rules. These tests run the fake server fixture in each
era and the bundled sample server (which is dual-era).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from toolscore.mcp import MCPError, MCPStdioClient
from toolscore.mcp.client import (
    LEGACY_PROTOCOL_VERSION,
    META_CLIENT_CAPABILITIES,
    META_CLIENT_INFO,
    META_PROTOCOL_VERSION,
    MODERN_PROTOCOL_VERSION,
    MCPClient,
)

FIXTURE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mcp_server.py"


def _fake(*extra: str) -> list[str]:
    return [sys.executable, str(FIXTURE_SERVER), *extra]


def test_versions_are_the_verified_revisions() -> None:
    assert MODERN_PROTOCOL_VERSION == "2026-07-28"
    assert LEGACY_PROTOCOL_VERSION == "2025-11-25"


def test_modern_server_is_used_statelessly() -> None:
    with MCPStdioClient(_fake("--era", "modern"), timeout=10.0) as client:
        assert client.era == "modern"
        assert client.protocol_version == MODERN_PROTOCOL_VERSION
        assert client.server_info == {"name": "fake-mcp-modern", "version": "0.2.0"}
        assert client.server_versions == [MODERN_PROTOCOL_VERSION]
        # The modern-only server rejects requests without _meta, so these
        # succeed only because every request carries the per-request fields.
        assert [t.name for t in client.list_tools()] == ["add", "flaky", "bad_schema"]
        result = client.call_tool("add", {"a": 2, "b": 3})
        assert not result.is_error
        assert result.text == "5"


def test_modern_server_instructions_come_from_discover() -> None:
    with MCPStdioClient(_fake("--era", "modern", "--instructions", "Be nice."), timeout=10.0) as c:
        assert c.server_instructions == "Be nice."
        assert c.server_capabilities == {"tools": {}}


def test_legacy_server_falls_back_to_initialize() -> None:
    with MCPStdioClient(_fake("--era", "legacy"), timeout=10.0) as client:
        assert client.era == "legacy"
        # The fake legacy server negotiates down to 2025-06-18.
        assert client.protocol_version == "2025-06-18"
        assert client.server_info["name"] == "fake-mcp"
        assert client.call_tool("add", {"a": 1, "b": 1}).text == "2"


def test_dual_era_server_stays_modern() -> None:
    with MCPStdioClient(_fake("--era", "dual"), timeout=10.0) as client:
        assert client.era == "modern"
        assert client.call_tool("add", {"a": 4, "b": 5}).text == "9"


def test_silent_legacy_server_falls_back_after_the_probe_timeout() -> None:
    started = time.monotonic()
    with MCPStdioClient(
        _fake("--era", "legacy", "--silent-unknown"), timeout=10.0, probe_timeout=0.5
    ) as client:
        assert client.era == "legacy"
        assert client.call_tool("add", {"a": 1, "b": 2}).text == "3"
    # Fell back after the short probe timeout, not the 10s request timeout.
    assert time.monotonic() - started < 8.0


def test_default_probe_timeout_is_bounded() -> None:
    assert MCPStdioClient(["unused"], timeout=30.0).probe_timeout == 5.0
    assert MCPStdioClient(["unused"], timeout=2.0).probe_timeout == 2.0


def test_unsupported_version_with_a_legacy_alternative_uses_initialize() -> None:
    command = _fake("--era", "dual", "--modern-versions", "2099-01-01,2025-11-25")
    with MCPStdioClient(command, timeout=10.0) as client:
        assert client.era == "legacy"


def test_no_common_version_is_a_clear_error() -> None:
    client = MCPStdioClient(
        _fake("--era", "modern", "--modern-versions", "2099-01-01"), timeout=10.0
    )
    with pytest.raises(MCPError, match=r"No protocol version in common.*2099-01-01"):
        client.start()


def test_discover_result_without_our_version_is_a_clear_error() -> None:
    # A DiscoverResult that does not list 2026-07-28 and offers no legacy version.
    with pytest.raises(MCPError, match="No protocol version in common"):
        MCPClient()._adopt_discover({"supportedVersions": ["2099-01-01"]}, auto=True)


def test_forced_modern_against_a_legacy_server_explains_itself() -> None:
    client = MCPStdioClient(_fake("--era", "legacy"), timeout=10.0, protocol="modern")
    with pytest.raises(MCPError, match="does not support server/discover"):
        client.start()


def test_forced_legacy_skips_the_probe() -> None:
    with MCPStdioClient(_fake("--era", "dual"), timeout=10.0, protocol="legacy") as client:
        assert client.era == "legacy"
        assert client.protocol_version == "2025-06-18"


def test_modern_only_server_rejects_a_forced_legacy_client_clearly() -> None:
    client = MCPStdioClient(_fake("--era", "modern"), timeout=10.0, protocol="legacy")
    with pytest.raises(MCPError, match="initialize"):
        client.start()


def test_invalid_protocol_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="protocol must be"):
        MCPStdioClient(["unused"], protocol="newest")  # type: ignore[arg-type]


def test_meta_fields_are_added_only_in_the_modern_era() -> None:
    client = MCPClient()
    client.era = "legacy"
    assert client._params({"name": "x"}) == {"name": "x"}
    client.era = "modern"
    client.protocol_version = MODERN_PROTOCOL_VERSION
    meta = client._params({"name": "x", "_meta": {"progressToken": 1}})["_meta"]
    assert meta[META_PROTOCOL_VERSION] == MODERN_PROTOCOL_VERSION
    assert meta[META_CLIENT_INFO]["name"] == "toolscore"
    assert meta[META_CLIENT_CAPABILITIES] == {}
    assert meta["progressToken"] == 1


def test_input_required_results_are_reported_as_errors() -> None:
    class Canned(MCPClient):
        def _roundtrip(self, method, params, request_id=None, timeout=None):  # type: ignore[no-untyped-def]
            return {"jsonrpc": "2.0", "id": 1, "result": {"resultType": "input_required"}}

    result = Canned().call_tool("ask", {})
    assert result.is_error
    assert "input_required" in result.text


@pytest.mark.parametrize("protocol", ["auto", "legacy"])
def test_bundled_sample_server_speaks_both_eras(protocol: str) -> None:
    command = [sys.executable, "-m", "toolscore.mcp.sample_server"]
    with MCPStdioClient(command, timeout=10.0, protocol=protocol) as client:  # type: ignore[arg-type]
        expected_era = "modern" if protocol == "auto" else "legacy"
        assert client.era == expected_era
        assert client.server_info["name"] == "notes-server"
        tools = {t.name: t for t in client.list_tools()}
        assert tools["delete_note"].annotations == {"readOnlyHint": False, "destructiveHint": True}
        assert tools["list_notes"].output_schema is not None
        listed = client.call_tool("list_notes", {"limit": 2})
        assert listed.structured_content == {"notes": ["groceries", "ideas"], "count": 2}
        assert client.call_tool("export_notes", {"format": "json"}).is_error
