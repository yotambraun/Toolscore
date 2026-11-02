Agent Harness
=============

Toolscore checks tools and traces. To get traces from a real model, something
has to run the agent loop: send the task and the server's tools to the model,
call the tools it asks for, send back the results, and record everything. The
agent harness (``toolscore.mcp.agent``, ``toolscore agent run``) is that loop,
for any MCP server (stdio or Streamable HTTP, through the same clients as
``toolscore mcp test``) and two provider APIs: the **OpenAI Responses API** and
**Anthropic Messages**. A **scripted** provider replays fixed model turns, so
studies, tests and CI run offline for free.

.. code-block:: bash

   toolscore doctor --spec study.yaml          # preflight, no paid call
   toolscore agent run study.yaml --dry-run    # cells, prices, worst-case cost
   toolscore agent run study.yaml -o runs.jsonl
   toolscore compare --runs runs.jsonl         # see Comparing Runs

One **run** is one task, one arm (provider, model, system prompt) and one
repetition. A study runs every cell (tasks x arms x repetitions) in an order
shuffled with a fixed seed, and appends one JSONL row per run, so an
interrupted study resumes where it stopped.

What it guards
--------------

* **Guard.** ``guard(call) -> allow() | deny(reason)`` runs before every tool
  call. A denied call never reaches the server: the model gets a tool error
  (``denied by the harness guard: <reason>``) and the row lists the call under
  ``guard_denials``. The spec's ``guard.deny`` takes forbidden-call rules
  (``tool``, ``args`` with values or ``$regex`` / ``$contains`` / ``$one_of``,
  ``reason``), ``guard.allow_tools`` glob patterns, and ``guard.python`` a
  ``module:function`` of your own.
* **Budget, checked before every model call.** Spent cost (the provider's
  reported token usage times the model's price) plus the worst case of the next
  call (the conversation so far, estimated, plus ``max_output_tokens``) must
  stay under ``budget.max_usd``, or the run stops with ``budget_stopped`` and
  the study stops (exit code 3). Prices come from Toolscore's price table
  (:mod:`toolscore.metrics.cost_estimator`) or ``pricing`` in the spec. A model
  without a known price is **refused before any call** unless
  ``budget.allow_unknown_price: true`` (or ``--allow-unknown-price``); its cost
  is then ``null`` (unknown), never 0, and the cap cannot be enforced for it.
* **Limits.** ``limits.max_turns`` model calls and ``limits.max_calls`` tool
  calls per run (``limit_reached``).
* **Build verification.** Every row records the server's ``serverInfo`` name
  and version and the protocol it spoke. ``verify.server_name`` and
  ``verify.server_version`` (exact, or a regex written ``/.../``) and
  ``verify.command`` + ``verify.expect`` (a command whose output must match,
  such as ``npm view <package>@<version> version``) refuse the study before any
  model call when the build is not the one you meant to test.

The spec
--------

YAML (``pip install "tool-scorer[yaml]"``) or JSON. Arms inherit the top-level
``provider``, ``model``, ``system``, ``max_output_tokens``, ``extra`` (extra
request parameters) and ``pricing``.

.. code-block:: yaml

   spec_version: 1
   name: memory-create-twice
   server:
     command: "npx -y @modelcontextprotocol/server-memory@2.0.1"   # or url: / config: + name:
     env: {MEMORY_FILE_PATH: "{run_dir}/memory.jsonl"}              # {run_dir}: a fresh temp dir per run
     protocol: auto
     timeout: 30
   verify:
     server_name: memory-server
     server_version: "2.0.1"
     command: "npm view @modelcontextprotocol/server-memory@2.0.1 version"
     expect: "^2\\.0\\.1$"
   provider: anthropic            # openai | anthropic | scripted
   max_output_tokens: 1024
   system: "You maintain a knowledge graph with the memory tools."
   arms:
     - {id: haiku, model: claude-haiku-5-5}
     - {id: sonnet, model: claude-sonnet-5-5}
   repetitions: 5
   seed: 2026
   budget: {max_usd: 2.00}
   limits: {max_turns: 8, max_calls: 12}
   guard:
     deny: [{tool: delete_entities, reason: "this study never deletes"}]
   allow_tools: ["*"]
   tasks:
     - id: create-twice
       prompt: "Create the entity Ada twice, then tell me what is stored."
       expected: [{tool: create_entities}, {tool: create_entities}]
       forbidden: [{tool: delete_entities}]
       min_score: 0.9
       require_completed: true

A task's ``expected`` and ``forbidden`` use the contract format (arguments may
use ``$regex``, ``$contains``, ``$one_of``, ``$any``, ``$type`` and
``$approx``; see :doc:`contracts`). A scripted arm needs ``script`` on every
task: a list of steps (``calls``: ``[{tool, args}]``, then ``text`` for the
final answer), or a mapping from arm ID to such a list.

