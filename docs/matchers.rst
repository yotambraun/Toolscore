Argument Matchers
=================

Matchers let you assert on the *shape* of an argument instead of its exact
value — "any string", "matches this regex", "approximately 9.99", "one of these
values". You drop a matcher in as the **value** inside an expected ``args`` dict
and it composes transparently with the normal argument comparison.

.. code-block:: python

   from toolscore import evaluate, ANY, Regex

   result = evaluate(
       expected=[{"tool": "get_weather", "args": {"city": Regex(r"NYC|JFK")}}],
       actual=[{"tool": "get_weather", "args": {"city": "NYC"}}],
   )
   assert result.argument_f1 == 1.0

Matchers work via operator overloading: a matcher's ``__eq__`` runs the match,
so ``Regex("NYC|JFK") == "NYC"`` is ``True``. That means they slot into dict
equality and the fluent :doc:`expect() API <fluent_api>` without any special
handling.

All matchers are importable from the top-level package
(``from toolscore import ANY, Regex, Approx, Contains, OneOf, IsType``) and from
:mod:`toolscore.matchers`.

.. contents::
   :local:
   :depth: 1


The matchers
------------

``ANY`` — match any value
^^^^^^^^^^^^^^^^^^^^^^^^^^

A singleton that matches anything. Use it when an argument must be *present* but
its value is irrelevant.

.. code-block:: python

   from toolscore import evaluate, ANY

   result = evaluate(
       expected=[{"tool": "search_flights", "args": {"origin": ANY, "destination": "NYC"}}],
       actual=[{"tool": "search_flights", "args": {"origin": "SFO", "destination": "NYC"}}],
   )
   assert result.argument_f1 == 1.0

.. note::
   ``ANY`` checks *presence* — the key must exist. If you do not care whether
   the key is there at all, omit it from the gold ``args`` entirely (see
   `The omitted-args vs {} contract`_).

``Regex`` — full-match a string
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Full-matches a string against a regular expression (``re.fullmatch`` semantics —
the *whole* value must match). Non-string values never match.

.. code-block:: python

   from toolscore import evaluate, Regex

   result = evaluate(
       expected=[{"tool": "book_flight", "args": {"flight_id": Regex(r"FL-\d+")}}],
       actual=[{"tool": "book_flight", "args": {"flight_id": "FL-42"}}],
   )
   assert result.argument_f1 == 1.0

Pass ``re`` flags as the second argument, e.g. ``Regex("nyc", re.IGNORECASE)``.

``Approx`` — numeric closeness
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Matches numbers within a tolerance, like ``pytest.approx``. The match passes
when ``|actual - expected| <= max(rel * |expected|, abs)``.

.. code-block:: python

   from toolscore import evaluate, Approx

   result = evaluate(
       expected=[{"tool": "charge", "args": {"amount": Approx(9.99, abs=0.01)}}],
       actual=[{"tool": "charge", "args": {"amount": 10.0}}],
   )
   assert result.argument_f1 == 1.0

* ``rel`` defaults to ``1e-6``; ``abs`` defaults to ``0.0``. With the default
  ``abs=0.0`` the match is purely relative, so comparing against an expected
  value of ``0`` requires exact equality — set ``abs`` when you need a tolerance
  around zero.
* ``bool`` is explicitly rejected even though it subclasses ``int``.

``Contains`` — membership
^^^^^^^^^^^^^^^^^^^^^^^^^^

Checks ``item in value``. Works for ``str``, ``list``, ``tuple``, ``set``,
``frozenset``, and ``dict`` (key membership). Non-containers never match.

.. code-block:: python

   from toolscore import evaluate, Contains

   result = evaluate(
       expected=[{"tool": "send_email", "args": {"tags": Contains("urgent")}}],
       actual=[{"tool": "send_email", "args": {"tags": ["urgent", "billing"]}}],
   )
   assert result.argument_f1 == 1.0

``OneOf`` — value is one of
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Passes if the value equals any of the candidates. Candidates may themselves be
matchers (their ``__eq__`` is invoked), so you can nest.

