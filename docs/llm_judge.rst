LLM-as-a-Judge
==============

Toolscore's core metrics are deterministic and syntactic — they compare tool
names and arguments exactly. Sometimes that is too strict: ``search`` vs
``web_search``, ``query`` vs ``q``, or two phrasings of the same value should
count as equivalent. The optional **LLM judge** uses a language model to score
*semantic* equivalence, multiplexed across providers.

.. note::
   The LLM judge is opt-in and non-deterministic by nature. Toolscore's default
   gate is the deterministic metric suite; reach for the judge as an *additional*
   signal, not a replacement. See :doc:`comparison` for where this fits.

.. contents::
   :local:
   :depth: 2


``JudgeConfig``
---------------

A single dataclass configures every provider:

.. code-block:: python

   from toolscore.metrics.llm_judge import JudgeConfig

   JudgeConfig(
       model="gpt-6-luna",    # model name; drives provider inference
       provider=None,         # None = infer from model / base_url
       api_key=None,          # None = read the per-provider env var
       base_url=None,         # set → OpenAI-compatible endpoint (Ollama/vLLM/...)
       temperature=None,      # None = send no temperature (see below)
       max_retries=2,         # passed to the underlying SDK
   )

.. note::
   ``temperature`` defaults to ``None``, and then no temperature is sent.
   Current Claude models (Opus 4.7 and later, Sonnet 5 and later, Haiku 5.5)
   and OpenAI's GPT-6 models at their default reasoning effort reject a
   non-default temperature with a 400 error. Set ``temperature=0.0`` only for
   models that accept it, such as most local OpenAI-compatible servers.

Current model IDs, verified against the providers' documentation on
2026-11-01, are in :mod:`toolscore.models`: ``gpt-6-luna`` (the default),
``claude-haiku-5-5`` and ``claude-sonnet-5-5`` (a stronger judge), and
``gemini-3.5-flash-lite``.

Anywhere a judge is accepted you can also pass a **bare model-name string**
(shorthand for ``JudgeConfig(model=...)``) or ``None`` (the default config).


Provider inference
------------------

When ``provider`` is ``None`` it is resolved from the model name (or
``base_url``):

.. list-table::
   :header-rows: 1
   :widths: 40 30 30

   * - Condition
     - Provider
     - Example model
   * - ``base_url`` is set
     - ``openai_compatible``
     - ``llama3.1``
   * - model starts with ``claude``
     - ``anthropic``
     - ``claude-haiku-5-5``
   * - model starts with ``gemini``
     - ``gemini``
     - ``gemini-3.5-flash-lite``
   * - anything else
     - ``openai``
     - ``gpt-6-luna``

You can always set ``provider`` explicitly. Two combinations are rejected:
``provider="openai_compatible"`` **requires** a ``base_url``, and any other
explicit provider **must not** be combined with a ``base_url`` (a base URL
implies an OpenAI-compatible endpoint, so the pairing is ambiguous).


Environment-variable keys
-------------------------

When ``api_key`` is omitted, the key is read from a per-provider environment
variable:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Provider
     - Environment variable
   * - ``openai``
     - ``OPENAI_API_KEY``
   * - ``anthropic``
     - ``ANTHROPIC_API_KEY``
   * - ``gemini``
     - ``GOOGLE_API_KEY`` (falls back to ``GEMINI_API_KEY``)
   * - ``openai_compatible``
     - ``OPENAI_API_KEY`` (often not needed — a placeholder is used)

For Gemini, ``GOOGLE_API_KEY`` is checked first and ``GEMINI_API_KEY`` second,
matching the newer ``google-genai`` SDK which accepts either.


Local / OpenAI-compatible endpoints (Ollama, vLLM, Groq)
--------------------------------------------------------

Any server that speaks the OpenAI chat-completions API works through the
``openai_compatible`` provider. Just set ``base_url``:

.. code-block:: python

   from toolscore.metrics.llm_judge import JudgeConfig, calculate_semantic_correctness

   # Ollama running locally — no real API key needed.
   judge = JudgeConfig(model="llama3.1", base_url="http://localhost:11434/v1")

   result = calculate_semantic_correctness(gold_calls, trace_calls, judge=judge)
   print(result["semantic_score"])

OpenAI-compatible endpoints often need no real key; the SDK still requires a
non-empty value, so Toolscore supplies a ``"not-needed"`` placeholder when no key
is found and a ``base_url`` is set. This also means the judge does not raise a
"missing API key" error for ``openai_compatible`` — it lets the local server
decide.


Batching behavior
-----------------

By default the judge issues a **single batched request** containing every
gold/trace pair and asks for a JSON array of per-pair scores. This keeps cost and
latency low.

* Only the first ``min(len(gold), len(trace))`` pairs are judged. A length
  mismatch additionally applies a proportional length penalty to the overall
  ``semantic_score``.
* If the batched response cannot be *parsed* into the expected number of
  pairs, the judge transparently falls back to **one request per pair**.
* Transport, authentication, and other SDK errors are **not** retried per-pair —
  they propagate so a bad key or network failure surfaces clearly instead of
  fanning out into N doomed requests.

The return value is a dict with ``semantic_score``, ``per_call_scores``,
``explanations``, ``model_used``, ``gold_count``, and ``trace_count``.


Extras install matrix
---------------------

Each provider's SDK is an optional extra, imported lazily so the module loads
even with no SDK installed:

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Provider
     - Install
     - SDK
   * - OpenAI / OpenAI-compatible
     - ``pip install tool-scorer[llm]``
     - ``openai``
   * - Anthropic
     - ``pip install tool-scorer[anthropic]``
     - ``anthropic``
   * - Gemini
     - ``pip install tool-scorer[gemini]``
     - ``google-genai``
   * - Everything
     - ``pip install tool-scorer[all]``
     - all of the above

If you call the judge without the required SDK, you get an ``ImportError`` whose
message includes the exact install command.


Using the judge from ``evaluate_trace``
----------------------------------------

The file-based :func:`toolscore.evaluate_trace` accepts a ``judge=`` argument
that folds semantic correctness into the result:

.. code-block:: python

   from toolscore import evaluate_trace
   from toolscore.metrics.llm_judge import JudgeConfig

   # judge=True  → default JudgeConfig() (gpt-6-luna, OpenAI)
   result = evaluate_trace("gold.json", "trace.json", judge=True)

   # judge="claude-haiku-5-5"  → string shorthand, inferred as Anthropic
   result = evaluate_trace("gold.json", "trace.json", judge="claude-haiku-5-5")

   # judge=JudgeConfig(...)  → full control
   result = evaluate_trace(
       "gold.json", "trace.json",
       judge=JudgeConfig(model="gemini-3.5-flash-lite"),
   )

``judge=False`` (the default) skips the judge entirely. The in-memory
:func:`toolscore.evaluate` does **not** run the judge — call
:func:`~toolscore.metrics.llm_judge.calculate_semantic_correctness` directly when
working in memory.

.. note::
   Earlier versions exposed ``use_llm_judge=...`` keyword arguments. Those are
   gone — the single ``judge=`` argument (bool, string, or ``JudgeConfig``) is
   the supported surface.


CLI flags
---------

The ``toolscore eval`` command exposes the judge:

.. code-block:: bash

   # OpenAI (default model gpt-6-luna, reads OPENAI_API_KEY):
   toolscore eval gold.json trace.json --llm-judge

   # Pick a model; the provider is inferred from the name:
   toolscore eval gold.json trace.json --llm-judge --llm-model claude-haiku-5-5
   toolscore eval gold.json trace.json --llm-judge --llm-model gemini-3.5-flash-lite

   # Force a provider:
   toolscore eval gold.json trace.json --llm-judge --llm-provider anthropic --llm-model ...

   # Local OpenAI-compatible server (Ollama):
   toolscore eval gold.json trace.json --llm-judge \
       --llm-model llama3.1 --llm-base-url http://localhost:11434/v1

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Flag
     - Meaning
   * - ``--llm-judge``
     - Enable the semantic judge (off by default).
   * - ``--llm-model NAME``
     - Judge model (default ``gpt-6-luna``). Drives provider inference.
   * - ``--llm-provider P``
     - Force ``openai`` / ``anthropic`` / ``gemini`` / ``openai_compatible``.
   * - ``--llm-base-url URL``
     - Custom OpenAI-compatible endpoint; forces ``openai_compatible``.


API reference
-------------

The ``calculate_semantic_correctness`` and ``calculate_batch_semantic_correctness``
functions are autodocumented under :doc:`api/metrics`.

.. autoclass:: toolscore.metrics.llm_judge.JudgeConfig
   :members:

.. autofunction:: toolscore.metrics.llm_judge.infer_provider
