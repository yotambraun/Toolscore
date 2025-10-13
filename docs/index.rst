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

✅ **Evaluates** existing tool usage traces from OpenAI, Anthropic, or custom sources

✅ **Compares** actual behavior against expected gold standards

✅ **Reports** detailed metrics on accuracy, efficiency, and correctness

❌ **Does NOT** call LLM APIs or execute tools (you capture traces separately)

Quick Start
-----------

.. code-block:: bash

   pip install tool-scorer

   # Run evaluation
   tool-scorer eval examples/gold_calls.json examples/trace_openai.json --html report.html

Key Features
------------

* **Comprehensive Metrics Suite**: Tool invocation accuracy, selection accuracy, sequence edit distance, argument matching, redundant calls, and side-effect validation
* **Multiple Trace Adapters**: Built-in support for OpenAI, Anthropic Claude, and custom JSON formats
* **CLI and Python API**: Command-line interface and programmatic usage
* **Rich Reports**: Interactive HTML and machine-readable JSON reports
* **Extensible**: Easy to add custom metrics and validators

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   installation
   quickstart
   user_guide

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/index
   api/core
   api/adapters
   api/metrics
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
