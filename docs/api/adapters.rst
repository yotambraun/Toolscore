Adapters Module
===============

.. currentmodule:: toolscore.adapters

Adapters convert various LLM trace formats into a normalized format for evaluation.

Base Classes
------------

.. autoclass:: ToolCall
   :members:
   :undoc-members:

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

Custom Adapter
^^^^^^^^^^^^^^

.. autoclass:: CustomAdapter
   :members:
   :undoc-members:
   :show-inheritance:
