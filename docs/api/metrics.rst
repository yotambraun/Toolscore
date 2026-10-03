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

Required Calls
--------------

.. autofunction:: calculate_required_call_recall

Efficiency Metrics
------------------

.. autofunction:: calculate_redundant_call_rate

Reports ``error_count``, ``error_rate`` and ``retry_after_error_count`` alongside
the redundancy and loop (``identical_rate``) metrics.

Safety: Credentials and Forbidden Calls
---------------------------------------

See :doc:`../behavior_safety` for the guide, the credential formats and the JSON
rule operators.

.. autofunction:: find_secrets

.. autofunction:: check_forbidden_calls

.. autofunction:: rules_from_json

.. autofunction:: load_forbidden_rules

.. autofunction:: toolscore.metrics.policy.call_matches_rule

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
