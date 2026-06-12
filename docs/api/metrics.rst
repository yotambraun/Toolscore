Metrics Module
==============

.. currentmodule:: toolscore.metrics

The metrics module provides functions to calculate various evaluation metrics.

Accuracy Metrics
----------------

.. autofunction:: calculate_invocation_accuracy

.. autofunction:: calculate_selection_accuracy

Sequence Metrics
----------------

.. autofunction:: calculate_edit_distance

Argument Metrics
----------------

.. autofunction:: calculate_argument_f1

Efficiency Metrics
------------------

.. autofunction:: calculate_redundant_call_rate

Side-Effect Metrics
-------------------

.. autofunction:: calculate_side_effect_success_rate

Performance Metrics
-------------------

.. autofunction:: calculate_latency

.. autofunction:: calculate_cost_attribution

LLM-as-a-judge Metrics (Optional)
----------------------------------

These metrics use an optional LLM judge that supports OpenAI, Anthropic, Gemini,
and any OpenAI-compatible endpoint. Configure it with a
:class:`~toolscore.metrics.llm_judge.JudgeConfig` (or a model-name string). See
the :doc:`../llm_judge` guide for provider inference, env-var keys, and install
extras.

.. autofunction:: toolscore.metrics.llm_judge.calculate_semantic_correctness

.. autofunction:: toolscore.metrics.llm_judge.calculate_batch_semantic_correctness
