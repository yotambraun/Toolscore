User Guide
==========

This guide covers common usage patterns and best practices for Toolscore.

Understanding Metrics
---------------------

Toolscore calculates several metrics to evaluate LLM tool usage:

Tool Invocation Accuracy
^^^^^^^^^^^^^^^^^^^^^^^^^

Measures whether the agent invoked tools when needed and refrained when not needed.

* **1.0**: Perfect - invoked exactly when required
* **< 1.0**: Missed some tool calls or invoked unnecessarily

Tool Selection Accuracy
^^^^^^^^^^^^^^^^^^^^^^^

Proportion of tool calls that match expected tool names.

* **1.0**: All tool names match gold standard
* **0.5**: Half of the tools were correct
* **0.0**: Wrong tools chosen

Sequence Edit Distance
^^^^^^^^^^^^^^^^^^^^^^

Levenshtein distance between expected and actual tool call sequences.

* **Edit distance**: Number of insertions/deletions/substitutions needed
* **Sequence accuracy**: 1 - (normalized edit distance)

Argument Match F1 Score
^^^^^^^^^^^^^^^^^^^^^^^

Evaluates how well arguments match.

* **Precision**: Of the arguments provided, how many were correct?
* **Recall**: Of the required arguments, how many were provided?
* **F1**: Harmonic mean of precision and recall

Redundant Call Rate
^^^^^^^^^^^^^^^^^^^

Percentage of unnecessary or duplicate tool calls.

* **0.0**: No redundant calls
* **> 0.0**: Some calls were unnecessary

Side-Effect Success Rate
^^^^^^^^^^^^^^^^^^^^^^^^^

Proportion of validated side-effects that succeeded.

Only applicable if you specify ``side_effects`` in your gold standard.

LLM-as-a-judge Semantic Correctness (Optional)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

An optional LLM judge scores *semantic* equivalence beyond exact string
matching — great for catching cases where tool names differ but intentions match
(``search_web`` vs ``web_search``). It supports OpenAI, Anthropic, Gemini, and any
OpenAI-compatible endpoint (Ollama/vLLM/Groq).

.. code-block:: python

   # Requires the provider's extra, e.g. pip install tool-scorer[llm]
   # and the matching API-key env var (OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_API_KEY)
   from toolscore.metrics.llm_judge import calculate_semantic_correctness, JudgeConfig

   # A bare model-name string is shorthand for JudgeConfig(model=...).
   result = calculate_semantic_correctness(gold_calls, trace_calls, judge="gpt-4o-mini")

   # Or full control via JudgeConfig (provider inferred from the model name):
   result = calculate_semantic_correctness(
       gold_calls, trace_calls,
       judge=JudgeConfig(model="claude-3-5-haiku-latest"),
   )

   print(f"Semantic Score: {result['semantic_score']:.2%}")
   print(f"Per-call scores: {result['per_call_scores']}")
   print(f"Explanations: {result['explanations']}")

.. note::
   The judge is now configured through a single ``judge=`` argument (a
   :class:`~toolscore.metrics.llm_judge.JudgeConfig`, a model-name string, or
   ``None``). The older ``model=`` / ``use_llm_judge=...`` keyword arguments have
   been removed. The file-based :func:`toolscore.evaluate_trace` also takes
   ``judge=`` (``True`` for the default config). See the :doc:`llm_judge` guide
   for provider inference, env-var keys, local endpoints, and CLI flags.

Scoring Semantics
-----------------

The in-memory :func:`toolscore.evaluate` (and ``assert_tools``, the snapshot
fixture, and the fluent ``expect()`` API) share three behaviors worth
understanding.

Omitted args vs ``{}``
^^^^^^^^^^^^^^^^^^^^^^^

**Omitting ``args`` means "do not check arguments"** — the tool must be called,
but whatever arguments the agent passed are accepted. An explicit ``"args": {}``
means "expect the tool to be called with **no** arguments."

.. code-block:: python

   from toolscore import evaluate

   # Omitted args — tool-name-only. Any arguments are fine.
   evaluate(expected=[{"tool": "search"}],
            actual=[{"tool": "search", "args": {"q": "x"}}]).argument_f1   # 1.0

   # Explicit {} — "expect no arguments". The agent passed one → mismatch.
   evaluate(expected=[{"tool": "search", "args": {}}],
            actual=[{"tool": "search", "args": {"q": "x"}}]).argument_f1   # 0.0

