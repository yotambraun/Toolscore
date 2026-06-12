"""Zero-dependency MCP (Model Context Protocol) stdio client for toolscore.

This subpackage provides a synchronous, standard-library-only client for
talking to MCP servers over the stdio transport, plus a loader for the
Claude Desktop style server configuration format. On top of that it builds the
"MCP Scorecard" harness: scenario generation, scenario execution, tool linting,
A--F scoring, and console/Markdown/JSON reports.
"""

from __future__ import annotations

from toolscore.mcp.client import (
    MCPError,
    MCPStdioClient,
    MCPTimeoutError,
    MCPToolDef,
    MCPToolResult,
)
from toolscore.mcp.config import MCPServerSpec, load_mcp_config
from toolscore.mcp.harness import (
    LintIssue,
    Scenario,
    ScenarioResult,
    generate_scenarios,
    lint_tools,
    run_scenarios,
)
from toolscore.mcp.scorecard import (
    MCPScorecard,
    grade_meets,
    print_scorecard,
    scorecard_to_json,
    scorecard_to_markdown,
)

__all__ = [
    "LintIssue",
    "MCPError",
    "MCPScorecard",
    "MCPServerSpec",
    "MCPStdioClient",
    "MCPTimeoutError",
    "MCPToolDef",
    "MCPToolResult",
    "Scenario",
    "ScenarioResult",
    "generate_scenarios",
    "grade_meets",
    "lint_tools",
    "load_mcp_config",
    "print_scorecard",
    "run_scenarios",
    "scorecard_to_json",
    "scorecard_to_markdown",
]
