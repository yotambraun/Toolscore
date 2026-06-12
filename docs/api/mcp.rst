MCP Module
==========

.. currentmodule:: toolscore.mcp

A standard-library-only client for Model Context Protocol (MCP) servers over the
stdio transport, plus the scorecard harness (scenario generation, execution,
linting, and A--F scoring). See :doc:`../mcp_testing` for the CLI guide and
:download:`the demo script <../../examples/mcp_scorecard_demo.py>` for
programmatic usage.

Client
------

.. autoclass:: MCPStdioClient
   :members:
   :undoc-members:

.. autoclass:: MCPToolDef
   :members:
   :undoc-members:

.. autoclass:: MCPToolResult
   :members:
   :undoc-members:

.. autoexception:: MCPError

.. autoexception:: MCPTimeoutError

Server configuration
--------------------

.. autoclass:: MCPServerSpec
   :members:
   :undoc-members:

.. autofunction:: load_mcp_config

Scorecard harness
-----------------

.. autofunction:: generate_scenarios

.. autofunction:: run_scenarios

.. autofunction:: lint_tools

.. autoclass:: Scenario
   :members:
   :undoc-members:

.. autoclass:: ScenarioResult
   :members:
   :undoc-members:

.. autoclass:: LintIssue
   :members:
   :undoc-members:

Scorecard
---------

.. autoclass:: MCPScorecard
   :members:
   :undoc-members:

.. autofunction:: grade_meets

.. autofunction:: print_scorecard

.. autofunction:: scorecard_to_json

.. autofunction:: scorecard_to_markdown
