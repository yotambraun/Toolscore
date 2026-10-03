Framework Integration Guide
===========================

Toolscore ships with extractors for the most popular agent frameworks so you
can pass raw responses directly to :func:`toolscore.evaluate` or
:func:`toolscore.test_agent` without manually building lists of tool-call
dicts.

All extractors return ``list[dict]`` with ``"tool"`` and ``"args"`` keys — the
same format accepted by :func:`toolscore.evaluate`. Where the source records
them, calls also carry ``result``, ``error``, ``is_error`` and ``duration``,
which feed the :doc:`behavior_safety`.

.. contents::
   :local:
   :depth: 1


LangGraph
---------

Use :func:`toolscore.from_langgraph` (or ``auto_extract`` — it is
auto-detected) to extract tool calls from a LangGraph agent's final state.

Accepted inputs:

- A final-state **dict** or **object** with a ``messages`` key/attribute
- A plain **list of messages**

Each message whose ``tool_calls`` attribute/key is non-empty contributes its
entries.  Order across messages is preserved.

.. code-block:: python

    from langgraph.prebuilt import create_react_agent
    from toolscore import evaluate
    from toolscore.integrations import from_langgraph

    agent = create_react_agent(model, tools)
    state = agent.invoke({"messages": [("user", "What's the weather in NYC?")]})

    expected = [{"tool": "get_weather", "args": {"city": "NYC"}}]
    result = evaluate(expected=expected, actual=from_langgraph(state))
    print(result.score)

You can also use :func:`toolscore.test_agent` directly because
:func:`toolscore.auto_extract` recognises the LangGraph state shape
automatically:

.. code-block:: python

    import toolscore

    result = toolscore.test_agent(
        agent=lambda prompt: agent.invoke({"messages": [("user", prompt)]}),
        input="What's the weather in NYC?",
        expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
        min_score=0.9,
    )


Pydantic AI
-----------

Use :func:`toolscore.from_pydantic_ai` to extract tool calls from a Pydantic
AI ``AgentRunResult`` or a list of messages.

Accepted inputs:

- An **AgentRunResult** (duck-typed: must have a callable ``all_messages()``)
- A plain **list of messages**

Parts with ``part_kind == "tool-call"`` (or class name ``ToolCallPart``) are
collected; ``args_as_dict()`` is called when available, otherwise ``args`` is
used (JSON string is parsed automatically).

.. code-block:: python

    from pydantic_ai import Agent
    from toolscore import evaluate
    from toolscore.integrations import from_pydantic_ai

    agent = Agent("openai:gpt-4o", tools=[get_weather])
    run_result = agent.run_sync("What's the weather in NYC?")

    expected = [{"tool": "get_weather", "args": {"city": "NYC"}}]
    result = evaluate(expected=expected, actual=from_pydantic_ai(run_result))
    print(result.score)

Or use :func:`toolscore.test_agent_async` for async Pydantic AI agents:

.. code-block:: python

    import toolscore

    async def my_agent(prompt: str):
        result = await agent.run(prompt)
        return result          # auto_extract will detect it

    result = await toolscore.test_agent_async(
        agent=my_agent,
        input="What's the weather in NYC?",
        expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
        min_score=0.9,
    )


OpenAI Agents SDK
-----------------

Use :func:`toolscore.from_openai_agents` to extract tool calls from an OpenAI
Agents SDK ``RunResult``.

Accepted inputs:

- A **RunResult** (duck-typed: must have a ``new_items`` attribute)
- A plain **list of items**

Items with ``type == "tool_call_item"`` are collected; each item's
``raw_item.name`` and ``raw_item.arguments`` (JSON string) provide the tool
name and parsed arguments.

.. code-block:: python

    from agents import Agent, Runner
    from toolscore import evaluate
    from toolscore.integrations import from_openai_agents

    agent = Agent(name="MyAgent", tools=[get_weather])
    run_result = Runner.run_sync(agent, "What's the weather in NYC?")

    expected = [{"tool": "get_weather", "args": {"city": "NYC"}}]
    result = evaluate(expected=expected, actual=from_openai_agents(run_result))
    print(result.score)

For async usage:

.. code-block:: python

    import toolscore

    async def my_agent(prompt: str):
        return await Runner.run(agent, prompt)

    result = await toolscore.test_agent_async(
        agent=my_agent,
        input="What's the weather in NYC?",
        expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
        min_score=0.9,
    )


Claude Agent SDK
----------------