See :doc:`matchers` for argument *shape* matchers (``ANY``, ``Regex``, …) and the
full contract.

Custom weights are renormalized
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The composite ``score`` is a weighted blend of ``selection_accuracy``,
``argument_f1``, ``sequence_accuracy``, and ``redundant_rate``. When you pass
``weights=``, your values are **merged with the defaults and then renormalized so
they sum to 1.0** before scoring — you do not have to make them add up yourself.

.. code-block:: python

   # Score on tool selection alone (other weights zeroed, then renormalized to 1.0).
   evaluate(
       expected=[{"tool": "search"}],
       actual=[{"tool": "search"}],
       weights={"selection_accuracy": 1.0, "argument_f1": 0.0,
                "sequence_accuracy": 0.0, "redundant_rate": 0.0},
   )

Unknown weight keys, negative/non-finite values, and an all-zero total are
rejected with a ``ValueError``.

Strict mode
^^^^^^^^^^^

By default argument comparison is lenient: ``1`` matches ``1.0`` and ``"NYC"``
matches ``" NYC "``. Pass ``strict=True`` to require pure equality (no int/float
coercion, no string stripping). Matchers run their own logic and are unaffected
by ``strict``.

.. code-block:: python

   evaluate(expected=[{"tool": "f", "args": {"n": 1}}],
            actual=[{"tool": "f", "args": {"n": 1.0}}]).argument_f1                 # 1.0
   evaluate(expected=[{"tool": "f", "args": {"n": 1}}],
            actual=[{"tool": "f", "args": {"n": 1.0}}], strict=True).argument_f1    # 0.0

Working with Trace Formats
---------------------------

Auto-Detection
^^^^^^^^^^^^^^

Toolscore can automatically detect the trace format:

.. code-block:: python

   result = evaluate_trace(
       gold_file="gold.json",
       trace_file="trace.json",
       format="auto"  # Auto-detect
   )

Explicit Format
^^^^^^^^^^^^^^^

For better performance, specify the format:

.. code-block:: python

   result = evaluate_trace(
       gold_file="gold.json",
       trace_file="trace_openai.json",
       format="openai"
   )

Supported formats: ``"auto"``, ``"openai"``, ``"anthropic"``, ``"langchain"``, ``"custom"``

Capturing Traces
----------------

From OpenAI
^^^^^^^^^^^

.. code-block:: python

   import json
   from openai import OpenAI

   client = OpenAI()

   response = client.chat.completions.create(
       model="gpt-4",
       messages=[{"role": "user", "content": "Create a file called test.txt"}],
       tools=[...],  # Your tool definitions
   )

   # Save trace
   trace = [{
       "role": "assistant",
       "tool_calls": [
           {
               "id": tc.id,
               "type": "function",
               "function": {
                   "name": tc.function.name,
                   "arguments": tc.function.arguments
               }
           }
           for tc in response.choices[0].message.tool_calls
       ]
   }]

   with open("trace_openai.json", "w") as f:
       json.dump(trace, f)

From Anthropic
^^^^^^^^^^^^^^

.. code-block:: python

   import json
   from anthropic import Anthropic

   client = Anthropic()

   message = client.messages.create(
       model="claude-3-5-sonnet-20241022",
       max_tokens=1024,
       tools=[...],  # Your tool definitions
       messages=[{"role": "user", "content": "Create a file called test.txt"}]
   )

   # Save trace
   trace = [{"role": "assistant", "content": message.content}]

   with open("trace_anthropic.json", "w") as f:
       json.dump(trace, f)

From LangChain
^^^^^^^^^^^^^^

Toolscore supports both legacy and modern LangChain formats:

.. code-block:: python

   import json
   from langchain.agents import AgentExecutor

   # Your LangChain agent execution
   result = agent_executor.invoke({"input": "Search for Python tutorials"})

   # Extract tool calls from result (legacy format)
   trace = []
   for step in result['intermediate_steps']:
       action, observation = step
       trace.append({
           "tool": action.tool,
           "tool_input": action.tool_input,
           "log": action.log
       })

   # Save trace
   with open("trace_langchain.json", "w") as f:
       json.dump(trace, f)

   # Evaluate
   result = evaluate_trace("gold.json", "trace_langchain.json", format="langchain")

Modern LangChain format (ToolCall):

.. code-block:: json

   [
     {
       "name": "search",
       "args": {"query": "Python tutorials"},
       "id": "call_123"
     }
   ]

