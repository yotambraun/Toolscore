Changelog
=========

All notable changes to Toolscore will be documented in this file.

The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_,
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.

[Unreleased]
------------

Added
^^^^^

* Comprehensive test suite with 83% coverage
* ReadTheDocs documentation with Sphinx
* Support for ``rows_affected``, ``rowcount``, and ``count`` fields in SQLValidator

Changed
^^^^^^^

* Improved SQLValidator to handle more database field names

[0.1.0] - 2025-10-11
--------------------

Initial release of Toolscore.

Added
^^^^^

* Core evaluation engine for LLM tool usage
* Support for OpenAI, Anthropic, and custom trace formats
* Comprehensive metrics suite:
  * Tool invocation accuracy
  * Tool selection accuracy
  * Sequence edit distance
  * Argument matching F1 score
  * Redundant call rate
  * Side-effect validation
  * Latency and cost attribution
* Side-effect validators for HTTP, filesystem, and database operations
* CLI interface with ``eval`` and ``validate`` commands
* Python API for programmatic use
* JSON and HTML report generation
* Example scripts and traces
* Complete test suite
* Type hints and mypy support
* Ruff linting configuration
* Apache 2.0 license
