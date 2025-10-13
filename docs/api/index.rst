API Reference
=============

This section contains the complete API documentation for Toolscore.

.. toctree::
   :maxdepth: 2

   core
   adapters
   metrics
   validators
   reports

Overview
--------

Toolscore provides a simple, Pythonic API for evaluating LLM tool usage. The main entry point is the :func:`~toolscore.evaluate_trace` function, which handles loading traces, computing metrics, and returning results.

Basic Usage
-----------

.. code-block:: python

   from toolscore import evaluate_trace

   result = evaluate_trace(
       gold_file="gold_calls.json",
       trace_file="trace.json",
       format="auto"
   )

   print(f"Accuracy: {result.metrics['selection_accuracy']:.2%}")

Main Components
---------------

* :doc:`core` - Core evaluation logic
* :doc:`adapters` - Trace format adapters (OpenAI, Anthropic, custom)
* :doc:`metrics` - Metric calculators (accuracy, sequence, arguments, etc.)
* :doc:`validators` - Side-effect validators (HTTP, filesystem, database)
* :doc:`reports` - Report generators (JSON, HTML)

Quick Reference
---------------

Core Functions
^^^^^^^^^^^^^^

.. currentmodule:: toolscore

.. autosummary::
   :nosignatures:

   evaluate_trace
   load_gold_standard
   load_trace

Adapters
^^^^^^^^

.. currentmodule:: toolscore.adapters

.. autosummary::
   :nosignatures:

   OpenAIAdapter
   AnthropicAdapter
   CustomAdapter
   ToolCall

Metrics
^^^^^^^

.. currentmodule:: toolscore.metrics

.. autosummary::
   :nosignatures:

   calculate_invocation_accuracy
   calculate_selection_accuracy
   calculate_edit_distance
   calculate_argument_f1
   calculate_redundant_call_rate
   calculate_side_effect_success_rate
   calculate_latency
   calculate_cost_attribution

Validators
^^^^^^^^^^

.. currentmodule:: toolscore.validators

.. autosummary::
   :nosignatures:

   HTTPValidator
   FileSystemValidator
   SQLValidator

Reports
^^^^^^^

.. currentmodule:: toolscore.reports

.. autosummary::
   :nosignatures:

   generate_json_report
   generate_html_report
