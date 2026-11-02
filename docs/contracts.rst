Contracts v2
============

A gold file lists the calls an agent must make, so every other call is
"extra" and every other path is wrong. A **contract** says more: which calls
are required, which are allowed but not needed, which must never happen, and
where more than one path is fine. ``toolscore eval``, ``evaluate_trace()``,
``toolscore regrade`` and the agent harness take a contract wherever they take
a gold file; :func:`toolscore.evaluate_contract` evaluates one in memory.

.. code-block:: json

   {
     "contract_version": 2,
     "description": "Book a flight to Lisbon. Checking the weather is fine; cancelling is not.",
     "required": [
       {"tool": "search_flights", "args": {"destination": "LIS", "date": {"$regex": "^2026-12-"}}},
       {
         "id": "book",
         "alternatives": [
           [{"tool": "book_flight", "args": {"flight_id": {"$regex": "^FL-\\d+$"}}}],
           [{"tool": "reserve_seat", "args": {"flight_id": {"$regex": "^FL-\\d+$"}}}]
         ]
       }
     ],
     "optional": [{"tool": "get_weather"}],
     "forbidden": [{"tool": "cancel_booking", "reason": "never cancel an existing booking"}],
     "weights": {"required_call_recall": 0.3},
     "min_score": 0.9
   }

Semantics
---------

**required**
   Scored like gold calls, in order. An element ``{"alternatives": [[calls],
   [calls], ...], "id": ...}`` stands for any one of its options (an option is a
   list of calls, or one call). Every combination of options is scored and the
   **highest composite score wins; ties go to the option declared first**. A
   top-level ``alternatives`` list of groups is appended after ``required``. At
   most 256 combinations are scored.

**optional**
   Neither penalized when absent nor counted as extra when present: a call that
   matches an optional entry (tool and arguments) is left out of the score
   metrics, unless it is needed to fill a required call of the same tool (calls
   are taken in order). The honesty, credential, forbidden-call and evidence
   checks still see every call, and records keep it
   (``EvaluationResult.trace_calls``; ``scored_calls`` is what the score
   compared).

**forbidden**
   The forbidden-call policy (see :doc:`behavior_safety`): reported under
   *Behavior and safety* and as the ``forbidden-calls`` evidence check, not
   scored. ``toolscore eval --forbidden`` rules are added to the contract's.

**weights**, **min_score**
   Score weights as for :func:`toolscore.evaluate`, and the passing score
   (``contract_metrics.passed``; the agent harness uses it per task).

Argument matchers
-----------------

Values are compared as in gold files (numbers and whitespace leniently unless
``strict``). In JSON a value can also be a matcher:

=====================================  ===============================================
Matcher                                Matches
=====================================  ===============================================
``{"$regex": "^FL-"}``                 the pattern found anywhere in the value
``{"$contains": "x"}``                 a string or list that contains ``x``
``{"$one_of": ["a", "b"]}``            any of the values
``{"$any": true}``                     anything (the argument must be present)
``{"$type": "string"}``                a JSON type (or a list of them): ``string``,
                                       ``integer``, ``number``, ``boolean``, ``array``,
                                       ``object``, ``null``
``{"$approx": 3.0}``                   a number close to it; or ``{"$approx":
                                       {"value": 3.0, "rel": 0.01, "abs": 0.1}}``
=====================================  ===============================================

In Python, any :class:`~toolscore.matchers.Matcher` (``Regex``, ``ANY``,
``Approx``...) works too.

What it reports
---------------

``metrics["contract_metrics"]``: ``contract_version``, the counts of required,
optional and forbidden entries, ``alternatives.chosen`` (the option picked per
group and its calls) and ``alternatives.combinations`` (every combination's
score), ``optional_matched`` (the optional calls left out of the score, by
index) and ``min_score`` / ``passed``.

Example (``examples/contracts/``, real output): an agent searched flights,
checked the weather and reserved a seat instead of calling ``book_flight``.

.. code-block:: text

   $ toolscore eval gold.json trace.json        # search_flights, then book_flight
   │ Grade F   FAIL (38.3%) │

   $ toolscore eval contract.json trace.json
   │ Grade A   PASS (95.7%) │

   Top issues to fix
     1. reserve_seat  `reserve_seat` called with unexpected arguments (unexpected: seat)

   Evidence: 7 pass, 0 fail, 0 unknown

The contract picked the ``reserve_seat`` alternative (0.957 against 0.59 for
``book_flight``), left ``get_weather`` out of the score, and still reports the
extra ``seat`` argument.

Schema and Python
-----------------

The JSON Schema ships as ``toolscore/schemas/contract-v2.schema.json``
(``toolscore.contract.CONTRACT_SCHEMA_PATH``). ``toolscore doctor --contract
FILE`` validates a contract and counts its combinations.

.. code-block:: python

   from toolscore import evaluate_contract, load_contract

   result = evaluate_contract(load_contract("contract.json"), actual_calls,
                              final_answer="Booked FL-204.")
   result.metrics["contract_metrics"]["alternatives"]["chosen"]

A gold file is still accepted everywhere; a file is read as a contract when it
is a JSON object with ``contract_version``, ``required`` or ``optional``.
