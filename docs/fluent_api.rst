Fluent API — ``expect()``
==========================

The ``expect()`` function is the easiest way to assert on an agent's tool-calling
behavior.  It returns an :class:`~toolscore.expect.Expectation` builder that you
configure with a fluent chain of method calls, then execute with
:meth:`~toolscore.expect.Expectation.run` (or
:meth:`~toolscore.expect.Expectation.run_async` for async agents).

Hero Example
------------

.. code-block:: python

    from toolscore import expect, ANY, Regex

    expect(agent).on("book me a flight to NYC") \
        .calls("search_flights", origin=ANY, destination="NYC") \
        .then_calls("book_flight", flight_id=Regex(r"FL-\d+")) \
        .does_not_call("cancel_booking") \
        .with_score(0.9) \
        .run()

If the assertion fails you get a rich diff table printed inline — no manual
digging through raw response objects required.

Quick Start
-----------

**Assert on an already-produced result (list of call dicts)**

.. code-block:: python

    actual = [
        {"tool": "search_flights", "args": {"origin": "JFK", "destination": "NYC"}},
        {"tool": "book_flight",    "args": {"flight_id": "FL-456"}},
    ]

    expect(actual) \
        .calls("search_flights", origin="JFK", destination="NYC") \
        .then_calls("book_flight", flight_id=Regex(r"FL-\d+")) \
        .with_score(0.9) \
        .run()

**Assert on a sync agent callable**

.. code-block:: python

    def my_agent(prompt: str) -> list[dict]:
        ...  # calls your LLM, returns tool-call dicts

    expect(my_agent) \
        .on("find flights from JFK to LAX") \
        .calls("search_flights", origin="JFK", destination="LAX") \
        .run()

**Assert on a raw provider response (auto-extracted)**

``expect()`` automatically calls :func:`~toolscore.integrations.auto_extract` so
you can pass a raw OpenAI, Anthropic, or Gemini response dict directly:

.. code-block:: python

    raw_response = openai_client.chat.completions.create(...)  # returns dict-like
    expect(raw_response) \
        .calls("search_flights", origin=ANY, destination="NYC") \
        .run()

Chain-Method Reference
----------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Method
     - Description
   * - ``.on(prompt)``
     - Set the input prompt for a callable subject.  Required when the subject is
       an agent function; forbidden when the subject is a result/list.
   * - ``.calls(tool, **args)``
     - Append an expected tool call.  ``**args`` may contain
       :ref:`matcher objects <matchers>` such as :data:`~toolscore.ANY` or
       :class:`~toolscore.Regex`.  Calling with **no kwargs** means "match the tool
       name but do not check arguments".
   * - ``.then_calls(tool, **args)``
     - Alias for :meth:`calls` — reads more naturally when describing sequences.
   * - ``.does_not_call(tool)``
     - Assert that *tool* must **not** appear in the actual calls.  Can be combined
       with :meth:`calls` or used alone (forbidden-only contract).
   * - ``.with_score(min_score)``
     - Set the minimum composite score (default: **0.9**).  Raises
       :class:`~toolscore.ToolScoreAssertionError` with a diff table when not met.
   * - ``.with_weights(**weights)``
     - Override composite-score weights.  Valid keys: ``selection_accuracy``,
       ``argument_f1``, ``sequence_accuracy``, ``redundant_rate``.
   * - ``.with_strict_args()``
     - Enable strict argument comparison: no int/float coercion, no string strip.
   * - ``.run()``
     - Execute the assertion synchronously.  Returns
       :class:`~toolscore.core.EvaluationResult` on success.
   * - ``.run_async()``
     - Execute the assertion asynchronously.  Works for both sync and async agent
       callables.  Returns :class:`~toolscore.core.EvaluationResult` on success.

.. _matchers:

Using Matchers
--------------

Import matchers from ``toolscore``:

.. code-block:: python

    from toolscore import ANY, Approx, Contains, IsType, OneOf, Regex

Place them as argument *values* inside :meth:`~toolscore.expect.Expectation.calls`:

.. code-block:: python

    expect(actual) \
        .calls("book_flight",
               flight_id=Regex(r"FL-\d+"),  # regex match
               seats=Approx(2),             # numeric closeness
               origin=ANY,                  # matches anything
               cabin=OneOf("economy", "business")) \
        .run()

See :doc:`api/core` for the full matcher reference.

Async Agents
------------

Use :meth:`~toolscore.expect.Expectation.run_async` for async agents:

.. code-block:: python

    import asyncio
    from toolscore import expect, ANY

    async def async_agent(prompt: str) -> list[dict]:
        ...  # async LLM call

    async def test_booking():
        result = await expect(async_agent) \
            .on("book me a flight") \
            .calls("search_flights", destination=ANY) \
            .run_async()
        assert result.score >= 0.9

    # or with asyncio.run in a plain test:
    asyncio.run(test_booking())

Calling ``.run()`` on an async agent function raises :class:`TypeError` with a
message directing you to use ``run_async()`` instead.

Forbidden-Only Contract
-----------------------

You may use :meth:`~toolscore.expect.Expectation.does_not_call` *without* any
:meth:`~toolscore.expect.Expectation.calls` declarations.  In this mode the
evaluation runs but the minimum-score threshold is **not enforced** — only the
forbidden-call check is applied:

.. code-block:: python

    # Assert the agent never calls the dangerous tool, regardless of what else it does
    expect(actual).does_not_call("delete_all_files").run()

API Reference
-------------

.. autofunction:: toolscore.expect.expect

.. autoclass:: toolscore.expect.Expectation
   :members:
   :undoc-members:
