Snapshot Testing
================

Jest-style snapshots for agent tool calls. Record what your agent *does* once,
review and approve it, then replay the approved baseline as a deterministic
regression test that fails the moment the agent drifts.

.. contents::
   :local:
   :depth: 2


The record → approve → replay story
-----------------------------------

A snapshot is a single JSON file that captures the list of tool calls an agent
made for one test. The workflow has three states:

1. **Record.** The first run captures the agent's calls into an *unapproved*
   snapshot, warns you, and does **not** assert anything yet. There is nothing
   to compare against.
2. **Approve.** You review the recorded calls and mark the snapshot approved
   (``toolscore approve``). This is the human-in-the-loop step that promotes a
   recording into a baseline.
3. **Replay.** Every subsequent run evaluates the agent's calls against the
   approved baseline with :func:`toolscore.evaluate` and fails the test when
   they drift.

The key design principle: **snapshots are created and reviewed locally, never
minted in CI.** In CI a missing or still-pending snapshot is a hard failure
(see `CI behavior`_) — otherwise an unreviewed recording could silently become
a "passing" baseline.


The ``toolscore_snapshot`` fixture
----------------------------------

The pytest fixture is the everyday entry point. It returns a callable that you
hand a raw agent response (or a list of ``{"tool", "args"}`` dicts). Snapshot
names default to the pytest node id, so you usually do not name them at all.

.. code-block:: python

    def test_books_a_flight(toolscore_snapshot):
        result = toolscore_snapshot(my_agent("book a flight to NYC"))
        # First run:  records a *pending* snapshot and warns.
        # After `toolscore approve`: replays and fails on drift.

The ``actual`` argument is run through
:func:`~toolscore.integrations.auto_extract`, so you can pass raw OpenAI,
Anthropic, Gemini, LangGraph, Pydantic AI, OpenAI Agents SDK, or Claude Agent
SDK responses directly — no manual extraction required.

Call signature
^^^^^^^^^^^^^^

.. code-block:: python

    toolscore_snapshot(
        actual,
        *,
        min_score=1.0,          # required composite score when replaying
        weights=None,           # optional custom metric weights
        strict=False,           # pure-equality argument comparison
        name=None,              # defaults to the pytest node id
    )

* ``min_score`` defaults to ``1.0`` — an *exact* replay. (A tiny epsilon is
  subtracted internally so floating-point noise in the weighted composite never
  spuriously fails a genuine match.) Lower it if you want to tolerate minor
  argument drift.
* ``weights`` and ``strict`` are forwarded to :func:`toolscore.evaluate`.
* ``name`` overrides the auto-generated name. A second *unnamed* call in the
  same test automatically gets a ``-2``, ``-3`` … suffix, so multiple snapshots
  per test never collide:

  .. code-block:: python

      def test_two_flows(toolscore_snapshot):
          toolscore_snapshot(agent("book a flight"))      # ...::test_two_flows
          toolscore_snapshot(agent("cancel a flight"))    # ...::test_two_flows-2

The fixture returns the :class:`~toolscore.core.EvaluationResult` when an
approved baseline was replayed, and ``None`` in every non-evaluating state
(recording, pending, or update).

Pytest options
^^^^^^^^^^^^^^

These options come from the bundled pytest plugin (auto-loaded on install):

.. list-table::
   :header-rows: 1
   :widths: 32 68

   * - Option
     - Effect
   * - ``--toolscore-snapshot-dir PATH``
     - Root directory for snapshot files, relative to the pytest rootdir.
       Default ``.toolscore/snapshots``.
   * - ``--toolscore-update``
     - Re-record every snapshot the fixture touches (overwrite **and**
       re-approve). Use after an intentional behavior change.
   * - ``--toolscore-allow-pending``
     - Treat missing/pending snapshots as non-fatal **even in CI** (warn
       instead of failing). Useful for staged rollouts of new snapshot tests.

Environment variables
^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Effect
   * - ``TOOLSCORE_RECORD_UPDATE=1``
     - Same as ``--toolscore-update``. This is how ``toolscore record --update``
       signals the subprocess. Any non-empty value other than ``0``/``false``/
       ``no`` is truthy.
   * - ``CI`` (set, non-empty)
     - Switches the snapshot state machine into CI mode: missing/pending
       snapshots **fail** instead of warning, and snapshots are never created.
       Most CI providers set this for you.


CLI commands
------------

``toolscore record`` — capture snapshots
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Two modes.

**Subprocess mode** runs pytest (or any command) with snapshot recording
enabled, so unnamed ``toolscore_snapshot`` calls record fresh baselines:

.. code-block:: bash

   # Record snapshots for a subset of tests:
   toolscore record -- pytest tests/ -k books_a_flight

   # Re-record (overwrite + re-approve) after an intentional change:
   toolscore record --update -- pytest tests/

Everything after ``--`` is the command to run. In subprocess mode ``record``
sets ``TOOLSCORE_RECORD=1`` (and ``TOOLSCORE_RECORD_UPDATE=1`` with
``--update``) in the child's environment, then exits with the command's exit
code.

