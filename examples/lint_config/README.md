# Lint agent instructions against the MCP tools that exist

Instruction files tell agents which tools to use. When a server drops or renames a tool, or a file
tells the agent to delete with a tool that declares itself read-only, nothing warns you.
`toolscore lint-config` reads the instruction files and MCP host configs in a repository and checks
every tool reference against what the servers really expose.

This folder is a small repository: a [`.mcp.json`](.mcp.json) with the bundled sample notes server
and a remote server still on the deprecated SSE transport, a [`CLAUDE.md`](CLAUDE.md), and a skill in
[`.claude/skills/tidy-notes/SKILL.md`](.claude/skills/tidy-notes/SKILL.md). The tool list of the notes
server is in `notes.snapshot.json`, written by:

```bash
toolscore mcp list "python -m toolscore.mcp.sample_server" --json notes.snapshot.json
```

## Run it

```bash
cd examples/lint_config
toolscore lint-config --snapshot notes=notes.snapshot.json
```

```text

Config lint  2 instruction file(s), 1 MCP config(s)
Servers: notes (5 tools), tracker (tools unknown)

  ERROR    .claude/skills/tidy-notes/SKILL.md:9  refers to the 'delete_notes' tool, which no 
configured server exposes; did you mean 'delete_note'? (config-unknown-tool)
           -> Point the instruction at a tool the server exposes (check `toolscore mcp list`), or 
remove it.
  WARNING  .claude/skills/tidy-notes/SKILL.md:10  tells the agent to use 'delete_note' to look up, 
but the tool declares destructiveHint: true (config-annotation-contradiction)
           -> Use a read-only tool for lookups; the server says this one can delete or overwrite 
data.
  ERROR    .mcp.json  MCP server 'tracker' uses the HTTP+SSE transport, which the MCP specification 
deprecated in 2025-03-26; toolscore supports stdio and Streamable HTTP. (config-server-invalid)
           -> Point the entry at the server's Streamable HTTP endpoint (type 'http').
  WARNING  CLAUDE.md:6  tells the agent to use 'export_notes' to delete, but the tool declares 
readOnlyHint: true (config-annotation-contradiction)
           -> Use a tool that can make the change, or, if this tool does change state, fix its 
annotations: readOnlyHint: true lets clients run it without asking.
  ERROR    CLAUDE.md:7  'mcp__notes__purge_all': server 'notes' does not expose 'purge_all' 
(config-unknown-tool)
           -> Point the instruction at a tool the server exposes (check `toolscore mcp list`), or 
remove it.
  WARNING  CLAUDE.md:8  'mcp__jira__create_issue' names server 'jira', which no MCP config here 
defines (configured: notes, tracker) (config-unknown-server)
           -> Add the server to the repository's MCP config (.mcp.json), or fix the name in the 
instruction file.

3 error(s), 3 warning(s)
```

Exit status 1 (an error was found; `--fail-on warning` or `--fail-on never` change that). `notes=`
binds the snapshot to the server's name in `.mcp.json`; without it the server's own name
(`notes-server`) is used. `--pin FILE` takes a `toolscore mcp pin` lock file the same way, and
`--connect` starts the servers in the configs to list their tools (it runs their commands, so it is
never the default).

What is not flagged: `mcp__notes__search_notes` and `mcp__notes__list_notes` (the server exposes
them), Claude Code's built-in `Read` and `Bash`, and plain prose. Without any tool list, the rules
that need one are reported as skipped:

```text
Config lint  2 instruction file(s), 1 MCP config(s)
Servers: notes (tools unknown), tracker (tools unknown)
Skipped config-unknown-tool: no tool inventory: pass --snapshot (toolscore mcp list --json) or --pin
(toolscore mcp pin) files, or --connect to start the configured servers
Skipped config-annotation-contradiction: no tool inventory: pass --snapshot (toolscore mcp list 
--json) or --pin (toolscore mcp pin) files, or --connect to start the configured servers
```

The rules (`config-server-invalid`, `config-unknown-server`, `config-unknown-tool`,
`config-annotation-contradiction`) are described in the
[config lint guide](https://yotambraun.github.io/Toolscore/docs/config_lint.html).
