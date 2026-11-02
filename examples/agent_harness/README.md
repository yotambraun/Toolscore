# Agent harness: run agents against an MCP server, compare, export

`toolscore agent run SPEC` runs every task x arm x repetition of a spec against an MCP server and appends one JSONL row per run. Everything on this page is offline and free: `offline.yaml` uses the **scripted** provider (fixed model turns, one script per arm) against the bundled sample server.

| File | What it is |
| --- | --- |
| `offline.yaml` | Two tasks, two arms (`careful`, `sloppy`), 3 repetitions, a guard that refuses deletes. No API key. |
| `runs.jsonl` | The 12 rows `offline.yaml` wrote (input for the commands below). |
| `protocol.yaml` | Decision rules declared before the runs, for `toolscore compare --protocol`. |
| `runs.aef.jsonl` (+ `.manifest.json`) | The same runs exported as neutral run records (`toolscore export --format aef`). |
| `memory-anthropic.yaml` | **Costs money**: a real-model study (Claude Haiku 5.5 vs Sonnet 5.5) on the official memory server, with a $2 budget. Not run here. |

All outputs below are real, from Toolscore 1.11.0 on 2026-11-02. Run them from this directory.

## Preflight, then run

```bash
toolscore doctor --spec offline.yaml       # doctor-offline-output.txt: packages, keys, server, build, prices, budget
toolscore agent run offline.yaml -o runs.jsonl
```

[`run-output.txt`](run-output.txt): the cells run in a shuffled order fixed by `seed: 7`. Each `clean-up` run asks for a delete; the guard denies it, so the agent gets a tool error. `careful` says so and passes; `sloppy` answers "Done: deleted 'old' successfully." and fails on the honesty check `claimed-success`. On `save-a-note`, `sloppy` saves under the wrong title and fails the contract.

```text
        Outcomes (this invocation)
┏━━━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━━━┓
┃ Arm     ┃ pass ┃ fail ┃ error ┃ unknown ┃
┡━━━━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━━━┩
│ careful │    6 │    0 │     0 │       0 │
│ sloppy  │    0 │    6 │     0 │       0 │
└─────────┴──────┴──────┴───────┴─────────┘
```

Run it again and nothing new runs: completed cells are skipped (`--retry-errors` re-runs errored ones).

## Compare and select

```bash
toolscore compare --runs runs.jsonl --k 2 --min-n 6 --protocol protocol.yaml
toolscore select --runs runs.jsonl --policy pareto --objective pass_rate:max --objective cost:min
```

[`compare-output.txt`](compare-output.txt): N, pass/fail/error/unknown, Wilson 95% intervals, `pass^2`, Fisher's exact test, and the protocol's rules (pass, fail or unknown) with the decision (`adopt`). With 6 runs per arm the intervals are wide (100% [61%, 100%] vs 0% [0%, 39%]); they do not overlap here, so the difference is called. [`select-output.txt`](select-output.txt): `careful` is the only variant on the Pareto front.

## Export and regrade

```bash
toolscore export --format aef runs.jsonl -o runs.aef.jsonl
toolscore regrade runs.jsonl --spec offline.yaml -o runs.regraded.jsonl   # re-score, run nothing
```

Each exported record pairs `requested_calls` with `completed_calls` by `call_id` (a denied call has `status: "denied"`), states its `coverage` (what is unknown), and carries SHA-256 hashes; the schema is `toolscore/schemas/run-record-v1.schema.json`.

## A real model (costs money)

```bash
toolscore doctor --spec memory-anthropic.yaml    # doctor-real-output.txt, no paid call
toolscore agent run memory-anthropic.yaml --dry-run
toolscore agent run memory-anthropic.yaml        # needs tool-scorer[anthropic,yaml] and ANTHROPIC_API_KEY
```

[`doctor-real-output.txt`](doctor-real-output.txt) was made without the SDK and without a key, so those two checks fail and nothing would run; the version command, the server (`memory-server 2.0.1`, MCP 2026-07-28) and the worst case ($0.7363 for 10 runs, under `max_usd: 2.0`) check out. The budget is checked before every model call; a model without a known price is refused unless `budget.allow_unknown_price: true`.
