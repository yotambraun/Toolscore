Quick Start
===========

This guide will get you started with Toolscore in 5 minutes.

5-Minute Tutorial
-----------------

1. Install Toolscore
^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   pip install tool-scorer

2. Run Your First Evaluation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use the included example files:

.. code-block:: bash

   tool-scorer eval examples/gold_calls.json examples/trace_openai.json --html report.html

3. View Results
^^^^^^^^^^^^^^^

The console output shows:

.. code-block:: text

   Invocation Accuracy: 100.00%
   Selection Accuracy: 100.00%
   Sequence Accuracy: 100.00%

Open ``report.html`` in your browser for detailed analysis.

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

Python API
^^^^^^^^^^

.. code-block:: python

   from toolscore import evaluate_trace

   # Run evaluation
   result = evaluate_trace(
       gold_file="gold_calls.json",
       trace_file="trace.json",
       format="auto"  # auto-detect format
   )

   # Access metrics
   print(f"Invocation Accuracy: {result.metrics['invocation_accuracy']:.2%}")
   print(f"Selection Accuracy: {result.metrics['selection_accuracy']:.2%}")

   sequence = result.metrics['sequence_metrics']
   print(f"Sequence Accuracy: {sequence['sequence_accuracy']:.2%}")

   arguments = result.metrics['argument_metrics']
   print(f"Argument F1: {arguments['f1']:.2%}")

Creating Gold Standards
-----------------------

A gold standard defines the expected tool calls for a task. Create a ``gold_calls.json`` file:

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
* Explore example scripts in the `examples/ directory <https://github.com/yotambraun/Toolscore/tree/main/examples>`_
* Check out the complete :doc:`api/index`
* Learn how to :doc:`contributing` to Toolscore
