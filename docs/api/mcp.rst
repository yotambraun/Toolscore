MCP Module
==========

.. currentmodule:: toolscore.mcp

Clients for Model Context Protocol (MCP) servers over stdio (standard library
only) and Streamable HTTP (``httpx``, the ``[http]`` extra), speaking MCP
2026-07-28 with a fallback to the ``initialize`` handshake, plus the scorecard
harness (scenario generation, execution, linting, output-schema checks, A--F
scoring and badges). See :doc:`../mcp_testing` for the CLI guide and
:download:`the demo script <../../examples/mcp_scorecard_demo.py>` for
programmatic usage.

Clients
-------

.. autoclass:: MCPClient
   :members: start, close, list_tools, call_tool

.. autoclass:: MCPStdioClient

.. autoclass:: MCPHttpClient

.. autodata:: MODERN_PROTOCOL_VERSION

.. autodata:: LEGACY_PROTOCOL_VERSION

.. autoclass:: MCPToolDef
   :members:
   :undoc-members:

.. autoclass:: MCPToolResult
   :members:
   :undoc-members:

.. autoexception:: MCPError

.. autoexception:: MCPTimeoutError

.. autoexception:: MCPHTTPStatusError

.. autofunction:: content_to_text

Recording sessions and injecting faults
---------------------------------------

See :doc:`../fault_injection`.

.. autoclass:: MCPRecorder
   :members:
   :undoc-members:

.. autoclass:: FaultSpec
   :members:

.. autoclass:: FaultRule
   :members:

.. autoclass:: FaultInjector
   :members:

.. autoclass:: toolscore.mcp.faults.Injection
   :members:

.. autodata:: toolscore.mcp.faults.FAULT_KINDS

.. autofunction:: load_fault_spec

Server configuration
--------------------

.. autoclass:: MCPServerSpec
   :members:
   :undoc-members:

.. autofunction:: load_mcp_config

.. autofunction:: open_client

Scorecard harness
-----------------

.. autofunction:: generate_scenarios

.. autofunction:: run_scenarios

.. autofunction:: lint_tools

.. autofunction:: toolscore.mcp.lint_rules.dangling_reference_issues

.. autofunction:: toolscore.mcp.lint_rules.poisoning_issues

.. autofunction:: toolscore.mcp.lint_rules.annotation_issues

.. autofunction:: toolscore.mcp.harness.output_schema_issues

.. autofunction:: toolscore.mcp.output_schema.validate_instance

.. autoclass:: Scenario
   :members:
   :undoc-members:

.. autoclass:: ScenarioResult
   :members:
   :undoc-members:

.. autoclass:: LintIssue
   :members:
   :undoc-members:

Argument values
---------------

.. autoclass:: ArgumentFixtures
   :members:

.. autofunction:: load_fixtures

.. autofunction:: toolscore.mcp.fixtures.parse_arg

Effect probes
-------------

See :doc:`../effect_probes`.

.. autofunction:: run_probes

.. autoclass:: ProbeResult
   :members:

.. autoclass:: ProbeConfig
   :members:

.. autoclass:: RoundTripPair
   :members:

.. autoclass:: BoundRelation
   :members:

.. autoclass:: Agreement
   :members:

.. autoclass:: CallSpec
   :members:

.. autofunction:: load_probe_config

.. autofunction:: toolscore.mcp.probes.builtin_relations

.. autofunction:: toolscore.mcp.probes.is_read_tool

.. autofunction:: toolscore.mcp.probes.write_basis

.. autodata:: toolscore.mcp.probes.PROBE_RULES
   :no-value:

Scorecard
---------

.. autoclass:: MCPScorecard
   :members:
   :undoc-members:

.. autofunction:: toolscore.mcp.scorecard.score_server

.. autofunction:: grade_meets

.. autofunction:: print_scorecard

.. autofunction:: scorecard_to_json

.. autofunction:: scorecard_to_markdown

Badges
------

.. autofunction:: toolscore.mcp.badge.badge_svg

.. autofunction:: toolscore.mcp.badge.badge_endpoint
