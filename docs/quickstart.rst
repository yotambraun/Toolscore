Quick Start
===========

This guide gets you to a green tool-call test in about 60 seconds, then covers
the rest of the API.

Install Toolscore
-----------------

.. code-block:: bash

   pip install tool-scorer

The fastest path: ``toolscore init`` + snapshots
------------------------------------------------

``toolscore init`` detects your agent framework and scaffolds a working pytest
suite plus an optional CI workflow — so your first run records a snapshot and
passes immediately.

1. Scaffold a test suite
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   toolscore init                 # auto-detects your framework, prompts to confirm
   toolscore init --yes           # accept the detected framework non-interactively
   toolscore init --framework langgraph   # or pick one explicitly

This writes ``tests/test_agent_tools.py`` (a passing suite wired to a snapshot),
``.toolscore/snapshots/`` (your reviewed baselines live here), and
``.github/workflows/toolscore.yml`` (unless ``--no-ci``).

2. Run pytest — the first run records a snapshot
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Edit the ``# TODO: import your agent`` block to call your real agent, then:

.. code-block:: bash

   pytest

The ``toolscore_snapshot`` fixture records the agent's tool calls into a
*pending* snapshot and warns. Nothing is asserted yet — there is no baseline to
compare against.

3. Review and approve the snapshot
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   toolscore snapshots list          # see what was recorded
   toolscore snapshots show <name>   # inspect the tool calls
   toolscore approve --all           # lock them in as the baseline

From now on every run replays against the approved baseline and **fails on
drift**. When the behavior changes on purpose, re-record with
``pytest --toolscore-update`` (or ``toolscore record --update -- pytest``) and
commit the updated snapshot file. See :doc:`snapshot_testing` for the full story.

The one-line assertion
^^^^^^^^^^^^^^^^^^^^^^^^

If you would rather assert against an explicit spec than a recorded snapshot:

.. code-block:: python

   import toolscore

   toolscore.assert_tools(
       expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
       actual=my_agent("weather in NYC"),   # raw provider response — auto-detected
       min_score=0.9,
   )

Evaluating captured traces
--------------------------

Toolscore can also score pre-captured trace files from the command line:

.. code-block:: bash

   tool-scorer eval examples/gold_calls.json examples/trace_openai.json --html report.html

Console output shows the metrics; open ``report.html`` for a detailed breakdown.

Basic Usage
-----------

Command Line Interface
^^^^^^^^^^^^^^^^^^^^^^

Evaluate a trace:

.. code-block:: bash

   tool-scorer eval gold_calls.json trace.json

Generate both JSON and HTML reports:

.. code-block:: bash

   tool-scorer eval gold_calls.json trace.json --html report.html

Specify trace format explicitly:

.. code-block:: bash

   tool-scorer eval gold_calls.json trace.json --format openai

Validate trace file format:

.. code-block:: bash

   tool-scorer validate trace.json

Python API (In-Memory)
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from toolscore import evaluate

   result = evaluate(
       expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
       actual=[{"tool": "get_weather", "args": {"city": "NYC"}}],
   )
   print(result.score)  # 1.0

Pass raw LLM provider responses directly — auto-detected:

.. code-block:: python

   from openai import OpenAI
   from toolscore import evaluate

   client = OpenAI()
   response = client.chat.completions.create(model="gpt-4o", messages=[...], tools=[...])

   # No from_openai() needed — auto-detected!
   result = evaluate(expected=[...], actual=response)

Python API (File-Based)
^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from toolscore import evaluate_trace

   result = evaluate_trace(
       gold_file="gold_calls.json",
       trace_file="trace.json",
       format="auto"
   )
   print(f"Selection Accuracy: {result.metrics['selection_accuracy']:.2%}")

Creating Gold Standards
-----------------------

A gold standard defines the expected tool calls for a task. Create a ``gold_calls.json`` file:

.. note::
   **Omitting ``args`` means "do not check arguments"** — the tool must be
   called, but any arguments are accepted. An explicit ``"args": {}`` means
   "expect the tool to be called with **no** arguments." See
   :doc:`matchers` for the full contract and for matchers like ``ANY`` and
   ``Regex`` that assert on argument *shape* instead of exact values.


.. code-block:: json

   [
     {
       "tool": "make_file",
       "args": {
         "filename": "poem.txt",
         "lines_of_text": ["Roses are red,", "Violets are blue."]
       },
       "side_effects": {
         "file_exists": "poem.txt"
       },
       "description": "Create a file with a poem"
     }
   ]

Supported Trace Formats
------------------------

OpenAI Format
^^^^^^^^^^^^^

.. code-block:: json

   [
     {
       "role": "assistant",
       "function_call": {
         "name": "get_weather",
         "arguments": "{\"location\": \"Boston\"}"
       }
     }
   ]

Anthropic Format
^^^^^^^^^^^^^^^^

.. code-block:: json

   [
     {
       "role": "assistant",
       "content": [
         {
           "type": "tool_use",
           "id": "toolu_123",
           "name": "search",
           "input": {"query": "Python"}
         }
       ]
     }
   ]

Custom Format
^^^^^^^^^^^^^

.. code-block:: json

   {
     "calls": [
       {
         "tool": "read_file",
         "args": {"path": "data.txt"},
         "result": "file contents"
       }
     ]
   }

Next Steps
----------

* Read the :doc:`user_guide` for detailed usage
* Lock in behavior with :doc:`snapshot_testing`
* Assert on argument shape with :doc:`matchers`
* Pass raw framework responses with the :doc:`frameworks` extractors
* Test an MCP server with :doc:`mcp_testing` -- or run ``toolscore demo`` to grade a bundled sample server in seconds (no setup, no API key)
* Add semantic scoring with the :doc:`llm_judge`
* Explore example scripts in the `examples/ directory <https://github.com/yotambraun/Toolscore/tree/main/examples>`_
* Check out the complete :doc:`api/index`
* Learn how to :doc:`contributing` to Toolscore
