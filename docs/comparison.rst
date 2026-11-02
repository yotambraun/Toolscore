Toolscore and Other MCP Tools
=============================

People who look at Toolscore usually also look at MCP Inspector, an MCP
security scanner, DeepEval's MCP metrics, Promptfoo, or the official MCP
conformance suite. They do different jobs, and several of them do their job
better than Toolscore would. This page says which to reach for, and where
Toolscore fits.

Every statement about another tool links to that tool's own documentation or
repository, as read on **2026-11-02**. Tools change; if something here is out of
date, please open an issue.

.. contents::
   :local:
   :depth: 1


Where Toolscore fits
--------------------

Toolscore asks two questions after the tool calls themselves look right: **did
the tool really do it**, and **did the agent tell the truth about it**. It grades
an MCP server from its own tool schemas (happy paths, edge cases, lint, A-F),
runs effect probes that write a value and read it back, pins tool definitions
against a lock file, injects faults through a proxy, and compares an agent's
final answer with what its tools returned. All of it is deterministic, runs
offline and costs nothing per run; a result Toolscore cannot check is reported
as unknown, never as a pass.

It is not an interactive debugger, a protocol conformance suite, a security
scanner with threat research behind it, an LLM judge of answer quality, or an
attack generator. The tools below are.


Which tool for which job
------------------------

.. list-table::
   :header-rows: 1
   :widths: 34 33 33

   * - Job
     - Reach for
     - What Toolscore does there
   * - Explore a server by hand, debug OAuth, review an MCP App
     - **MCP Inspector** (web UI, TUI, CLI)
     - Nothing comparable: no UI. ``toolscore mcp list`` prints the tools.
   * - Script a smoke test in CI: connect, list, call, assert
     - **MCP Inspector CLI** (JSON output, exit codes, assertions you write with
       ``jq``)
     - ``toolscore mcp test`` generates the calls from the tool schemas and grades
       the server, with no assertions to write.
   * - Check that a server or client conforms to the MCP specification
     - **The official MCP conformance suite**
     - Does not replace it. Toolscore tests what the tools do, not every rule of
       the protocol.
   * - Scan the agents, MCP servers and skills on a machine for prompt
       injection, tool poisoning, toxic flows or malware
     - **Snyk Agent Scan** or **Cisco MCP Scanner**
     - A lighter, offline check: lint rules for instructions hidden in tool
       descriptions, and ``mcp pin`` / ``verify-pin`` to fail CI when a tool
       definition changes or a delete/exec tool appears.
   * - Judge with a model whether an agent used its MCP tools well
     - **DeepEval** (MCP Use, Multi-Turn MCP Use, MCP Task Completion)
     - Deterministic checks instead: required and forbidden calls, arguments,
       contracts. An LLM judge is optional (:doc:`llm_judge`).
   * - Red-team an agent or an MCP server with generated attacks
     - **Promptfoo** (MCP provider and the MCP red-team plugin)
     - Fault injection with fixed, reproducible faults (``mcp proxy --inject``),
       including one planted instruction with a canary token, not attack
       generation.
   * - Compare prompts and models over a test matrix in YAML
     - **Promptfoo**
     - Not its job; Toolscore is a pytest plugin, a CLI and a Python API.
   * - Check that a write really happened (write, then read back)
     - **Toolscore** effect probes (:doc:`effect_probes`)
     - ``probe-silent-noop``, ``probe-data-lost``, bounds and agreement checks.
   * - Check that the agent's final answer matches what its tools returned
     - **Toolscore** honesty checks (:doc:`honesty_checks`)
     - ``claimed-success``, ``undisclosed-warning``,
       ``escape-hatch-after-refusal``, injected faults the answer hides.

For the last two rows we found no equivalent check in the documentation of the
tools above; that is the gap Toolscore was built for.


MCP Inspector
-------------

`MCP Inspector <https://github.com/modelcontextprotocol/inspector>`__ is the MCP
project's developer tool for inspecting servers. One package provides a web UI,
a CLI "for automation, CI, and fast agent feedback loops", a terminal UI and an
experimental connection CLI. Its `smoke-testing guide
<https://github.com/modelcontextprotocol/inspector/blob/main/docs/cli-smoke-testing.md>`__
describes a connect, list, call, assert workflow with ``--format json``, ``jq``
and an exit-code map, and Inspector manages OAuth tokens and client secrets.

