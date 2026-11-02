For Security and Platform Teams
===============================

Know which MCP servers your agents use, fail CI when one of them changes under
you, block destructive calls and leaked credentials, and review what coding
agents did on developer machines. Everything is local and deterministic.

1. Pin every MCP server
-----------------------

.. code-block:: bash

   toolscore mcp pin --config .mcp.json --server notes -o pins/notes.lock.json
   toolscore mcp verify-pin --config .mcp.json --server notes --lock pins/notes.lock.json

The lock file holds a SHA-256 of every tool definition, the server identity,
protocol and instructions, and a read/write/delete/network/exec capability
manifest. ``examples/pinning/`` has a rug pull: the same server with a
poisoned ``search_notes`` description and a new ``run_command`` tool. Real
output, shortened:

.. code-block:: text

   $ toolscore mcp verify-pin examples/pinning/notes-rugpull.json --lock examples/pinning/notes.lock.json
   Pin check
     ERROR  new tool 'run_command' can exec (name 'run' + 'command'; description 'Runs a 
   shell command') (pin-capability-added)
     ERROR  new tool 'run_command' (exec) is not in the lock (pin-tool-added)
   …
     ERROR  'search_notes' changed: description (pin-tool-changed)
   …
   Pin check: FAIL (3 failing of 3 finding(s), --fail-on drift)

``--fail-on capability`` fails only on a new delete or exec capability. In CI,
the Action's ``mcp-pin-file`` input does the same (:doc:`pinning_diff`).

2. Lint the instructions that name the tools
--------------------------------------------

``toolscore lint-config`` reads ``CLAUDE.md``, ``AGENTS.md``, ``SKILL.md`` files,
Cursor rules and Copilot instructions, and the MCP host configs, and flags tool
names no configured server exposes, unknown servers, configs on the deprecated
SSE transport, and instructions that contradict a tool's annotations, such as
deleting with a ``readOnlyHint`` tool (:doc:`config_lint`):

.. code-block:: bash

   toolscore lint-config --pin notes=pins/notes.lock.json --fail-on error

3. Block destructive calls and leaked credentials
-------------------------------------------------

A policy file of forbidden calls, with matchers, and the credential detector
(OpenAI, Anthropic, GitHub, AWS, Google, Slack, Stripe keys, private keys) run
on every trace. Real output on ``examples/guardrails/``, shortened:

.. code-block:: text

   $ toolscore eval gold.json trace.json --forbidden forbidden.json --fail-on-violations
   …
     ERROR    call 2 run_shell matches forbidden rule 1: destructive shell command
     ERROR    call 3 http_post passes a credential (aws_access_key_id) in 'body.text': 
   AKIA…LE
   …
   ERROR 2 forbidden call(s) or credential(s) found (--fail-on-violations)

Credentials are shown only as redacted previews in every report
(:doc:`behavior_safety`). MCP lint also flags tool poisoning in definitions:
hidden Unicode, "ignore previous instructions", text that tells the model to
hide something from the user (:doc:`mcp_testing`).

4. Review what coding agents did
--------------------------------

.. code-block:: bash

   toolscore sessions list --since 1d --flagged
   toolscore honesty ~/.claude/projects/<project>/<session>.jsonl
   toolscore sessions export SESSION.jsonl -o trace.json      # credentials redacted

Claude Code and Codex CLI sessions are read in place, read-only, and nothing is
uploaded (:doc:`coding_sessions`). To see how an agent behaves when a tool is
denied or fails, put ``toolscore mcp proxy --inject faults.json`` in front of a
server: the session records what was injected, so the honesty checks know the
ground truth (:doc:`fault_injection`).