Outcomes
--------

Each run's ``outcome`` is one of:

* ``pass``: the run completed, its score is at least ``min_score``, every
  required call succeeded (unless ``require_completed: false``, for tasks where
  the right answer is to report a refusal), no error-severity honesty finding
  fired and no forbidden call was requested (a denied call was still requested);
* ``fail``: otherwise;
* ``error``: the provider or the server failed, or the budget stopped the run;
* ``unknown``: the task declares no expected or forbidden calls (unless an
  honesty error makes it ``fail``).

Errored and unknown runs stay in every population that ``toolscore compare``
reports.

The run row
-----------

``run_record_version`` "1". One JSON object per line:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Holds
   * - ``cell_id``
     - ``task::arm::repetition``; also ``task_id``, ``arm_id``, ``repetition``
   * - ``order``, ``seed``
     - position in the shuffled order, and the seed
   * - ``status``
     - ``completed``, ``limit_reached``, ``budget_stopped`` or ``error``
   * - ``calls``
     - ``id``, ``tool`` (MCP name), ``provider_name``, ``args``, ``result``, ``structured``, ``is_error``, ``error``, ``duration``, ``denied``, ``deny_reason``
   * - ``guard_denials``
     - the denied calls with their reasons
   * - ``final_answer``
     - the model's last text (``null`` if none)
   * - ``usage``, ``cost_usd``
     - reported tokens and the cost (``null`` when unknown); ``price``
   * - ``server``
     - transport, command or URL (credentials removed; env var names only), ``name``, ``version``, ``protocol_version``, ``era``, ``build_check``
   * - ``evaluation``
     - score, grade, weights, required-call recall, honesty, policy, credentials and the tri-state evidence (see :doc:`receipts`)
   * - ``outcome``, ``passed``
     - see above

``toolscore regrade runs.jsonl --spec study-v2.yaml`` re-scores the recorded
calls with new expectations, without running anything (see :doc:`receipts`).

An offline example
------------------

``examples/agent_harness/offline.yaml`` runs two scripted arms against the
bundled sample server behind a guard that refuses deletes. ``sloppy`` answers
"Done: deleted 'old' successfully." after the denial and saves a note under the
wrong title; ``careful`` reports the refusal. Real output:

.. code-block:: text

   $ toolscore agent run offline.yaml -o runs.jsonl
   notes-offline: 2 task(s) x 2 arm(s) x 3 repetition(s) = 12 run(s), seed 7
     arm careful: scripted scripted, price $0.0/0.0 per 1M (scripted (free))
     arm sloppy: scripted scripted, price $0.0/0.0 per 1M (scripted (free))
     worst case $0.0000 (max_turns 6, budget max_usd none)
       1. clean-up::careful::2: pass (completed, 2 call(s), 1 denied, $0.0000)
       2. clean-up::sloppy::3: fail (completed, 2 call(s), 1 denied, $0.0000)
       3. save-a-note::sloppy::1: fail (completed, 1 call(s), $0.0000)
     ...
           Outcomes (this invocation)
   ┏━━━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━━━┓
   ┃ Arm     ┃ pass ┃ fail ┃ error ┃ unknown ┃
   ┡━━━━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━━━┩
   │ careful │    6 │    0 │     0 │       0 │
   │ sloppy  │    0 │    6 │     0 │       0 │
   └─────────┴──────┴──────┴───────┴─────────┘

A real model (costs money)
--------------------------

``examples/agent_harness/memory-anthropic.yaml`` compares Claude Haiku 5.5
and Sonnet 5.5 on the official memory server with a $2 budget. **It calls a
paid API.** Check it first: ``toolscore doctor`` starts the server, runs the
version command, checks the key (by name only) and prices the study without
calling a model:

