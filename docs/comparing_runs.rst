Comparing Runs
==============

An agent that passes 7 times out of 10 and one that passes 9 times out of 10
may not be different at all. ``toolscore compare --runs`` and ``toolscore
select`` read repeated runs per variant and say what the data supports, with
light, standard-library statistics. For a full study (design, pre-registration,
grading, reports), use `Agent Eval Flow <https://github.com/guybass/agent-eval-flow>`_.

Inputs
------

* ``--runs runs.jsonl`` (repeatable): rows from ``toolscore agent run`` or
  records from ``toolscore export``. The variant is ``arm_id`` (or
  ``variant``, ``arm``, ``model``; ``--variant-key`` picks another field), the
  task ``task_id``, the outcome ``outcome`` (else ``passed``, else ``status:
  error``, else unknown), the cost ``cost_usd`` and the latency ``duration_s``.
* ``GOLD --variant NAME=DIR`` (repeatable): every ``*.json`` trace in ``DIR``
  scored against ``GOLD`` (a gold file or contract). A trace passes at
  ``--min-score`` (0.9) with no error-severity honesty finding; a trace that
  cannot be read is an ``error`` run. File names give the task:
  ``search-3.json`` and ``search_r2.json`` are both task ``search``.

The one-trace-per-model form, ``toolscore compare GOLD TRACE...``, is unchanged.

What it reports
---------------

Per variant:

* **complete populations**: ``N`` runs and how many ``pass``, ``fail``,
  ``error`` and ``unknown``. Errored and unknown runs stay in the
  denominator: a run that crashed did not pass;
* the **pass rate with a 95% Wilson interval**;
* **pass^k** (``--k``): the probability that ``k`` runs of a task all pass,
  estimated per task with the unbiased estimator ``C(c, k) / C(n, k)`` for
  ``c`` passes in ``n`` runs (as in tau-bench), averaged over the tasks with at
  least ``k`` runs (the others are counted and left out);
* mean **cost** and **latency** over the runs that have them, with how many
  do (``unknown`` when none do; never 0).

Per pair (each variant against ``--baseline``, or every pair): the difference
in pass rate and a **two-sided Fisher exact test**. A difference is **not
distinguishable** when either variant has fewer than ``--min-n`` runs (10), the
95% intervals overlap, or ``p >= --alpha`` (0.05). ``--json`` writes it all.

Real output (``examples/agent_harness/``):

.. code-block:: text

   $ toolscore compare --runs runs.jsonl --k 2 --min-n 6 --protocol protocol.yaml
                                      Runs per variant
   ┏━━━━━━━━━┳━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┓
   ┃ Variant ┃ N ┃ pass/fail/err/unk ┃ Pass rate [95% CI] ┃ pass^2 ┃ Cost/run ┃ Latency ┃
   ┡━━━━━━━━━╇━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━┩
   │ careful │ 6 │           6/0/0/0 │   100% [61%, 100%] │   100% │  $0.0000 │   0.00s │
   │ sloppy  │ 6 │           0/6/0/0 │       0% [0%, 39%] │     0% │  $0.0000 │   0.00s │
   └─────────┴───┴───────────────────┴────────────────────┴────────┴──────────┴─────────┘
                                    Pass-rate differences
   ┏━━━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
   ┃ A       ┃ B      ┃ B - A ┃ Fisher p ┃ Verdict                                        ┃
   ┡━━━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
   │ careful │ sloppy │ -100% │    0.002 │ careful has the higher pass rate (p = 0.00216) │
   └─────────┴────────┴───────┴──────────┴────────────────────────────────────────────────┘

Pre-declared decision rules
---------------------------

``--protocol protocol.yaml`` evaluates decision rules written **before** the
runs (light pre-registration; record the file, or the ``protocol sha256`` the
report prints, before you run):

.. code-block:: yaml

   protocol_version: 1
   title: careful beats sloppy
   baseline: sloppy
   candidate: careful
   alpha: 0.05
   min_runs: 6            # runs per variant before any rule can pass
   rules:
     - {id: higher-pass-rate, metric: pass_rate, expect: candidate_better}
     - {id: no-more-errors, metric: error_rate, expect: not_worse}
     - {id: cost-per-run, metric: cost, max: 0.01}

A rule has a ``metric`` (``pass_rate``, ``pass_lower``, ``pass_hat_k``,
``cost``, ``latency``, ``error_rate``, ``unknown_rate``) and ``expect:
candidate_better`` (for pass rates: distinguishable by the test above; for
other metrics: better by more than ``tolerance``), ``expect: not_worse`` (not
worse by more than ``tolerance``), or ``min`` / ``max`` bounds on the
candidate. Each rule is ``pass``, ``fail`` or ``unknown`` (fewer than
``min_runs`` runs, or the metric is unknown: never a pass), and the decision is
``adopt`` (every rule passed), ``reject`` (a rule failed; exit 1) or
``undecided``.

.. code-block:: text

   ┃ Rule             ┃ Status ┃ Detail                                         ┃
   │ higher-pass-rate │ pass   │ careful has the higher pass rate (p = 0.00216) │
   │ no-more-errors   │ pass   │ error_rate change +0 >= -0.0                   │
   │ cost-per-run     │ pass   │ cost 0 <= 0.01                                 │
   Decision (careful vs sloppy): adopt  protocol sha256 aa9c071bcf44...

Choosing a variant
------------------

``toolscore select`` (inspired by Agent Eval Flow's selection policies) ranks
the variants on objectives in priority order (``--objective METRIC[:max|min]``,
default ``pass_rate:max``, ``cost:min``, ``latency:min``) with a policy:

* ``lexicographic``: best on the first objective, ties broken by the next;
* ``weighted``: each objective scaled to ``[0, 1]`` across the variants (1 is
  best), weighted (``--weight cost=2``) and summed;
* ``pareto``: the variants no other variant beats on every objective; the first
  objective breaks a tie.

It always prints the **Pareto front**, and reports the variants whose value is
unknown for an objective (ranked worst, never treated as 0).

.. code-block:: text

   $ toolscore select --runs runs.jsonl --policy pareto --objective pass_rate:max --objective cost:min
   Policy pareto  (pass_rate:max, cost:min)
   Ranking: careful > sloppy
   Pareto front: careful
   Selected: careful (the only variant on the Pareto front)

Python
------

.. code-block:: python

   from toolscore.stats import (
       compare_runs, evaluate_protocol, fisher_exact, load_runs, pass_hat_k,
       select_variant, wilson_interval,
   )

   comparison = compare_runs(load_runs(["runs.jsonl"]), k=2, min_n=10)
   for v in comparison.variants:
       print(v.variant, v.n, v.counts, v.pass_rate, v.interval, v.pass_hat_k)
   print(select_variant(comparison, "pareto", ["pass_rate:max", "cost:min"]).chosen)

   wilson_interval(7, 10)        # (0.3968..., 0.8922...)
   fisher_exact(1, 9, 11, 3)     # 0.00276
   pass_hat_k(3, 5, 2)           # 0.3
