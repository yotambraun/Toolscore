"""MCP (Model Context Protocol) server testing for toolscore.

This subpackage provides synchronous MCP clients for the stdio transport
(standard library only) and the Streamable HTTP transport (``httpx``, the
``[http]`` extra). Both speak MCP 2026-07-28 and fall back to the
``initialize`` handshake of earlier revisions. It also loads the server
configuration files of MCP hosts (Claude Desktop, Cursor, VS Code, Claude Code).
On top of that it builds the "MCP Scorecard" harness: scenario generation,
scenario execution, tool linting, output-schema checks, A--F scoring, badges,
and console/Markdown/JSON reports.
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
from toolscore.mcp.recorder import MCPRecorder
from toolscore.mcp.scorecard import (
    MCPScorecard,
    build_fix_list,
    grade_meets,
    print_scorecard,
    scorecard_to_json,
    scorecard_to_markdown,
)
from toolscore.verdict import FixSuggestion

__all__ = [
    "LEGACY_PROTOCOL_VERSION",
    "MODERN_PROTOCOL_VERSION",
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
    "Scenario",
    "ScenarioResult",
    "build_fix_list",
    "content_to_text",
    "estimate_tokens",
    "generate_scenarios",
    "grade_meets",
    "lint_tools",
    "load_mcp_config",
    "open_client",
    "print_scorecard",
    "run_scenarios",
    "scorecard_to_json",
    "scorecard_to_markdown",
    "tool_definition_tokens",
]