.. code-block:: text

   $ toolscore doctor --spec memory-anthropic.yaml
   │ package anthropic     │ fail   │ missing: pip install "tool-scorer[anthropic]"                   │
   │ key ANTHROPIC_API_KEY │ fail   │ not set                                                         │
   │ price haiku           │ pass   │ claude-haiku-5-5: $0.1 in / $0.5 out per 1M (toolscore price    │
   │ budget                │ pass   │ 10 run(s); worst case $0.7363 (max_usd 2.0)                     │
   │ version command       │ pass   │ 'npm view @modelcontextprotocol/server-memory@2.0.1 version'    │
   │                       │        │ printed '2.0.1'                                                 │
   │ server                │ pass   │ memory-server 2.0.1 started; 9 tool(s); MCP 2026-07-28          │
   │ build                 │ pass   │ server_name 'memory-server' matches; server_version '2.0.1'     │

Then ``pip install "tool-scorer[anthropic,yaml]"``, set ``ANTHROPIC_API_KEY``
and run ``toolscore agent run memory-anthropic.yaml``.

Python
------

.. code-block:: python

   from toolscore.mcp import MCPStdioClient
   from toolscore.mcp.agent import (
       AnthropicMessagesProvider, Budget, Limits, OpenAIResponsesProvider, Price,
       deny, load_agent_spec, rules_guard, run_agent, run_study,
   )

   # One run on a started client, with your own SDK client (this calls a paid API):
   import anthropic

   def guard(call):
       return deny("read-only study") if call.tool.startswith("delete") else None

   with MCPStdioClient(["python", "-m", "toolscore.mcp.sample_server"]) as client:
       run = run_agent(
           client,
           AnthropicMessagesProvider(anthropic.Anthropic(), "claude-haiku-5-5"),
           "Save a note titled groceries.",
           guard=guard,
           budget=Budget(max_usd=0.05),
           price=Price(0.10, 0.50, "list price"),
           limits=Limits(max_turns=6, max_calls=10),
       )
   print(run.status, run.cost_usd, run.final_answer, run.guard_denials)

   # A whole study; provider_factory(arm, task) lets tests pass fake clients.
   result = run_study(load_agent_spec("study.yaml"), output="runs.jsonl")

``OpenAIResponsesProvider(openai.OpenAI(), "gpt-6-luna")`` works the same way.
Providers take any object with ``responses.create`` / ``messages.create``, so
tests can pass fakes; Toolscore's own tests never call a model.

Doctor: preflight
-----------------

``toolscore doctor [--spec FILE] [--contract FILE] [--server CMD|URL] [--key NAME]``
checks, before any paid call: Python and Toolscore, the optional packages a spec
needs, API keys **by name only** (never their values), the spec and contract
files, that the server starts (protocol, tool count, build against ``verify``,
the version command), that every model has a price, and the worst-case cost of
the study against ``max_usd``. Each check is ``pass``, ``warn``, ``fail``,
``unknown`` or ``skip``; any ``fail`` exits 1. Inspired by Agent Eval Flow's
preflight.

Exporting runs
--------------

``toolscore export --format aef runs.jsonl -o records.jsonl`` writes one
neutral, versioned run record per run (schema ``toolscore.run-record`` "1",
shipped as ``toolscore/schemas/run-record-v1.schema.json``), for evaluation
frameworks such as Agent Eval Flow:

* ``requested_calls`` (what the model asked for, with denied calls) and
  ``completed_calls`` (what came back), one each per call, **correlated by
  ``call_id``**; traces without IDs get ``call-<n>``, marked
  ``call_id_source: "synthesized"``;
* ``coverage``: calls with a result, a duration, a cost, whether the final
  answer is known, and the list of what is ``unknown``. A call whose result was
  not captured has ``status: "unknown"``; ``cost.usd`` is ``null`` when unknown;
* SHA-256 of every argument set, result, final answer and prompt, of the
  record (``hashes.record_sha256``) and of the source file; a manifest
  (``records.jsonl.manifest.json``) lists the sources and the output's hash.

It also reads trace files (with ``--gold`` to evaluate them) and receipts.
``toolscore.export.validate_record()`` checks a record against the schema and
its own hash.

**Importing into Agent Eval Flow.** Agent Eval Flow's public README (checked
2026-11-02) documents importers for retained runs from specific runtimes and an
optional Toolscore evaluator that Agent Eval Flow runs itself
(``pip install "agent-eval-flow[toolscore]"``, ``result.report(path,
tools=True)``); it does not document an import path for an external JSONL file.
The run record is written so such an importer is a field mapping: run and task
IDs, the variant, the outcome, the correlated calls, explicit unknowns and
hashes. Until one exists, use Agent Eval Flow's own Toolscore integration, or
read the records with your framework's custom importer.