.. code-block:: python

   from toolscore import evaluate, OneOf, Regex

   result = evaluate(
       expected=[{"tool": "set_unit", "args": {"unit": OneOf("C", "F", Regex(r"kelvin"))}}],
       actual=[{"tool": "set_unit", "args": {"unit": "F"}}],
   )
   assert result.argument_f1 == 1.0

``IsType`` — type check
^^^^^^^^^^^^^^^^^^^^^^^^

Passes ``isinstance(value, types)`` for one or more types.

.. code-block:: python

   from toolscore import evaluate, IsType

   result = evaluate(
       expected=[{"tool": "paginate", "args": {"page": IsType(int)}}],
       actual=[{"tool": "paginate", "args": {"page": 3}}],
   )
   assert result.argument_f1 == 1.0

.. note::
   ``IsType(int)`` does **not** match ``True``/``False`` even though ``bool``
   subclasses ``int``. Use ``IsType(bool)`` explicitly to match booleans. This
   avoids a common footgun where an accidental boolean slips past an int check.


The omitted-args vs ``{}`` contract
------------------------------------

This is the single most important rule for writing gold expectations, and it is
independent of matchers — but matchers interact with it, so it lives here.

* **Omitting** ``args`` (or setting it to ``null``/``None``) means **"do not
  check arguments."** The tool must be called, but whatever arguments the agent
  passed are accepted.
* An explicit ``"args": {}`` means **"expect the tool to be called with exactly
  zero arguments."** If the agent passes any argument, that is a mismatch.

.. code-block:: python

   from toolscore import evaluate

   # Omitted args — tool-name-only expectation. Any args are fine.
   omitted = evaluate(
       expected=[{"tool": "search"}],
       actual=[{"tool": "search", "args": {"q": "python"}}],
   )
   assert omitted.argument_f1 == 1.0   # arguments not checked
   assert omitted.score == 1.0

   # Explicit empty dict — "expect no arguments". The agent passed one, so it fails.
   strict_empty = evaluate(
       expected=[{"tool": "search", "args": {}}],
       actual=[{"tool": "search", "args": {"q": "python"}}],
   )
   assert strict_empty.argument_f1 == 0.0
   assert strict_empty.score < 1.0     # ~0.7 — the surplus argument is penalized

This contract flows through every argument-sensitive metric (``argument_f1``,
tool correctness, trajectory), the composite ``score``, gold-file loading, and
the fluent ``expect().calls("tool")`` API. The fluent ``.calls("tool")`` with no
keyword arguments omits argument checking; pass kwargs —
``.calls("search", q="python")`` — to assert on specific arguments.

When you *do* specify ``args``, you check only the keys you list — a matcher (or
literal) is required for each key you care about, and extra keys the agent passed
that you did not list count against precision.


Strict mode interplay
----------------------

``evaluate(..., strict=True)`` (and ``assert_tools(..., strict=True)``,
``toolscore_snapshot(..., strict=True)``) makes *literal* argument comparison use
pure equality: no int/float coercion (``1`` vs ``1.0``) and no string stripping
(``"NYC"`` vs ``" NYC "``).

Matchers run their own ``matches()`` logic and are **not** affected by
``strict``. ``Approx`` already controls its own tolerance; ``Regex`` already
controls its own pattern. So a robust pattern is: use lenient defaults for plain
values, and reach for ``strict=True`` only when you want byte-exact literal
matching — while still using matchers for the fields where you want fuzzy intent.

.. code-block:: python

   from toolscore import evaluate, Approx

   # strict only tightens the *literal* "currency" field;
   # Approx still governs "amount" on its own terms.
   result = evaluate(
       expected=[{"tool": "charge", "args": {"amount": Approx(9.99, abs=0.01), "currency": "USD"}}],
       actual=[{"tool": "charge", "args": {"amount": 10.0, "currency": "USD"}}],
       strict=True,
   )
   assert result.argument_f1 == 1.0


API reference
-------------

See :doc:`api/matchers` for the full autodoc of every matcher class.
