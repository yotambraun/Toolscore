Core Module
===========

.. currentmodule:: toolscore.core

The core module provides the main evaluation functions and result container.

Main Functions
--------------

.. autofunction:: evaluate

.. autofunction:: assert_tools

.. autofunction:: test_agent

.. autofunction:: test_agent_async

.. autofunction:: evaluate_trace

.. autofunction:: load_gold_standard

.. autofunction:: load_trace

.. autofunction:: adapter_for

.. currentmodule:: toolscore.transcript

.. autoclass:: Transcript
   :members:

.. autofunction:: load_transcript

.. autofunction:: transcript_from_data

.. autofunction:: final_answer_of

.. autofunction:: normalize_tool_name

.. currentmodule:: toolscore.core

.. currentmodule:: toolscore.integrations

.. autofunction:: auto_extract

.. autofunction:: from_otel

.. autofunction:: from_openai_responses

.. currentmodule:: toolscore.core

Result Container
----------------

.. autoclass:: EvaluationResult
   :members:
   :undoc-members:
