"""Zero-dependency MCP (Model Context Protocol) stdio client for toolscore.

This subpackage provides a synchronous, standard-library-only client for
talking to MCP servers over the stdio transport, plus a loader for the
Claude Desktop style server configuration format. It is the foundation of
toolscore's "MCP Scorecard" feature.
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

__all__ = [
    "MCPError",
    "MCPServerSpec",
    "MCPStdioClient",
    "MCPTimeoutError",
    "MCPToolDef",
    "MCPToolResult",
    "load_mcp_config",
]
