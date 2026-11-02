Toolscore Documentation
=======================

.. image:: https://badge.fury.io/py/tool-scorer.svg
   :target: https://badge.fury.io/py/tool-scorer
   :alt: PyPI version

.. image:: https://img.shields.io/badge/License-Apache%202.0-blue.svg
   :target: https://github.com/yotambraun/Toolscore/blob/main/LICENSE
   :alt: License

.. image:: https://static.pepy.tech/badge/tool-scorer
   :target: https://pepy.tech/project/tool-scorer
   :alt: Downloads

**Toolscore** tests MCP servers and the tool calls agents make. It grades any MCP server A--F (local or remote, MCP 2026-07-28 and earlier revisions) and checks the tool calls an agent makes against the ones you expect, locally, deterministically and without an API key.

Correct tool calls are not enough. Toolscore checks that the tool really did it (:doc:`effect_probes`), and that the agent told the truth about it (:doc:`honesty_checks`, :doc:`fault_injection`).

What is Toolscore?
------------------

Toolscore evaluates LLM tool usage - it doesn't call LLM APIs directly. Think of it as a testing framework for function-calling agents:

✅ **Evaluates** tool usage traces from OpenAI (Chat Completions and Responses), Anthropic, Gemini, agent frameworks, recorded MCP sessions, OpenTelemetry spans, or custom sources

✅ **Compares** actual behavior against expected gold standards

✅ **Reports** detailed metrics on accuracy, efficiency, and correctness, plus failed calls, leaked credentials and forbidden calls

✅ **Grades and lints** MCP servers over stdio or Streamable HTTP, including behavior annotations, output schemas, references to missing tools and tool poisoning

❌ **Does NOT** call LLM APIs or execute tools (you capture traces separately)

Quick Start
-----------

.. code-block:: bash

   pip install tool-scorer

   # Run evaluation
   toolscore eval examples/gold_calls.json examples/trace_openai.json --html report.html

   # Grade a bundled sample MCP server, then your own (a command or a URL)
   toolscore demo
   toolscore mcp test "python my_server.py"
   toolscore mcp test https://mcp.example.com/mcp --auth-env MCP_TOKEN   # needs tool-scorer[http]

Key Features
------------

* **Comprehensive Metrics Suite**: Tool invocation accuracy, selection accuracy, sequence edit distance, argument matching, redundant and repeated calls, required calls completed, and side-effect validation
* **Behavior and Safety Checks**: Failed calls, blind retries, credentials passed into tool arguments, and forbidden-call policies, with a CI gate (:doc:`behavior_safety`)
* **Truth Checks**: effect probes that catch tools reporting success without doing it (:doc:`effect_probes`), honesty checks that compare tool results with the agent's final answer (:doc:`honesty_checks`), and a fault-injection proxy that makes chosen calls fail (:doc:`fault_injection`)
* **Rigor**: an agent harness that runs LLM agents against MCP servers with guards, budgets and resumable runs (:doc:`agent_harness`); pinning and drift checks against MCP rug pulls, and server diffs (:doc:`pinning_diff`); contracts with optional, forbidden and alternative calls (:doc:`contracts`); content-hashed receipts, regrading and tri-state evidence (:doc:`receipts`); repeated-run statistics and variant selection (:doc:`comparing_runs`)
* **Snapshot Testing**: Record, approve and replay your agent's tool calls in pytest (:doc:`snapshot_testing`)
* **MCP Scorecard, Lint and Recorder**: Grade any MCP server (stdio or Streamable HTTP, MCP 2026-07-28 with a fallback to the ``initialize`` handshake), lint its annotations, output schemas, missing-tool references and tool poisoning, write a grade badge, and record real sessions (:doc:`mcp_testing`)
* **Native Everywhere**: OpenAI (Chat Completions and Responses API), Anthropic, Gemini, LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, CrewAI, MCP and OpenTelemetry traces (:doc:`frameworks`)
* **CLI, Python API and GitHub Action**: Command-line interface, programmatic usage and CI gates
* **Rich Reports**: Console, HTML, Markdown, CSV and machine-readable JSON reports, plus a versioned record for evaluation harnesses
* **Extensible**: Easy to add custom metrics and validators

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   installation
   quickstart
   what_it_catches

.. toctree::
   :maxdepth: 1
   :caption: Who it's for

   for_server_authors
   for_agent_builders
   for_security_teams
   for_researchers

.. toctree::
   :maxdepth: 2
   :caption: Guides

   user_guide
   snapshot_testing
   matchers
   frameworks
   fluent_api
   behavior_safety
   honesty_checks
   llm_judge
   mcp_testing
   effect_probes
   fault_injection
   coding_sessions
   config_lint
   pinning_diff
   agent_harness
   contracts
   receipts
   comparing_runs
   ci
   extending
   comparison

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/index
   api/core
   api/adapters
   api/matchers
   api/metrics
   api/snapshots
   api/mcp
   api/rigor
   api/validators
   api/reports

.. toctree::
   :maxdepth: 1
   :caption: Development

   contributing
   changelog

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