Creating Effective Gold Standards
----------------------------------

Best Practices
^^^^^^^^^^^^^^

1. **Focus on required arguments**: Don't specify every detail, only what matters
2. **Think about intent**: Define what the agent SHOULD do, not what it COULD do
3. **Use side-effects**: Add critical validations (file creation, API calls, etc.)
4. **Be specific**: Clear tool names and argument values

Example Gold Standard
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: json

   [
     {
       "tool": "search_web",
       "args": {
         "query": "Python tutorials",
         "num_results": 10
       },
       "description": "Search for Python tutorials",
       "side_effects": {
         "http_ok": true
       }
     },
     {
       "tool": "summarize",
       "args": {
         "text": "..."
       },
       "description": "Summarize search results"
     }
   ]

Side-Effect Validation
----------------------

HTTP Validation
^^^^^^^^^^^^^^^

Validate HTTP requests succeeded:

.. code-block:: json

   {
     "tool": "make_request",
     "args": {"url": "https://api.example.com"},
     "side_effects": {
       "http_ok": true,
       "http_status": 200
     }
   }

Filesystem Validation
^^^^^^^^^^^^^^^^^^^^^

Validate files exist:

.. code-block:: json

   {
     "tool": "create_file",
     "args": {"filename": "output.txt"},
     "side_effects": {
       "file_exists": "output.txt"
     }
   }

Database Validation
^^^^^^^^^^^^^^^^^^^

Validate database operations:

.. code-block:: json

   {
     "tool": "insert_user",
     "args": {"name": "John", "email": "john@example.com"},
     "side_effects": {
       "sql_rows": 1
     }
   }

Generating Reports
------------------

JSON Reports
^^^^^^^^^^^^

Machine-readable format for programmatic access:

.. code-block:: bash

   tool-scorer eval gold.json trace.json --output results.json

.. code-block:: python

   from toolscore.reports import generate_json_report

   json_path = generate_json_report(result, "report.json")

HTML Reports
^^^^^^^^^^^^

Human-friendly format with visualization:

.. code-block:: bash

   tool-scorer eval gold.json trace.json --html report.html

.. code-block:: python

   from toolscore.reports import generate_html_report

   html_path = generate_html_report(result, "report.html")

Batch Evaluation
----------------

Evaluate multiple traces:

.. code-block:: python

   import glob
   from toolscore import evaluate_trace

   gold_file = "gold_standard.json"
   results = []

   for trace_file in glob.glob("traces/*.json"):
       result = evaluate_trace(gold_file, trace_file, format="auto")
       results.append({
           "file": trace_file,
           "accuracy": result.metrics['selection_accuracy']
       })

   # Find best performer
   best = max(results, key=lambda x: x['accuracy'])
   print(f"Best trace: {best['file']} ({best['accuracy']:.1%})")

End-to-End Agent Testing
------------------------

Use ``test_agent()`` to run an agent, extract tool calls, and evaluate in one call:

.. code-block:: python

   from toolscore import test_agent

   result = test_agent(
       agent=my_agent_fn,          # any callable returning an LLM response
       input="What's the weather?",
       expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
       min_score=0.9,              # optional: raises if below
   )

Data-Driven Testing with ``@toolscore.cases()``
------------------------------------------------

Parametrize pytest tests with a list of test-case dicts:

.. code-block:: python

   import toolscore

   @toolscore.cases([
       {"input": "weather NYC", "expected": [{"tool": "get_weather", "args": {"city": "NYC"}}]},
       {"input": "email bob",   "expected": [{"tool": "send_email", "args": {"to": "bob"}}]},
   ])
   def test_my_agent(input, expected):
       response = my_agent(input)
       toolscore.assert_tools(expected=expected, actual=response, min_score=0.9)

Pytest Integration
------------------

Toolscore includes a pytest plugin for seamless test integration. The plugin is automatically loaded when you install Toolscore.

Using Fixtures
^^^^^^^^^^^^^^

.. code-block:: python

   # test_my_agent.py
   def test_agent_accuracy(toolscore_eval, toolscore_assert):
       """Test that agent achieves minimum accuracy."""
       result = toolscore_eval("gold_calls.json", "trace.json")

       # Use built-in assertions
       toolscore_assert.assert_invocation_accuracy(result, threshold=0.9)
       toolscore_assert.assert_selection_accuracy(result, threshold=0.9)
       toolscore_assert.assert_argument_f1(result, min_f1=0.8)

