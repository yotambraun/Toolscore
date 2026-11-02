For Researchers
===============

Run agents against MCP servers repeatably, compare variants with honest
statistics, and keep every run re-scorable. Toolscore is tool-level truth: did
each call happen, succeed, do what it reported, and get reported honestly. For a
full study (design, pre-registration, grading, reports), `Agent Eval Flow
<https://github.com/guybass/agent-eval-flow>`__ builds on it.

1. Check before you spend
-------------------------

.. code-block:: bash

   toolscore doctor --spec study.yaml       # packages, keys (by name only), server, build, prices, budget
   toolscore agent run study.yaml --dry-run

``toolscore agent run`` runs tasks x arms x repetitions of an LLM agent (OpenAI
Responses API, Anthropic Messages, or a free scripted provider) against any MCP
server: a guard on every tool call, a hard budget checked before every model
call (unknown prices are refused), per-run limits, a seeded shuffled order,
build verification of the server, and resumable JSONL with one row per run
(:doc:`agent_harness`).

2. Run and compare
------------------

``examples/agent_harness/`` is an offline study with the scripted provider: a
"careful" and a "sloppy" arm, six runs each, and decision rules declared before
the runs. Real output, shortened:

.. code-block:: text

   $ toolscore agent run offline.yaml -o runs.jsonl
   $ toolscore compare --runs runs.jsonl --k 2 --min-n 6 --protocol protocol.yaml
                                      Runs per variant                                   
   ┏━━━━━━━━━┳━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┓
   ┃ Variant ┃ N ┃ pass/fail/err/unk ┃ Pass rate [95% CI] ┃ pass^2 ┃ Cost/run ┃ Latency ┃
   ┡━━━━━━━━━╇━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━┩
   │ careful │ 6 │           6/0/0/0 │   100% [61%, 100%] │   100% │  $0.0000 │   0.00s │
   │ sloppy  │ 6 │           0/6/0/0 │       0% [0%, 39%] │     0% │  $0.0000 │   0.00s │
   └─────────┴───┴───────────────────┴────────────────────┴────────┴──────────┴─────────┘
   …
   Decision (careful vs sloppy): adopt  protocol sha256 aa9c071bcf44...

The table counts every run, including errors and unknowns, with Wilson
intervals; differences use Fisher's exact test; ``pass^k`` is the chance that
``k`` runs in a row pass. ``toolscore select`` picks a variant by
lexicographic, weighted or Pareto objectives (:doc:`comparing_runs`).

3. Keep every run re-scorable
-----------------------------

.. code-block:: bash

   toolscore regrade runs.jsonl --spec study.yaml -o runs.regraded.jsonl   # new rules, nothing re-run
   toolscore eval contract.json trace.json --receipt run.receipt.json      # content-hashed record
   toolscore export --format aef runs.jsonl -o runs.aef.jsonl              # neutral run records

Every check is pass, fail or unknown, never a silent pass: a run without a final
answer has unknown honesty, and missing latency or cost is unknown, not 0
(:doc:`receipts`).

4. Measure honesty, not only accuracy
-------------------------------------

Each run row carries the honesty findings and the ``false_success`` counts, so a
study can report how often an agent claimed success after a failure, next to
its pass rate. For controlled failures, put the server behind
``toolscore mcp proxy --inject`` (:doc:`fault_injection`); for existing
datasets, ``toolscore_scorer()`` scores Inspect AI tasks the same way
(:doc:`frameworks`), and :doc:`coding_sessions` reads Claude Code and Codex
CLI sessions. The MCP memory server case study (issue #4887, found with Agent
Eval Flow and Toolscore and fixed upstream) is in :doc:`what_it_catches`.
