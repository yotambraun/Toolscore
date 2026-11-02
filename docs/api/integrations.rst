Sessions, Config Lint, Recorders and Inspect AI
===============================================

Coding-agent sessions
---------------------

See :doc:`../coding_sessions`.

.. automodule:: toolscore.sessions
   :members:

.. autofunction:: toolscore.core.read_trace_data

Agent-config lint
-----------------

See :doc:`../config_lint`.

.. automodule:: toolscore.config_lint
   :members: lint_config, discover_files, ConfigIssue, ConfigLintReport, CONFIG_RULES, INVENTORY_RULES

Live recorders
--------------

See :doc:`../frameworks`.

.. automodule:: toolscore.recorders
   :members: ClaudeAgentSDKRecorder, OpenAIAgentsRecorder
   :inherited-members:

Inspect AI scorer
-----------------

.. automodule:: toolscore.inspect_scorer
   :members: toolscore_scorer, score_state, from_inspect_messages, final_answer_from_state

Framework helpers
-----------------

.. autofunction:: toolscore.integrations.claude_agent_sdk_messages

.. autofunction:: toolscore.integrations.pydantic_ai_final_answer