Use :func:`toolscore.from_claude_agent_sdk` to extract tool calls from a list
of Claude Agent SDK messages.

Accepted input:

- A **list of messages** (dicts or objects) — each message's ``content``
  blocks are inspected; blocks with ``type == "tool_use"`` yield calls via
  ``name`` + ``input``.

.. code-block:: python

    import anthropic
    from toolscore import evaluate
    from toolscore.integrations import from_claude_agent_sdk

    client = anthropic.Anthropic()
    messages = []
    # … run your agent loop, appending messages …

    expected = [{"tool": "web_search", "args": {"query": "python async"}}]
    result = evaluate(expected=expected, actual=from_claude_agent_sdk(messages))
    print(result.score)

.. note::

    :func:`toolscore.from_anthropic` handles a **single** Anthropic
    ``Message`` response.  Use :func:`~toolscore.from_claude_agent_sdk` when
    you have a **list** of messages collected from a multi-turn agent loop.


CrewAI (experimental)
---------------------

Use :func:`toolscore.from_crewai` to extract tool calls from a CrewAI result.

.. warning::

    This extractor is **experimental**.  CrewAI does not expose a stable
    structured trace API; extraction is best-effort and may not cover all
    CrewAI versions or configurations.

Accepted inputs:

- A **list** of tool-result entries with ``tool_name`` + ``tool_args`` keys/attrs
- An **object or dict** with a ``tools_results`` attribute/key

.. code-block:: python

    from crewai import Crew, Agent, Task
    from toolscore import evaluate
    from toolscore.integrations import from_crewai

    crew = Crew(agents=[...], tasks=[...])
    crew_result = crew.kickoff()

    # crew_result.tools_results is a list of tool invocation records
    expected = [{"tool": "search", "args": {"q": "AI agents"}}]
    result = evaluate(expected=expected, actual=from_crewai(crew_result))
    print(result.score)

OpenTelemetry (any instrumented framework)
------------------------------------------

Frameworks and observability platforms that follow the OpenTelemetry semantic
conventions for generative AI record each tool execution as a span. Use
:func:`toolscore.from_otel` (or pass the spans straight to
:func:`toolscore.evaluate`; they are auto-detected) to turn those spans into
tool calls, so any instrumented agent can be scored without a dedicated
extractor.

Recognized spans:

- GenAI ``execute_tool`` spans: ``gen_ai.operation.name == "execute_tool"`` with
  ``gen_ai.tool.name`` and, when recorded, ``gen_ai.tool.call.arguments``,
  ``gen_ai.tool.call.result`` and ``gen_ai.tool.call.id``
- MCP client spans: ``mcp.method.name == "tools/call"`` with
  ``gen_ai.tool.name`` (the call id comes from ``jsonrpc.request.id``)

Other spans (agent, chat, embeddings) are skipped. A call failed when the span
has ``error.type`` or an ERROR status. Calls are returned in start-time order
with ``tool``, ``args``, ``result``, ``is_error``, ``error``, ``duration``
(seconds) and ``id``; arguments and results recorded as JSON strings are
decoded.

Accepted inputs:

- An **OTLP JSON export** (``{"resourceSpans": [...]}``), as written by OTLP/JSON
  exporters and the collector's file exporter
- A **list of span dicts**
- A **list of SDK span objects** (``ReadableSpan``), for example from an
  ``InMemorySpanExporter`` in tests

.. code-block:: python

    import json
    from toolscore import evaluate, from_otel

    spans = json.load(open("examples/otel_genai_spans.json"))
    for call in from_otel(spans):
        print(call["tool"], call["is_error"], call["error"])

    result = evaluate(
        expected=[{"tool": "search_orders"}, {"tool": "issue_refund"}, {"tool": "send_email"}],
        actual=spans,
    )
    print(result.required_call_recall)   # 0.67: the refund call failed

From the command line, OTLP JSON files are auto-detected, or pass
``--format otel``:

.. code-block:: bash

    toolscore eval gold.json spans.json --format otel

.. note::

    Tool arguments and results are opt-in attributes in the conventions
    (they may contain sensitive data). Without them, Toolscore still scores
    tool selection, order and failures, but not arguments.

MCP sessions
------------

To score what an agent did against an MCP server, record the session with
``toolscore mcp record`` (see :ref:`recording-sessions`) and evaluate the file;
recorded sessions and plain JSON-RPC 2.0 message lists are auto-detected:

.. code-block:: bash

    toolscore eval gold.json session.json
