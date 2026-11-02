"""MCP (Model Context Protocol) server testing for toolscore.

This subpackage provides synchronous MCP clients for the stdio transport
(standard library only) and the Streamable HTTP transport (``httpx``, the
``[http]`` extra). Both speak MCP 2026-07-28 and fall back to the
``initialize`` handshake of earlier revisions. It also loads the server
configuration files of MCP hosts (Claude Desktop, Cursor, VS Code, Claude Code).
On top of that it builds the "MCP Scorecard" harness: scenario generation,
scenario execution, tool linting, output-schema checks, effect probes (did the
tool really do what it reported), A--F scoring, badges, and console/Markdown/JSON
reports. ``MCPRecorder`` records stdio sessions and, with a fault spec, injects
failures into chosen calls. Snapshots, locks and diffs (:mod:`toolscore.mcp.pin`,
:mod:`toolscore.mcp.server_diff`) pin a server's tools and catch drift.
"""

from __future__ import annotations

from toolscore.mcp.client import (
    LEGACY_PROTOCOL_VERSION,
    MODERN_PROTOCOL_VERSION,
    MCPClient,
    MCPError,
    MCPHttpClient,
    MCPHTTPStatusError,
    MCPStdioClient,
    MCPTimeoutError,
    MCPToolDef,
    MCPToolResult,
)
from toolscore.mcp.config import MCPServerSpec, load_mcp_config, open_client
from toolscore.mcp.content import content_to_text
from toolscore.mcp.faults import FaultInjector, FaultRule, FaultSpec, load_fault_spec
from toolscore.mcp.fixtures import ArgumentFixtures, load_fixtures
from toolscore.mcp.harness import (
    LintIssue,
    Scenario,
    ScenarioResult,
    estimate_tokens,
    generate_scenarios,
    lint_tools,
    run_scenarios,
    tool_definition_tokens,
)
from toolscore.mcp.pin import (
    CAPABILITIES,
    PIN_RULES,
    PinFinding,
    PinReport,
    build_lock,
    infer_capabilities,
    load_lock,
    verify_pin,
    write_lock,
)
from toolscore.mcp.probes import (
    PROBE_RULES,
    Agreement,
    BoundRelation,
    CallSpec,
    ProbeConfig,
    ProbeResult,
    RoundTripPair,
    load_probe_config,
    run_probes,
)
from toolscore.mcp.recorder import MCPRecorder
from toolscore.mcp.scorecard import (
    PROBE_GRADE_CAP,
    MCPScorecard,
    build_fix_list,
    grade_meets,
    print_scorecard,
    scorecard_to_json,
    scorecard_to_markdown,
)
from toolscore.mcp.server_diff import ServerDiff, ToolChange, diff_snapshots
from toolscore.mcp.snapshot import ServerSnapshot, load_snapshot, write_snapshot
from toolscore.verdict import FixSuggestion

__all__ = [
    "CAPABILITIES",
    "LEGACY_PROTOCOL_VERSION",
    "MODERN_PROTOCOL_VERSION",
    "PIN_RULES",
    "PROBE_GRADE_CAP",
    "PROBE_RULES",
    "Agreement",
    "ArgumentFixtures",
    "BoundRelation",
    "CallSpec",
    "FaultInjector",
    "FaultRule",
    "FaultSpec",
    "FixSuggestion",
    "LintIssue",
    "MCPClient",
    "MCPError",
    "MCPHTTPStatusError",
    "MCPHttpClient",
    "MCPRecorder",
    "MCPScorecard",
    "MCPServerSpec",
    "MCPStdioClient",
    "MCPTimeoutError",
    "MCPToolDef",
    "MCPToolResult",
    "PinFinding",
    "PinReport",
    "ProbeConfig",
    "ProbeResult",
    "RoundTripPair",
    "Scenario",
    "ScenarioResult",
    "ServerDiff",
    "ServerSnapshot",
    "ToolChange",
    "build_fix_list",
    "build_lock",
    "content_to_text",
    "diff_snapshots",
    "estimate_tokens",
    "generate_scenarios",
    "grade_meets",
    "infer_capabilities",
    "lint_tools",
    "load_fault_spec",
    "load_fixtures",
    "load_lock",
    "load_mcp_config",
    "load_probe_config",
    "load_snapshot",
    "open_client",
    "print_scorecard",
    "run_probes",
    "run_scenarios",
    "scorecard_to_json",
    "scorecard_to_markdown",
    "tool_definition_tokens",
    "verify_pin",
    "write_lock",
    "write_snapshot",
]