**Use Inspector** to look at a server, try calls by hand, debug authorization,
or write precise assertions about specific calls. **Use Toolscore** when you
want a server graded without writing the calls, or want effect probes, pinning,
fault injection or a grade badge. They work well together: Inspector to
understand a failure Toolscore reports.


MCP security scanners
---------------------

`Snyk Agent Scan <https://github.com/snyk/agent-scan>`__ (the
``invariantlabs-ai/mcp-scan`` repository now redirects to it) discovers the
agents, MCP servers and skills on a machine and scans them for prompt
injection, tool poisoning, tool shadowing and toxic flows, and skills for
malicious code and credential handling. Analysis goes through the Agent Scan
API: its README says it sends tool names and descriptions, server
configurations and skill content, with secrets redacted. It has ``--ci`` and
``--json``; the README calls the CLI output experimental.

`Cisco MCP Scanner <https://github.com/cisco-ai-defense/mcp-scanner>`__ scans
tools, prompts, resources and server instructions with YARA rules (no API key
needed), an LLM analyzer, the Cisco AI Defense API, behavioral analysis of the
server's source code against its descriptions, VirusTotal lookups and
dependency audits; the analyzers beyond YARA and the dependency audit need keys
or network access.

**Use a scanner** for a security review of what is installed: they bring threat
research, semantic analysis and malware checks that Toolscore does not have.
**Toolscore's part** is smaller and offline: lint rules for hidden instructions
in descriptions (pattern-based, so they miss what the patterns do not know), a
lock file that fails CI on any change to a tool definition (a rug pull), and a
capability manifest that flags a new delete or exec tool. See
:doc:`for_security_teams`.


DeepEval
--------

DeepEval's `MCP Use metric <https://deepeval.com/docs/metrics-mcp-use>`__
"uses LLM-as-a-judge to evaluate the MCP primitives called as well as the
arguments generated", with multi-turn and task-completion variants. Its
`Tool Correctness metric <https://deepeval.com/docs/metrics-tool-correctness>`__
compares ``tools_called`` with ``expected_tools`` deterministically and adds an
LLM judgment of tool selection when ``available_tools`` is given.

**Use DeepEval** when "did it use the tools well" needs semantic judgment, or
for its broad answer-quality and RAG metrics. **Use Toolscore** when the check
must be deterministic and free: the same trace always gets the same result,
with no model call. DeepEval's MCP metrics evaluate how an application uses MCP
servers; Toolscore's MCP commands test the server itself.


Promptfoo
---------

Promptfoo's `MCP provider <https://www.promptfoo.dev/docs/providers/mcp/>`__
"calls Model Context Protocol (MCP) tools directly, so you can test or red team
the server itself", for local and remote servers. Its `MCP red-team plugin
<https://www.promptfoo.dev/docs/red-team/plugins/mcp/>`__ generates attacks
such as function discovery, parameter injection and tool metadata injection.
Its `assertions <https://www.promptfoo.dev/docs/configuration/expected-outputs/>`__
include deterministic tool checks (``is-valid-openai-tools-call``,
``tool-call-f1``, ``trajectory:tool-used``, ``trajectory:tool-args-match``,
``trajectory:tool-sequence``) and model-assisted ones.

**Use Promptfoo** for adversarial testing and for comparing prompts and models
across a matrix. **Use Toolscore** for a server grade generated from the
schemas, effect probes, pinning, reproducible fault injection, and honesty
checks on the agent's final answer, in pytest or the CLI.


The MCP conformance suite
-------------------------

The `MCP conformance test framework
<https://github.com/modelcontextprotocol/conformance>`__ tests MCP client and
server implementations against the specification. For a server it connects by
URL, runs scenarios (initialization, tool listing and calls, resources,
prompts), validates every JSON-RPC message on the wire against the spec's JSON
schema, and can run exactly what one revision (such as 2026-07-28) requires. It
has a GitHub Action.

**Toolscore does not replace it.** If you build an MCP SDK or need to show
conformance, run the conformance suite. Toolscore speaks 2026-07-28 and
2025-11-25 and reports the protocol problems it meets, but its tests are about
whether your tools work, do what they report, and are described well enough for
a model to use them.


Using them together
-------------------

A server team might run the conformance suite on its SDK, Toolscore's
``mcp test --probes --ci`` and ``verify-pin`` in every pull request, Inspector
when something fails, and a security scanner before publishing. An agent team
might use DeepEval or Promptfoo for answer quality and red-teaming, and
Toolscore's contracts and honesty checks as the deterministic gate in CI.
