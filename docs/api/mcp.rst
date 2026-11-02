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

.. autodata:: toolscore.mcp.scorecard.PROBE_GRADE_CAP

Snapshots, pinning and diffs
----------------------------

See :doc:`../pinning_diff`.

.. autoclass:: ServerSnapshot
   :members:

.. autofunction:: load_snapshot

.. autofunction:: write_snapshot

.. autofunction:: toolscore.mcp.snapshot.snapshot_from_json

.. autofunction:: build_lock

.. autofunction:: verify_pin

.. autofunction:: load_lock

.. autofunction:: write_lock

.. autofunction:: infer_capabilities

.. autofunction:: toolscore.mcp.pin.load_capability_overrides

.. autoclass:: PinReport
   :members:

.. autoclass:: PinFinding
   :members:

.. autodata:: toolscore.mcp.pin.PIN_RULES
   :no-value:

.. autodata:: toolscore.mcp.pin.CAPABILITIES

.. autofunction:: diff_snapshots

.. autoclass:: ServerDiff
   :members:

.. autoclass:: ToolChange
   :members:

.. autofunction:: toolscore.mcp.server_diff.render_diff

Agent harness
-------------

See :doc:`../agent_harness`.

.. automodule:: toolscore.mcp.agent
   :no-index:

.. currentmodule:: toolscore.mcp.agent

.. autofunction:: run_agent

.. autofunction:: run_study

.. autofunction:: load_agent_spec

.. autofunction:: spec_from_mapping

.. autofunction:: regrade_rows

.. autofunction:: evaluate_run

.. autofunction:: estimate_study_cost

.. autofunction:: preflight_prices

.. autofunction:: check_build

.. autofunction:: map_tools

.. autofunction:: rules_guard

.. autofunction:: allow

.. autofunction:: deny

.. autoclass:: OpenAIResponsesProvider

.. autoclass:: AnthropicMessagesProvider

.. autoclass:: ScriptedProvider

.. autoclass:: ModelProvider
   :members:

.. autoclass:: AgentRun
   :members:

.. autoclass:: AgentSpec
   :members: cells

.. autoclass:: Budget
   :members:

.. autoclass:: Limits

.. autoclass:: Price

.. autoclass:: GuardCall

.. autoclass:: GuardDecision

.. autoexception:: UnknownPriceError

.. autoexception:: BuildMismatchError
