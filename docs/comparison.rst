Toolscore vs. Other Tools
=========================

"Should I use Toolscore or DeepEval / RAGAS / LangSmith?" Usually the answer is
**both** — they solve different problems. This page is an honest map of where
Toolscore fits, and where it deliberately does not.

.. contents::
   :local:
   :depth: 1


The short version
-----------------

**Toolscore is a deterministic, local CI gate for tool-calling behavior.** It
takes a captured agent trace (or a live agent call) and checks the *tool calls*
against an expected specification or an approved snapshot — exactly, offline, and
fast. It is the unit test that fails your pull request when the agent stops
calling the right tool with the right arguments.

The other tools listed here are primarily **evaluation/observability
platforms**: LLM-judge-centric scoring of answer quality, dashboards, and
production trace collection. They answer "is the agent's *output* good, in
aggregate, over time?" — a different and complementary question.

You typically use a platform to observe and grade production quality, and
Toolscore to lock down tool-calling correctness in CI so regressions never ship.


What the others are
-------------------

* **DeepEval** — an LLM-evaluation framework (often described as "Pytest for
  LLMs"). Strong on LLM-judged answer-quality metrics (faithfulness, relevancy,
  hallucination, G-Eval), RAG metrics, and red-teaming. Most metrics call an LLM.
* **RAGAS** — focused on retrieval-augmented-generation quality: context
  precision/recall, faithfulness, answer relevancy. LLM-judge-centric by design.
* **LangSmith / Phoenix / MLflow (tracing+evals)** — observability platforms.
  They capture production traces, provide dashboards and datasets, and run
  (often LLM-judged) evaluations over them. Their center of gravity is
  *production telemetry and aggregate quality*, not a local pass/fail tool-call
  gate.

None of these are "wrong" — they are simply aimed at output quality and
observability, while Toolscore is aimed at deterministic tool-call correctness.


Feature comparison
------------------

.. list-table::
   :header-rows: 1
   :widths: 30 18 18 17 17

   * - Dimension
     - Toolscore
     - DeepEval
     - RAGAS
     - LangSmith / Phoenix / MLflow
   * - Deterministic scoring
     - Yes (core)
     - Partial (LLM-judged)
     - Mostly LLM-judged
     - Partial
   * - Runs fully offline (no API key)
     - Yes
     - Rarely (most metrics need an LLM)
     - No (needs an LLM)
     - Partial (tracing yes; LLM evals no)
   * - Cost per run
     - Free (no LLM calls)
     - LLM-metered
     - LLM-metered
     - Platform + LLM-metered
   * - CI-native pass/fail gate
     - Yes (built for it)
     - Yes
     - Via wrappers
     - Possible, not the focus
   * - Snapshot testing of tool calls
     - **Yes**
     - No
     - No
     - No
   * - MCP server testing / scorecard
     - **Yes**
     - No
     - No
     - No
   * - Tool-call / function-calling focus
     - **Primary**
     - Secondary
     - No (RAG-focused)
     - Secondary
   * - LLM-as-a-judge (semantic)
     - Optional add-on
     - Core
     - Core
     - Core
   * - Agent-framework coverage
     - Broad (OpenAI, Anthropic, Gemini, LangGraph, Pydantic AI, OpenAI Agents,
       Claude Agent SDK, CrewAI, MCP)
     - Broad
     - RAG pipelines
     - Broad
   * - Production observability / dashboards
     - **No** — by design
     - Limited
     - No
     - **Yes** (their core)
   * - Live production trace collection
     - **No** — by design
     - No
     - No
     - **Yes** (their core)

Where the table says **No — by design** for Toolscore, it is being honest:
Toolscore does **not** collect production traces, render dashboards, or do
observability. It is a library and CLI you run in development and CI. If you need
production telemetry and trend dashboards, pair it with one of the platforms.


When to reach for Toolscore
---------------------------

* You want a **fast, deterministic CI check** that the agent calls the right
  tools with the right arguments — no API key, no LLM cost, no flakiness.
* You want **snapshot tests** for agent behavior ("Jest snapshots for tool
  calls"): record once, approve, fail on drift. See :doc:`snapshot_testing`.
* You are building or shipping an **MCP server** and want a one-command
  test/lint/scorecard. See :doc:`mcp_testing`.
* You want to assert tool-calling behavior across **many frameworks** with one
  small API. See :doc:`frameworks` and :doc:`fluent_api`.

When to reach for a platform instead (or as well)
-------------------------------------------------

* You need to grade **answer/output quality** (faithfulness, relevancy,
  hallucination) — that is squarely DeepEval / RAGAS / G-Eval territory.
* You need **production observability**: trace collection, dashboards, latency
  and cost trends, dataset curation — that is LangSmith / Phoenix / MLflow.

The two are complementary. Toolscore even offers an optional :doc:`LLM judge
<llm_judge>` for the cases where syntactic matching is too strict — but it stays
opt-in, because the whole point of Toolscore is the deterministic gate.
