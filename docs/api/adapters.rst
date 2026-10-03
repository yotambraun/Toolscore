Adapters Module
===============

.. currentmodule:: toolscore.adapters

Adapters convert various LLM trace formats into a normalized format for evaluation.

Base Classes
------------

.. autoclass:: ToolCall

.. autoclass:: BaseAdapter
   :members:
   :undoc-members:

Adapter Implementations
-----------------------

OpenAI Adapter
^^^^^^^^^^^^^^

.. autoclass:: OpenAIAdapter
   :members:
   :undoc-members:
   :show-inheritance:

Anthropic Adapter
^^^^^^^^^^^^^^^^^

.. autoclass:: AnthropicAdapter
   :members:
   :undoc-members:
   :show-inheritance:

LangChain Adapter
^^^^^^^^^^^^^^^^^

.. autoclass:: LangChainAdapter
   :members:
   :undoc-members:
   :show-inheritance:

Supports both legacy (AgentAction) and modern (ToolCall) LangChain formats.

Gemini Adapter
^^^^^^^^^^^^^^

.. autoclass:: GeminiAdapter
   :members:
   :undoc-members:
   :show-inheritance:

MCP Adapter
^^^^^^^^^^^

.. autoclass:: MCPAdapter
   :members:
   :undoc-members:
   :show-inheritance:

Reads JSON-RPC 2.0 message lists and sessions written by ``toolscore mcp record``.
Each ``tools/call`` response is paired with its request by id, so the call keeps
its result, error and duration.

OpenTelemetry Adapter
^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: OTelAdapter
   :members:
   :undoc-members:
   :show-inheritance:

.. autofunction:: toolscore.adapters.otel.tool_calls_from_otel

Custom Adapter
^^^^^^^^^^^^^^

.. autoclass:: CustomAdapter
   :members:
   :undoc-members:
   :show-inheritance:
