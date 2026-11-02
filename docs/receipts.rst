Receipts & Regrade
==================

Record once, re-score forever (an idea from Agent Eval Flow). A trace is
evidence; the contract and the weights are a judgment about it. Toolscore keeps
the two apart: a **receipt** says exactly what was evaluated and how, and
``toolscore regrade`` re-scores the same evidence under a new contract or new
weights without running the agent, the model or the MCP server again.

Receipts
--------

.. code-block:: bash

   toolscore eval gold.json trace.json --receipt run.receipt.json

A receipt (``kind: "toolscore.evaluation"``, ``receipt_version`` "1") holds:

* ``inputs``: every input file (``gold``, ``trace``, ``forbidden``,
  ``honesty_config``, ``injected``) with its path, SHA-256 and size;
* ``settings``: the trace format, side-effect validation, the LLM judge model,
  the normalized weights, and the SHA-256 of a final answer given with
  ``--final-answer``;
* ``contract_sha256``: the hash of the expected calls as canonical JSON;
* ``toolscore_version`` and ``created_at``;
* ``result``: the score, grade, required-call recall, and ``record_sha256``,
  the hash of the full :meth:`~toolscore.core.EvaluationResult.to_dict`
  record (deterministic: the same evaluation always hashes the same);
* ``receipt_sha256``: the hash of everything above, so a changed receipt is
  detectable too.

Hashes are of canonical JSON (sorted keys, no whitespace, UTF-8), except
input files, which are hashed as bytes on disk.
:func:`toolscore.receipts.verify_receipt` re-checks a receipt and its inputs.

Regrade
-------

.. code-block:: bash

   toolscore regrade run.receipt.json --gold contract-v2.json
   toolscore regrade run.receipt.json --weight required_call_recall=0.3 --receipt-dir receipts/
   toolscore regrade trace.json --gold gold.json            # a bare trace needs --gold
   toolscore regrade runs.jsonl --spec study-v2.yaml -o runs.v2.jsonl   # agent runs

Given a receipt, ``regrade`` first checks that the trace (and the other
inputs) still match their hashes, and refuses when they do not (``--no-verify``
regrades anyway and prints the problems). The receipt's gold file, format,
weights and forbidden rules are the defaults; ``--gold``, ``--weight`` and
``--forbidden`` replace them. It prints the score and grade before and after,
writes new receipts with ``--receipt-dir`` (each names the receipt it came
from in ``settings.regraded_from``) and the table with ``--json``.

For ``toolscore agent run`` JSONL files, ``--spec`` (new task definitions by
task ID) or ``--gold`` (new expected calls for every row) re-evaluates every
recorded run: the calls, results and final answers stay as recorded; the
``evaluation``, ``outcome`` and ``passed`` are new, and ``regraded.from_sha256``
is the hash of the original row.

Real output (``examples/contracts/``): the same trace, graded F against the gold
file it was recorded with, regraded against a contract.

.. code-block:: text

   $ toolscore regrade run.receipt.json --gold contract.json
                        Regrade
   ┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
   ┃ Source           ┃  Before ┃   After ┃ Change ┃
   ┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
   │ run.receipt.json │ 38.3% F │ 95.7% A │ +57.4% │
   └──────────────────┴─────────┴─────────┴────────┘
   Nothing was re-run: same traces, new contract or weights.

Python: :func:`toolscore.regrade` returns a :class:`~toolscore.receipts.Regrade`
(``result``, ``receipt``, ``previous``, ``score_delta``, ``problems``);
:func:`toolscore.build_receipt` builds a receipt for any evaluation.

Tri-state evidence
------------------

A check that lacks the data it needs does not pass. Every evaluation reports
its checks as ``pass``, ``fail`` or ``unknown``, with the reason, and counts
them: ``Evidence: 4 pass, 0 fail, 3 unknown`` in the console, a table in the
Markdown and HTML reports, ``evidence`` in the JSON report and in
``to_dict()``, and :attr:`~toolscore.core.EvaluationResult.evidence` in Python.

=====================  ====================================================  ==============================
Check                  Pass when                                             Unknown when
=====================  ====================================================  ==============================
``required-calls``     every required call was made and did not fail         nothing was required; or the
                                                                             calls were made but the trace
                                                                             has no result or error for
                                                                             them
``call-errors``        no call failed                                        no call has a result or error
``forbidden-calls``    no forbidden call (only with rules)                   never
``credentials``        no credential in tool arguments                       never
``claimed-success``    no success claim over a failure                       no final answer, or one not in
                                                                             English
``disclosure``         every warning, unrecovered error and injected fault   no final answer, or no tool
                       was disclosed                                         results in the trace
``escape-hatch``       no code-execution call got around a refusal           no tool results in the trace
``side-effects``       every declared side effect validated (when declared)  never
=====================  ====================================================  ==============================

``coverage`` says how much of the trace holds the evidence: calls with an
outcome, a duration and a cost, and whether the final answer is known. The same
rule runs through every new feature: the honesty checks report ``results:
"missing"`` for a trace with only requests; an inconclusive effect probe is
``unknown`` probe evidence (the scorecard's ``probe_evidence``); an unknown
price makes a run's cost ``null``; and an exported run record lists what is
unknown.

Unknown, never 0: latency and cost
----------------------------------

``latency_metrics`` and ``cost_metrics`` are always present, with a ``status``:
``measured`` (every call has the value), ``partial`` (some do; the totals cover
those) or ``unknown`` (none do; the totals are ``null``). Reports print
``unknown``, or ``1.234s (3 of 5 calls)``, never ``0``. A measured ``0.0`` is
shown as ``0.000s``. The JSON report's summary adds ``total_duration``,
``total_cost``, ``latency_status`` and ``cost_status``.

Complete records
----------------

:meth:`~toolscore.core.EvaluationResult.to_dict` (``schema_version`` "2") and
the JSON report carry the composite score, the grade, the normalized weights,
every metric, the evidence, and every call: expected calls with their
arguments (matchers as their ``repr``), actual calls with ``id``, arguments,
``result``, ``is_error``, ``error``, ``duration``, ``cost`` and ``timestamp``
(``null`` when the trace does not have them). :attr:`ToolCall.id
<toolscore.adapters.base.ToolCall.id>` is the provider's call ID or the JSON-RPC
request ID.
