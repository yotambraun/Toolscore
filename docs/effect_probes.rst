Effect Probes
=============

Correct tool calls are not enough: a tool can answer "success" and do nothing.
The scorecard's scenarios check that every tool *answers*; effect probes check
that it *did what it reported*. They are deterministic invariant checks against
the live server, with no model and no API key.

Each probe generalizes a real bug that a pass rate could not see:

* the official MCP memory server's ``create_entities`` skipped entities whose
  name already existed and still answered with success
  (`modelcontextprotocol/servers#4887 <https://github.com/modelcontextprotocol/servers/issues/4887>`_);
* its graph file lost unreadable lines on the next write (#4885);
* the filesystem server's ``read_text_file`` returns the whole file for
  ``head: 0`` (#4178).

.. code-block:: bash

   toolscore mcp test "python my_server.py" --probes                  # read-only probes
   toolscore mcp test "python my_server.py" --probes --allow-writes   # plus write round trips
   toolscore mcp test "python my_server.py" --probe-config probes.yaml --allow-writes

Try it on the bundled sample server, started with a deliberate bug: creating a
note whose title exists reports success and changes nothing.

.. code-block:: text

   $ toolscore mcp test "python -m toolscore.mcp.sample_server --bug silent-skip" \
       --probes --allow-writes

   ╭────────────────────────────────────────────────────╮
   │ MCP Scorecard: notes-server 1.1.0                  │
   │ Grade C   Score 74%                                │
   │ happy 80%  |  edge 100%  |  lint 91%  |  effect 0% │
   │ MCP 2026-07-28 (stateless)                         │
   ╰────────────────────────────────────────────────────╯
   ...
                                         Effect probes
   ┏━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
   ┃ Probe      ┃ Tool        ┃ Result ┃ Confidence ┃ Detail                                ┃
   ┡━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
   │ bound      │ list_notes  │ pass   │ medium     │ limit bounded the result for [1, 2]   │
   │ round-trip │ create_note │ FAIL   │ high       │ a second write to key                 │
   │            │             │        │            │ 'tsp64c7f0-title' reported success;   │
   │            │             │        │            │ state unchanged (probe-silent-noop)   │
   └────────────┴─────────────┴────────┴────────────┴───────────────────────────────────────┘

   Top issues to fix
     1. create_note  a second write to key 'tsp64c7f0-title' reported success; state
   unchanged (probe-silent-noop)
        -> Make the tool report what it did: return an error, or say which items were
   skipped, instead of success when nothing was stored.

Without the bug (``python -m toolscore.mcp.sample_server``) the same command
grades B (86%) and the round trip passes. ``--bug lose-on-write`` (every new
note replaces the stored ones) gives ``probe-data-lost``, and
``--bug limit-ignored`` gives ``probe-bound-exceeded``.

On real servers, see `examples/mcp_memory_probes
<https://github.com/yotambraun/toolscore/tree/main/examples/mcp_memory_probes>`_:
``@modelcontextprotocol/server-memory@2026.8.31``, released before the #4887 fix,
gets ``probe-silent-noop`` on ``create_entities``; ``2.0.1`` passes, because it
answers "Skipped 1 entity that already exists". Both runs need no probe config.
`examples/mcp_filesystem_probes
<https://github.com/yotambraun/toolscore/tree/main/examples/mcp_filesystem_probes>`_
shows the built-in bounds flagging ``head: 0`` and ``tail: 0`` on
``@modelcontextprotocol/server-filesystem@2.1.0``.

Safety: read-only by default
----------------------------

``--probes`` alone calls only read-only tools (``readOnlyHint: true``, or a
name that starts with a read verb such as ``get``, ``list``, ``search``,
``read``). Probes that write run only with ``--allow-writes`` (or
``allow_writes=True``); without it they are listed as skipped:

.. code-block:: text

   1 probe(s) skipped because they write (create_note); add --allow-writes to run them
   against a disposable server.

Write probes leave records behind, named with a ``tsp<hex>-`` marker. Point
them at a disposable instance (a temporary data file, a test database, a
sandbox account), never at production data. A probe config cannot turn writes
on; only the command line or the Python argument can.

The scorecard's own scenarios already call every tool, write tools included,
with generated values, so the same advice applies to ``mcp test`` without
probes.

Round trips (writes)
--------------------

A tool is a *write tool* when its name contains a storing verb (``create``,
``add``, ``update``, ``write``, ``set``, ``save``, ``put``, ``insert``,
``upsert``, ``append``, ``edit``, ``modify``, ``store``, ``remember``,
``record``) and it is not annotated ``readOnlyHint: true`` or
``destructiveHint: true``, or when it declares ``readOnlyHint: false`` and
``destructiveHint: false``. Tools that send, publish, deploy or delete are not
probed unless you list them under ``writes`` in a probe config.

For each write tool:

1. **Write** values that carry a unique marker: every free-text field gets
   ``tsp<hex>-<field>``; arrays get one item; objects get their required and
   text fields. ``--arg`` values replace generated ones.
2. **Read back** through the server's read tools (at most six): tools sharing
   a noun with the write tool first (``create_note`` and ``search_notes``),
   then any other read tool. A reader's arguments are filled from the write: a
   parameter with the same name as a written field gets its value, a
   query-like parameter (``query``, ``q``, ``search``, ``filter``...) gets the
   record's key, a limit-like parameter gets 100. A reader that shows a marker
   is *confirmed*.
3. **Same key, new values.** If the write has a key field (last word ``name``,
   ``id``, ``key``, ``title``, ``path``, ``slug``, ``uri``, ``url``,
   ``filename``, ``email`` or ``username``), write again with the same key and
   new markers elsewhere. An error is fine (the tool refused). A result that
   says it skipped (``skipped``, ``already exists``, ``unchanged``,
   ``duplicate``...; a JSON ``"skipped": []`` does not count) is fine. A plain
   success with the old values still showing is ``probe-silent-noop``.
4. **Another record.** Write a record with a new key, then read the first one
   again. If it is gone: ``probe-data-lost``.

A write that fails with the generated values, or that no read tool answers
for, is ``inconclusive`` with the reason ("supply values with --arg").

Bounds (read-only)
------------------

Built-in relations, for read-only tools only:

========================================  ===============  ==================================================
Parameter (integer)                       Tried with       Must return
========================================  ===============  ==================================================
``head``                                  0, 1, 2          exactly the first ``min(N, all)`` lines
``tail``                                  0, 1, 2          exactly the last ``min(N, all)`` lines
``limit``, ``max_results``, ``top_k``,    1, 2             at most N items; exactly ``min(N, all)`` when the
``top_n``, ``max_items``, ``page_size``,                   parameter is optional (``all`` is the count
``per_page``, ``n_results``,                               without it)
``num_results``, ``first``, ``last``
========================================  ===============  ==================================================

Items are counted from ``structuredContent`` (a list, or an object with one
list field), then from a JSON result of the same shape, otherwise as text
lines. ``limit: 0`` is not tried, because some APIs read it as "no limit";
declare it if your tool means zero. Names such as ``max``, ``count`` or
``max_length`` (characters, in the fetch server) are not bounds.

Confidence and the grade
------------------------

Every probe result says how its read tool or relation was chosen (``basis``)
and how sure that is:

==========  ================================================================  ==================
Confidence  When                                                              A failure is
==========  ================================================================  ==================
high        declared in a probe config, or the read tool already showed       an error; lowers
            this record (steps 3 and 4 above)                                 the score, caps
                                                                              the grade at C
medium      inferred from names: a built-in bound, a read tool sharing a      a warning
            noun with the write tool
low         any other read tool; a built-in ``limit`` counted in text lines   a warning
==========  ================================================================  ==================

Heuristics never fail a grade on their own. A tool with a high-confidence
failure costs as much as a tool that fails all of its happy paths::

    score = max(0, score - 0.6 * tools_failing_probes / max(num_tools, 1))

so a run whose probes all pass scores exactly as without probes. The header
shows ``effect`` (the share of high-confidence checks that passed, ``n/a`` when
there were none), and ``--ci`` treats a high-confidence failure as blocking.

The grade cap
~~~~~~~~~~~~~

On a server with many tools that penalty is small: the official memory server
has 9 tools, so ``probe-silent-noop`` on ``create_entities`` costs ``0.6 / 9``
and ``server-memory@2026.8.31`` still scored 93%. A tool that reports success
and does nothing is a correctness bug, not a style issue, so any high-confidence
probe failure also **caps the letter grade at C**. The score is unchanged; the
grade, the badge (``C (capped) · Toolscore``, with the reason in its title) and
every report say why:

.. code-block:: text

   ╭────────────────────────────────────────────────────────────────────────╮
   │ MCP Scorecard: memory-server 0.6.3                                     │
   │ Grade C   Score 93%                                                    │
   │ Grade A by score, capped because: probe-silent-noop on create_entities │
   │ happy 100%  |  edge 100%  |  lint 100%  |  effect 50%                  │
   │ MCP 2025-11-25 (initialize handshake)                                  │
   ╰────────────────────────────────────────────────────────────────────────╯

The JSON report has ``grade_cap`` (``enabled``, ``capped``, ``cap``,
``uncapped_grade``, ``reasons``, ``note``). ``--fail-under`` and the Action's
``mcp-grade`` output use the capped grade. ``--no-probe-grade-cap``
(``score_server(..., probe_grade_cap=False)``, Action input
``mcp-probe-grade-cap: false``) restores the grade the score alone earns. A
grade that is already C or worse is not marked capped, and warnings
(medium/low confidence) never cap.

Probe rules
~~~~~~~~~~~

=================================  =========================================================
Rule                               Fires when
=================================  =========================================================
``probe-write-not-observable``     a write reported success but no read tool shows it
``probe-silent-noop``              a same-key write reported success and changed nothing
``probe-data-lost``                a record shown earlier is gone after a later write
``probe-bound-exceeded``           more lines or items than the bound parameter allows
``probe-bound-short``              fewer than ``min(N, all)`` lines or items
``probe-slice-mismatch``           ``head``/``tail`` content is not the start/end of the full content
``probe-paths-disagree``           two declared tools that should agree return different items
``probe-not-idempotent``           the same declared read returns different results
=================================  =========================================================

Probe configs: declare what you know
------------------------------------

A probe config (JSON, or YAML with ``pip install "tool-scorer[yaml]"``)
declares pairs, relations and agreements. Everything declared is high
confidence. This is ``examples/probes/notes-probes.yaml``:

.. code-block:: yaml

   # Round trip: create_note must be visible through search_notes, searched by its key.
   pairs:
     - write: create_note
       read: search_notes
       read_args: {query: "{key}"}

   # Bound: list_notes(limit=N) returns exactly min(N, all notes).
   relations:
     - id: list-limit
       tool: list_notes
       param: limit
       values: [1, 2]
       expect: exact

   # Two paths: every note search_notes finds is also listed by list_notes.
   agreements:
     - id: search-within-list
       left: {tool: search_notes, args: {query: ""}, field: title}
       right: {tool: list_notes, args: {limit: 100}}
       expect: subset

All keys:

``args``
   Known-good argument values, as for ``--args-file`` (see below).
``builtins``
   ``false`` turns the built-in bounds off.
``writes`` / ``exclude``
   Extra tools to treat as write tools; tools never probed.
``pairs``
   ``write``, ``read``, optional ``read_args`` (``"{key}"`` and ``"{marker}"``
   are replaced by the record's key value and first marker), ``write_args``
   and ``key`` (the key field names, overriding the heuristic).
``relations``
   ``tool``, ``param``, ``values`` (non-negative integers), ``expect``
   (``at_most``, ``exact``, ``prefix`` or ``suffix``), ``args``, ``unit``
   (``auto``, ``lines`` or ``items``) and ``id``.
``agreements``
   ``left`` and ``right`` calls (``tool``, ``args``, optional ``field`` to pick
   a key of object items) and ``expect`` (``subset``: every left item is in
   right; ``equal``).
``idempotent``
   Calls (``tool``, ``args``) that must return the same result twice.

Declared relations and agreements on a tool that is not read-only need
``--allow-writes``, like round trips.

From Python:

.. code-block:: python

   from toolscore.mcp import BoundRelation, MCPStdioClient, ProbeConfig, run_probes

   config = ProbeConfig(
       relations=[BoundRelation("read_text_file", "head", [0, 1, 3], "prefix",
                                {"path": "/tmp/sandbox/ten.txt"}, "lines")],
   )
   with MCPStdioClient(["npx", "-y", "@modelcontextprotocol/server-filesystem",
                        "/tmp/sandbox"]) as client:
       for result in run_probes(client, client.list_tools(), config=config):
           print(result.tool, result.check, result.status, result.rule, result.message)

``score_server(client, probes=config, allow_writes=False)`` runs the whole
scorecard with them.

.. _arg-values:

Argument values for sandboxed servers: ``--arg``
------------------------------------------------

Servers that accept only some values (the filesystem and git servers reject
paths outside their allowed roots) fail every generated happy path, and the
probes cannot read anything. Give them values they accept:

.. code-block:: bash

   toolscore mcp test "npx -y @modelcontextprotocol/server-filesystem /tmp/sandbox" \
     --arg path=/tmp/sandbox/notes.txt \          # every tool with a 'path' parameter
     --arg list_directory:path=/tmp/sandbox \     # one tool
     --args-file args.yaml                        # or a file of them

``NAME=VALUE`` applies to every tool that declares ``NAME``; ``TOOL:NAME=VALUE``
to one tool. Values are read as JSON when they parse (``5``, ``true``,
``["a"]``), otherwise as text; a number given for a string parameter is sent as
text. A file holds the same as ``{"*": {NAME: VALUE}, "TOOL": {NAME: VALUE}}``.
``--arg`` wins over the file. The values replace generated ones in every
happy-path scenario and are the probes' starting arguments; edge cases keep
their deliberately bad values. On ``server-filesystem@2.1.0``, giving its six
read tools a sandbox path took the grade from F (48%) to D (66%).

Limits
------

* A probe sees the server only through its tools. State it cannot read back
  (a file a tool writes but no tool lists) is ``inconclusive`` or a low/medium
  warning, never a grade failure, unless you declare the reader.
* Readers that cache, paginate (without a limit-like parameter) or apply
  eventual consistency can hide a fresh write; declare the right reader and
  arguments.
* Write tools that need existing data (``add_observations`` needs an existing
  entity) are inconclusive with generated values; give them values with
  ``--arg`` or ``write_args``.
* State that only breaks under conditions the tools cannot create (#4885 needs
  a corrupted file before the write) is out of reach.
* Probes run over stdio or HTTP, like the scorecard.
