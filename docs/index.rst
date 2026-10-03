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

**Toolscore** is a Python package for evaluating LLM tool usage against gold standard specifications. It helps developers benchmark different models, validate agent behavior, and track improvements in function calling accuracy over time.

What is Toolscore?
------------------

Toolscore evaluates LLM tool usage - it doesn't call LLM APIs directly. Think of it as a testing framework for function-calling agents:

✅ **Evaluates** tool usage traces from OpenAI, Anthropic, Gemini, agent frameworks, recorded MCP sessions, OpenTelemetry spans, or custom sources

✅ **Compares** actual behavior against expected gold standards

✅ **Reports** detailed metrics on accuracy, efficiency, and correctness, plus failed calls, leaked credentials and forbidden calls

✅ **Grades and lints** MCP servers, including references to missing tools and tool poisoning

❌ **Does NOT** call LLM APIs or execute tools (you capture traces separately)

Quick Start
-----------

.. code-block:: bash

   pip install tool-scorer

   # Run evaluation
   toolscore eval examples/gold_calls.json examples/trace_openai.json --html report.html

   # Grade an MCP server
   toolscore mcp test "python my_server.py"

Key Features
------------

* **Comprehensive Metrics Suite**: Tool invocation accuracy, selection accuracy, sequence edit distance, argument matching, redundant and repeated calls, required calls completed, and side-effect validation
* **Behavior and Safety Checks**: Failed calls, blind retries, credentials passed into tool arguments, and forbidden-call policies, with a CI gate (:doc:`behavior_safety`)
* **Snapshot Testing**: Record, approve and replay your agent's tool calls in pytest (:doc:`snapshot_testing`)
* **MCP Scorecard, Lint and Recorder**: Grade any MCP server, lint it for missing-tool references and tool poisoning, and record real sessions (:doc:`mcp_testing`)
* **Native Everywhere**: OpenAI, Anthropic, Gemini, LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, CrewAI, MCP and OpenTelemetry traces (:doc:`frameworks`)
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

.. toctree::
   :maxdepth: 2
   :caption: Guides

   user_guide
   snapshot_testing
   matchers
   frameworks
   fluent_api
   behavior_safety
   llm_judge
   mcp_testing
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
