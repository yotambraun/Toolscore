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

Supported formats: ``"auto"``, ``"openai"``, ``"anthropic"``, ``"custom"``

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
       "http_ok": true,           # Any 2xx status
       "http_status": 200         # Specific status code
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
       "sql_rows": 1              # Expected rows affected
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
