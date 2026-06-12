Extending Toolscore
===================

Toolscore ships adapters for OpenAI, Anthropic, Gemini, LangChain, MCP, and a
flexible generic/custom format, plus duck-typed extractors for the major agent
frameworks (see :doc:`frameworks`). When your trace format is none of those, you
write a small adapter. This page covers the adapter contract and how to feed a
custom format into an evaluation.

.. contents::
   :local:
   :depth: 1


When you need a custom adapter
------------------------------

Reach for a custom adapter only when:

* your trace shape is not OpenAI / Anthropic / Gemini / LangChain / MCP, **and**
* it does not already fit the lenient :class:`~toolscore.adapters.CustomAdapter`
  (which accepts ``{"calls": [...]}`` or a bare list of objects with a
  ``tool``/``name``/``function`` field and ``args``/``arguments``/``input``).

If a quick reshape into ``[{"tool": ..., "args": {...}}]`` is easy, do that and
pass it straight to :func:`toolscore.evaluate` — you may not need an adapter at
all.


The ``BaseAdapter`` contract
----------------------------

Subclass :class:`toolscore.adapters.BaseAdapter` and implement one method,
``parse()``, which converts raw trace data into a list of
:class:`~toolscore.adapters.ToolCall` objects in chronological order.

.. code-block:: python

   from typing import Any
   from toolscore.adapters import BaseAdapter, ToolCall


   class MyFrameworkAdapter(BaseAdapter):
       """Parse my framework's ``{"events": [...]}`` trace shape."""

       def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
           # Reuse the base validator: raises ValueError for None / non-(dict|list).
           self._validate_trace_data(trace_data)

           events = trace_data["events"] if isinstance(trace_data, dict) else trace_data
           calls: list[ToolCall] = []
           for event in events:
               if event.get("kind") != "tool_call":
                   continue  # skip non-tool events
               calls.append(
                   ToolCall(
                       tool=event["op"],            # required, non-empty
                       args=event.get("params", {}),
                       result=event.get("result"),  # optional
                   )
               )
           return calls

Contract details:

* **Return type** is ``list[ToolCall]``, ordered as the calls happened.
* :class:`~toolscore.adapters.ToolCall` requires a non-empty ``tool`` name
  (an empty name raises ``ValueError``). ``args``, ``result``, ``timestamp``,
  ``duration``, ``cost``, and ``metadata`` are optional.
* **Mind the ``args is None`` semantics.** For an *actual/trace* call, ``None``
  means "no arguments recorded" and is treated as empty. For a *gold/expected*
  call, ``None`` (omitted ``args``) means "do not check arguments". Adapters that
  parse real traces should set a concrete dict (``{}`` when there are none) so
  the distinction stays clean. See the omitted-args contract in :doc:`matchers`.
* ``parse()`` should raise ``ValueError`` for malformed input.
* ``self._validate_trace_data(...)`` is a provided helper that rejects ``None``
  and non-``dict``/``list`` inputs — call it first.


Using a custom adapter
----------------------

Once parsed, convert the ``ToolCall`` list into the ``{"tool", "args"}`` dicts
that :func:`toolscore.evaluate` expects, and evaluate:

.. code-block:: python

   from toolscore import evaluate

   raw = {"events": [{"kind": "tool_call", "op": "search", "params": {"q": "python"}}]}
   tool_calls = MyFrameworkAdapter().parse(raw)

   actual = [{"tool": c.tool, "args": c.args or {}} for c in tool_calls]
   result = evaluate(
       expected=[{"tool": "search", "args": {"q": "python"}}],
       actual=actual,
   )
   print(result.score)  # ~1.0

.. note::
   The file-based :func:`toolscore.load_trace` / :func:`toolscore.evaluate_trace`
   ``format=`` argument selects from the **built-in** adapters
   (``auto``, ``openai``, ``anthropic``, ``gemini``, ``mcp``, ``langchain``,
   ``custom``). ``format="custom"`` maps to the generic
   :class:`~toolscore.adapters.CustomAdapter`, not to your subclass. To use your
   own adapter, parse the raw data yourself (as above) and pass the resulting
   dicts to :func:`toolscore.evaluate`, or first massage your trace into the
   generic ``custom`` shape and load it with ``format="custom"``.

Tip: if your format is close to an existing one, the lenient
:class:`~toolscore.adapters.CustomAdapter` already tries multiple key names
(``tool``/``name``/``function`` and ``args``/``arguments``/``input``), so a
minimal reshape may let you skip a custom class entirely.


Request an adapter
------------------

If a framework or trace format is popular enough to belong in Toolscore itself,
open an **Adapter / Framework Support Request** so it can ship for everyone:

* Use the issue template:
  https://github.com/yotambraun/Toolscore/issues/new?template=adapter_request.yml
* Include a tiny **redacted** sample of the raw response/trace shape, the
  framework name and version, and how you currently capture the trace.

A captured sample is the single most useful thing you can attach — it lets the
maintainers build and test the extractor against real data.
