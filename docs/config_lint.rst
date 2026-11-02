Agent-Config Lint
=================

Instruction files tell agents which tools to use: ``CLAUDE.md``, ``AGENTS.md``,
``SKILL.md`` files, Cursor rules, Copilot instructions. When a server renames
or drops a tool, or an instruction says to delete with a tool that declares
itself read-only, nothing warns you: the agent calls a tool that is not there,
or a client runs a "read-only" tool without asking. ``toolscore lint-config``
checks every tool reference in those files against what the configured MCP
servers really expose.

.. code-block:: bash

   toolscore lint-config                                   # the current repository
   toolscore lint-config --snapshot notes=notes.snapshot.json
   toolscore lint-config --pin pins/notes.lock.json --fail-on warning
   toolscore lint-config --connect                         # start the configured servers

What it reads
-------------

* Instruction files: ``CLAUDE.md``, ``CLAUDE.local.md``, ``AGENTS.md``, any
  ``SKILL.md`` (``.claude/skills/*/SKILL.md``, plugin skills), ``.cursor/rules``
  (``.mdc`` and ``.md``), ``.cursorrules``, ``.github/copilot-instructions.md``
  and ``.github/instructions/*.instructions.md``. A Markdown file named on the
  command line is always read. ``.git``, ``node_modules``, virtual environments
  and build output are skipped.
* MCP host configs: ``.mcp.json``, ``.cursor/mcp.json``, ``.vscode/mcp.json`` and
  ``claude_desktop_config.json``; with ``--user``, also ``~/.claude.json``.
* The tools each server exposes: ``--snapshot [SERVER=]FILE`` (a
  ``toolscore mcp list --json`` snapshot) or ``--pin [SERVER=]FILE`` (a
  ``toolscore mcp pin`` lock file), repeatable. ``SERVER`` is the server's name
  in your MCP config; without it the server's own name is used. ``--connect``
  starts every configured server to list its tools: it runs the commands in the
  config files, so it is never the default.

Without a tool list, the rules that need one are reported as **skipped**, never
as passed.

Rules
-----

``config-server-invalid`` (error)
   A host-config entry Toolscore cannot use: no ``command`` or ``url``, the
   deprecated SSE transport, or unreadable JSON. Entries whose ``${VAR}`` is
   unset here are not flagged.

``config-unknown-server`` (warning)
   An ``mcp__<server>__<tool>`` name whose server no host config defines.

``config-unknown-tool`` (error)
   An ``mcp__<server>__<tool>`` name whose server is known and does not expose
   the tool, or a quoted name written as a tool (```delete_notes` tool``) that
   is close to, but not, a tool a configured server exposes ("did you mean").

``config-annotation-contradiction`` (warning)
   "use X to delete / create / update ..." where X declares
   ``readOnlyHint: true``, or "use X to read / list / look up ..." where X
   declares ``destructiveHint: true``.

The rules are conservative: Claude Code's built-in tools (``Read``, ``Bash``,
...) and plain prose are never flagged, a quoted name far from every MCP tool is
left alone, and ``mcp__plugin_*`` / ``mcp__claude_ai_*`` names, which come from
plugins and connectors outside the repository, are not checked against it.

Example
-------

``examples/lint_config/`` is a small repository with a ``.mcp.json`` (the
bundled sample notes server, and a remote server still on SSE), a ``CLAUDE.md``
and a skill. Real output:

.. code-block:: text

   $ cd examples/lint_config && toolscore lint-config --snapshot notes=notes.snapshot.json

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

Exit status 1 on an error (``--fail-on warning`` or ``never`` change that);
``--json FILE`` writes the report. In CI, run it next to ``toolscore mcp
verify-pin`` so that a server change and the instructions that depend on it
are checked together (:doc:`pinning_diff`).