**Trace mode** seeds a snapshot straight from an existing trace file — no
subprocess, useful for importing a known-good run:

.. code-block:: bash

   toolscore record --from-trace trace.json --name books_a_flight
   toolscore record --from-trace trace.json --name books_a_flight --format openai

``--name`` is required in trace mode. ``--format`` (default ``auto``) selects
the trace adapter. Without ``--update`` the command refuses to overwrite an
existing snapshot. Trace-mode recordings start **pending** (approve them
afterwards); ``--update`` overwrites *and* approves in one step.

Both modes accept ``--dir`` to point at a non-default snapshot directory.

``toolscore approve`` — promote a recording to a baseline
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   toolscore approve books_a_flight        # approve one snapshot by name
   toolscore approve a b c                  # approve several by name
   toolscore approve --all                  # approve every pending snapshot

Approval prints a table of what was approved (name, call count, age). This is
the one place a human says "yes, this is the behavior I want to lock in."

``toolscore snapshots`` — list / show / rm
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   toolscore snapshots list             # all snapshots (status, calls, source)
   toolscore snapshots list --pending   # only unapproved ones
   toolscore snapshots show books_a_flight   # full tool calls + metadata
   toolscore snapshots rm books_a_flight     # delete (prompts unless --yes)

All snapshot commands accept ``--dir`` (default ``.toolscore/snapshots``).


Snapshot file format
--------------------

Each snapshot is one human-readable JSON file under the snapshot root. The file
name is ``<sanitized-name>-<sha1(name)[:8]>.json`` — the hash suffix guarantees
uniqueness and keeps every file inside the root even if the name contains path
separators.

.. code-block:: json

   {
     "schema_version": 1,
     "name": "tests/test_flights.py::test_books_a_flight",
     "created_at": "2025-06-01T12:00:00+00:00",
     "updated_at": "2025-06-01T12:05:00+00:00",
     "toolscore_version": "1.7.0",
     "approved": true,
     "source": "pytest",
     "calls": [
       {"tool": "search_flights", "args": {"destination": "NYC"}},
       {"tool": "book_flight", "args": {"flight_id": "FL-42"}}
     ]
   }

``approved`` is the state flag flipped by ``toolscore approve``. ``source`` is
``"pytest"``, ``"record"``, or ``"trace"`` depending on how it was produced.
**Commit these files to version control** — they are your reviewed baselines,
and a diff on a snapshot file is a diff on your agent's behavior.


CI behavior
-----------

The snapshot state machine reads the ``CI`` environment variable at call time
and behaves differently:

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - State
     - Locally (``CI`` unset)
     - In CI (``CI`` set)
   * - Snapshot missing
     - Write a pending snapshot, warn, return ``None``.
     - **Fail** — and do not write the file. Record it locally first.
   * - Exists but **pending**
     - Warn, return ``None`` (never evaluated against).
     - **Fail** — approve it locally first.
   * - ``--toolscore-update``
     - Overwrite + approve, warn, return ``None``.
     - Same.
   * - Exists and **approved**
     - Evaluate against the baseline; fail below ``min_score``.
     - Same.

This is why a fresh snapshot can never sneak through CI as "passing": only an
**approved** baseline is ever evaluated, and CI refuses to create or rubber-stamp
new ones.

``--toolscore-allow-pending`` relaxes the first two rows in CI — missing and
pending snapshots warn instead of failing — which lets you land a new snapshot
test before its baseline is approved (a staged rollout). Approved replays are
unaffected and still fail on drift.

At the end of a run the plugin prints a one-line Jest-style summary, e.g.::

   toolscore: 2 snapshots created (pending approval), 1 updated, 5 passed


The update flow
---------------

When your agent's behavior changes *on purpose*, the baseline must change too:

1. Make the change and run the snapshot test. The approved baseline now drifts,
   so the test **fails** with a diff showing exactly what changed.
2. If the new behavior is correct, re-record it:

   .. code-block:: bash

      toolscore record --update -- pytest tests/ -k the_changed_test
      # or, directly:
      pytest tests/ -k the_changed_test --toolscore-update

3. Review the changed snapshot file in your diff and commit it.

``--update`` overwrites the calls **and** re-approves in one step, so there is
no separate ``approve`` needed after an update.


Programmatic API
----------------

The fixture and CLI are thin wrappers over
:func:`toolscore.snapshots.snapshot_check` and
:class:`~toolscore.snapshots.SnapshotStore`. You can drive the state machine
directly:

.. code-block:: python

   from toolscore.snapshots import snapshot_check, SnapshotStore

   store = SnapshotStore(".toolscore/snapshots")
   result = snapshot_check("my_flow", my_agent("book a flight"), store=store)
   # result is None until the snapshot is approved, then an EvaluationResult.

See the :doc:`api/snapshots` reference for the full ``Snapshot`` /
``SnapshotStore`` / ``snapshot_check`` API.
