---
name: audit-mcp-server
description: Audit an MCP server with Toolscore - lint its tool definitions, run the A-F scorecard, run effect probes that check its tools really did what they reported, and explain each finding with a concrete fix. Use when someone wants to test, grade, review, harden or debug an MCP server (local stdio command, remote URL, or an entry in a Claude Desktop / Cursor / VS Code / Claude Code config), or asks whether their MCP tools are well described, safe for clients, or silently failing.
when_to_use: Trigger phrases include "test my MCP server", "grade this MCP server", "audit MCP tools", "MCP scorecard", "is my MCP server any good", "lint tool descriptions", "do my tools actually work".
argument-hint: "[server command | URL | config file + server name]"
---

# Audit an MCP server

Toolscore measures; you explain. Every number and finding you report must come
from a Toolscore run in this session.

## 0. Toolscore

Use `toolscore` if it is installed (`toolscore --version` prints 1.11 or later),
otherwise `uvx tool-scorer` in its place (same commands). Remote servers need
`pip install "tool-scorer[http]"` (or `uvx --from "tool-scorer[http]" toolscore`).

## 1. Find the server

Work out the target from `$ARGUMENTS` or the repository:

- A local stdio server: the command that starts it, quoted as one argument,
  for example `"python server.py"`, `"node dist/index.js"`, `"uvx my-server"`.
  Look at `pyproject.toml` / `package.json` scripts and the README for it.
- A remote Streamable HTTP server: its URL. A token goes in an environment
  variable passed by name, `--auth-env MCP_TOKEN`; never put a secret on the
  command line or in your reply.
- A host config: `--config .mcp.json --server NAME` (also Claude Desktop,
  Cursor and VS Code files).

If the server needs real paths or IDs (filesystem or git servers reject
generated ones), collect values the user is happy for it to touch and pass them
with `--arg path=/tmp/sandbox/notes.txt` or `--arg TOOL:NAME=VALUE`.

## 2. Lint (static, reads only the tool list)

```bash
toolscore mcp lint "python server.py"
```

Every issue has a stable rule ID. Group them for the user: references to tools
the server does not expose, tool poisoning (hidden Unicode, "ignore previous
instructions", text that hides things from the user), missing or contradictory
behavior annotations (`readOnlyHint`, `destructiveHint`), schema hygiene.

## 3. Scorecard (calls every tool)

```bash
toolscore mcp test "python server.py" --report md -o SCORECARD.md
```

This calls each tool with generated happy-path and edge-case arguments. Before
running it on a server connected to real data or real accounts, tell the user
that it calls every tool, including write and delete tools, and ask. Report the
grade, the score, and the "Top issues to fix" list. Two outcomes do not change
the score but belong in your summary: `edge-accepted-invalid-input` (a tool
answered arguments that break its own input schema as a success) and scenarios
that are "not evaluated" because the server asked for client input
(`input_required`); say they were not tested, not that they passed.

## 4. Effect probes

Read-only probes need no permission beyond step 3:

```bash
toolscore mcp test "python server.py" --probes
```

Write probes create, overwrite and read back marker records (`tsp<hex>-...`)
and leave them behind. **Ask the user before adding `--allow-writes`**, and only
point it at a disposable instance, a sandbox directory or a test account:

```bash
toolscore mcp test "python server.py" --probes --allow-writes
```

A high-confidence probe failure such as `probe-silent-noop` (a write that
reported success and changed nothing) or `probe-data-lost` caps the grade at C;
say so when it happens. Low- and medium-confidence probe results are hints, not
verdicts: say which read tool the probe used (the `basis` column) and that a
probe config (`--probe-config probes.yaml`, see the effect-probes guide) makes
them exact.

## 5. Explain the fixes

For each finding, in order of impact:

1. what is wrong, quoting the tool name and the rule ID;
2. why it matters to a client or a model (models choose tools by their
   descriptions; clients use annotations to decide whether to ask first);
3. the concrete change: a description rewrite, the annotation JSON, the schema
   property type, the handler bug. If the server's source is in this
   repository, offer to make the change and re-run the scorecard to show the
   grade move.

Then suggest the next steps that fit: a grade badge
(`--badge .github/badges/mcp-grade.svg`), a CI gate
(`uses: yotambraun/toolscore@v1` with `mcp-command` and `mcp-fail-under`; add
`sarif-file` and `github/codeql-action/upload-sarif` to see the findings in
GitHub code scanning, or `--junit` for a GitLab or Jenkins test report), and
pinning the tool definitions with the `pin-mcp-servers` skill.

Guides: https://yotambraun.github.io/Toolscore/docs/mcp_testing.html and
https://yotambraun.github.io/Toolscore/docs/effect_probes.html

$ARGUMENTS