Available Fixtures
^^^^^^^^^^^^^^^^^^

* ``toolscore_eval``: Run evaluations with automatic path resolution
* ``toolscore_assert``: Pre-built assertion helpers
* ``toolscore_assert_tools``: The ``assert_tools`` one-liner as a fixture
* ``toolscore_snapshot``: Record/approve/replay snapshots (see :doc:`snapshot_testing`)
* ``toolscore_gold_dir``: Path to gold standards directory
* ``toolscore_trace_dir``: Path to traces directory

Assertion Helpers
^^^^^^^^^^^^^^^^^

The ``toolscore_assert`` fixture provides:

* ``assert_invocation_accuracy(result, threshold, msg=None)``
* ``assert_selection_accuracy(result, threshold, msg=None)``
* ``assert_sequence_accuracy(result, threshold, msg=None)``
* ``assert_argument_f1(result, min_f1, msg=None)``
* ``assert_redundancy_below(result, max_rate, msg=None)``

Example Test Suite
^^^^^^^^^^^^^^^^^^

.. code-block:: python

   # tests/test_agent_performance.py
   import pytest

   def test_agent_meets_requirements(toolscore_eval, toolscore_assert):
       """Verify agent meets all accuracy requirements."""
       result = toolscore_eval("gold_standard.json", "agent_trace.json")

       # Multiple assertions
       toolscore_assert.assert_invocation_accuracy(result, 0.9)
       toolscore_assert.assert_selection_accuracy(result, 0.9)
       toolscore_assert.assert_argument_f1(result, 0.8)

   def test_agent_efficiency(toolscore_eval, toolscore_assert):
       """Verify agent doesn't make redundant calls."""
       result = toolscore_eval("gold_standard.json", "agent_trace.json")
       toolscore_assert.assert_redundancy_below(result, max_rate=0.1)

   def test_multiple_scenarios(toolscore_eval, toolscore_assert):
       """Test agent across multiple scenarios."""
       scenarios = [
           ("scenario1_gold.json", "scenario1_trace.json", 0.95),
           ("scenario2_gold.json", "scenario2_trace.json", 0.90),
           ("scenario3_gold.json", "scenario3_trace.json", 0.85),
       ]

       for gold, trace, min_acc in scenarios:
           result = toolscore_eval(gold, trace)
           toolscore_assert.assert_selection_accuracy(
               result, min_acc, f"Failed for {gold}"
           )

Run tests:

.. code-block:: bash

   pytest tests/ -v

Interactive Tutorials
---------------------

Toolscore includes Jupyter notebooks for hands-on learning:

1. **Quickstart Tutorial** (``examples/notebooks/01_quickstart.ipynb``)

   * 5-minute introduction to Toolscore
   * Load gold standards and traces
   * Run evaluations and interpret metrics
   * Generate HTML/JSON reports

2. **Custom Formats** (``examples/notebooks/02_custom_formats.ipynb``)

   * Work with custom trace formats
   * Create gold standards for custom workflows
   * Best practices for format design

3. **Advanced Metrics** (``examples/notebooks/03_advanced_metrics.ipynb``)

   * Deep dive into each metric
   * Real-world examples and scenarios
   * Metric selection guide
   * Tips for improving scores

Run locally:

.. code-block:: bash

   cd examples/notebooks
   jupyter notebook

Or open in `Google Colab <https://colab.research.google.com/>`_ for instant experimentation.

Tips and Tricks
---------------

1. **Start simple**: Begin with basic tool and args matching before adding side-effects
2. **Incremental testing**: Test individual components before full workflows
3. **Consistent formats**: Use the same trace format across evaluations
4. **Version control**: Track gold standards in git to see evolution
5. **Automate**: Integrate Toolscore into your CI/CD pipeline

Troubleshooting
---------------

Common Issues
^^^^^^^^^^^^^

**"Format detection failed"**
   Explicitly specify the format with ``--format``

**"No tool calls found"**
   Verify your trace file has the correct structure

**"Side-effect validation failed"**
   Check that files/resources actually exist before validation

**"Argument mismatch"**
   Gold standard arguments should match exactly (or use partial matching)

Getting Help
^^^^^^^^^^^^

* Check :doc:`api/index` for detailed API reference
* See `examples/ directory <https://github.com/yotambraun/Toolscore/tree/main/examples>`_ for working examples
* Open an issue on `GitHub <https://github.com/yotambraun/Toolscore/issues>`_
