For MCP Server Authors
======================

Grade your server, check that its tools really do what they report, show the
grade in your README and keep it from slipping in CI. Everything here calls your
server's tools locally; no model is involved.

1. Grade it
-----------

.. code-block:: bash

   pip install tool-scorer            # add [http] for a remote server
   toolscore mcp test "python my_server.py" --badge .github/badges/mcp-grade.svg

The scorecard generates happy-path and edge-case calls from each tool's schema,
runs them, lints the definitions and ranks what to fix. Real output on the
bundled sample server (``python -m toolscore.mcp.sample_server``), shortened:

.. code-block:: text

   ╭──────────────────────────────────────╮
   │ MCP Scorecard: notes-server 1.1.0    │
   │ Grade B   Score 86%                  │
   │ happy 80%  |  edge 100%  |  lint 91% │
   │ MCP 2026-07-28 (stateless)           │
   ╰──────────────────────────────────────╯
   …
   Top issues to fix
     1. export_notes  fails on valid input (export failed: storage backend not configured)
        -> The tool errors on well-formed arguments - check the handler and that the input 
   schema matches what the tool actually accepts.
     2. delete_note  property 'note_id' is missing a 'type'
   …
   Badge (grade B) written to .github/badges/mcp-grade.svg.

``toolscore mcp lint`` runs only the static checks, with stable rule IDs
(:doc:`mcp_testing`). Servers that need real paths or IDs get them with
``--arg path=/tmp/sandbox/notes.txt`` or ``--args-file``.

2. Check that the tools really do it
------------------------------------

A tool can answer "saved" and store nothing. Effect probes write marked values,
read them back, write again to the same key and check bounds such as ``limit``.
Point write probes at a disposable instance: they leave ``tsp<hex>-`` records.

.. code-block:: bash

   toolscore mcp test "python my_server.py" --probes                  # read-only bounds
   toolscore mcp test "python my_server.py" --probes --allow-writes   # round trips

On the sample server's ``--bug silent-skip`` mode (real output, shortened):

.. code-block:: text

   create_note on an existing title says it saved the note and changes nothing. Effect probes 
   write marked notes, write again to the same title and read them back (they run only against 
   this disposable server).

   ╭────────────────────────────────────────────────────╮
   │ MCP Scorecard: notes-server 1.1.0                  │
   │ Grade C   Score 74%                                │
   │ happy 80%  |  edge 100%  |  lint 91%  |  effect 0% │
   │ MCP 2026-07-28 (stateless)                         │
   ╰────────────────────────────────────────────────────╯
                            Tools                          
   ┏━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
   ┃ Tool         ┃ Scenarios ┃ Avg latency ┃ Def. tokens ┃
   ┡━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
   │ create_note  │       6/6 │      2.9 ms │          80 │
   │ list_notes   │       6/6 │      3.6 ms │          59 │
   │ search_notes │       6/6 │      2.3 ms │          48 │
   │ delete_note  │       6/6 │      3.8 ms │          52 │
   │ export_notes │       3/6 │      2.8 ms │          64 │
   └──────────────┴───────────┴─────────────┴─────────────┘
   Tool definitions cost ~303 estimated tokens of context across 5 tool(s).
                                          Effect probes                                        
   ┏━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
   ┃ Probe      ┃ Tool        ┃ Result ┃ Confidence ┃ Detail                                  ┃
   ┡━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
   │ bound      │ list_notes  │ pass   │ medium     │ limit bounded the result for [1, 2]     │
   │ round-trip │ create_note │ FAIL   │ high       │ a second write to key 'tspefdcdf-title' │
   │            │             │        │            │ reported success; state unchanged       │
   │            │             │        │            │ (probe-silent-noop)                     │
   └────────────┴─────────────┴────────┴────────────┴─────────────────────────────────────────┘
   Probe evidence: 1 pass, 1 fail, 0 unknown (inconclusive is never a pass).

A high-confidence probe failure caps the grade at C. On the official memory
server, ``server-memory@2026.8.31`` (before the #4887 fix) gets
``probe-silent-noop`` on ``create_entities`` and grade C; ``2.0.1`` passes
(:doc:`effect_probes`). A probe config declares exact pairs and bounds when the
heuristics cannot find them.

3. Show the grade and gate CI
-----------------------------

.. code-block:: markdown

   [![MCP grade](.github/badges/mcp-grade.svg)](https://github.com/yotambraun/toolscore)

.. code-block:: yaml

   - uses: yotambraun/toolscore@v1
     with:
       mcp-command: 'python my_server.py'
       mcp-fail-under: 'B'
       mcp-probes: 'true'
       mcp-badge: .github/badges/mcp-grade.svg

``examples/github_actions/mcp-badge.yml`` commits the badge when the grade
changes (:doc:`ci`).

4. Pin what you ship
--------------------

``toolscore mcp pin`` writes ``toolscore.lock.json`` with a hash of every tool
definition and a read/write/delete/network/exec capability manifest; ``mcp
diff`` shows what changed between two builds, so a release that renames a
parameter or adds a delete tool is a reviewed change, not a surprise for your
users (:doc:`pinning_diff`).
