---
name: pin-mcp-servers
description: Pin the tool definitions of MCP servers with Toolscore (toolscore.lock.json with a hash of every tool, the server, protocol and instructions, and a read/write/delete/network/exec capability manifest) and verify the pin in CI, so a changed tool description, a new tool or a new delete or exec capability fails the build. Use when someone wants to protect against MCP rug pulls or tool-description poisoning, lock MCP server versions, detect MCP server drift, or review what changed between two server versions.
when_to_use: Trigger phrases include "pin my MCP servers", "MCP lock file", "rug pull", "tool poisoning", "detect MCP drift", "what changed in this MCP server", "verify MCP server in CI".
argument-hint: "[server command | URL | config file + server name]"
---

# Pin MCP servers

Pinning reads each server's tool list (`tools/list`) and calls no tools.

## 0. Toolscore

Use `toolscore` (1.11 or later; `toolscore --version`) or `uvx tool-scorer` in
its place. Remote servers need the `[http]` extra.

## 1. Which servers

From `$ARGUMENTS`, or the MCP host config in the repository (`.mcp.json`,
`.cursor/mcp.json`, `.vscode/mcp.json`) or the user's client config. List them
for the user, with the version each command starts. A command such as
`npx -y @scope/server` without a version can change under the pin at any time;
suggest pinning the package version in the command too
(`npx -y @scope/server@1.2.3`).

## 2. Pin

One lock file per server keeps diffs readable:

```bash
toolscore mcp pin "npx -y @modelcontextprotocol/server-memory@2.0.1" -o pins/memory.lock.json
toolscore mcp pin --config .mcp.json --server notes -o pins/notes.lock.json
```

Show the capability manifest it printed (which tools read, write, delete, use
the network or execute code) and ask the user to confirm it matches what they
expect. If a tool is classified wrongly, write a capability override file and
re-pin with `--capabilities overrides.json`. Commit the lock files.

## 3. Verify

```bash
toolscore mcp verify-pin "npx -y @modelcontextprotocol/server-memory@2.0.1" --lock pins/memory.lock.json
```

Exit status 1 means drift. `--fail-on capability` fails only on a new delete or
exec capability; `--fail-on never` reports without failing. To see exactly what
changed between two builds or versions, with text diffs of the descriptions:

```bash
toolscore mcp diff "npx -y @modelcontextprotocol/server-memory@2026.8.31" "npx -y @modelcontextprotocol/server-memory@2.0.1"
```

## 4. CI

```yaml
- uses: yotambraun/toolscore@v1
  with:
    mcp-command: 'npx -y @modelcontextprotocol/server-memory@2.0.1'
    mcp-pin-file: pins/memory.lock.json
    mcp-pin-fail-on: drift
```

Or run `toolscore mcp verify-pin ... --ci` in any job: it writes the report to
the GitHub Actions job summary. `--sarif drift.sarif` (for GitHub code scanning)
and `--junit drift.xml` (for GitLab or Jenkins) write each drift finding,
pointing at the lock file. To catch drift before it is committed, add the
`toolscore-verify-pin` pre-commit hook (`repo: https://github.com/yotambraun/toolscore`,
`args: ["python server.py", --lock, toolscore.lock.json]`). When a change is intended, review the diff with
the user, then re-run `toolscore mcp pin` and commit the new lock file in the
same pull request.

Guide: https://yotambraun.github.io/Toolscore/docs/pinning_diff.html

$ARGUMENTS
