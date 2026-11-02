<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <img src="assets/logo.svg" alt="Toolscore Logo" width="360"/>
  </picture>
</p>

<h1 align="center">Toolscore</h1>

<p align="center">
  <strong>Correct tool calls are not enough.</strong><br/>
  Toolscore checks that the tool really did it, and that the agent told the truth about it.<br/>
  <em>Deterministic, local, $0 per run, made for CI.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/tool-scorer/"><img src="https://badge.fury.io/py/tool-scorer.svg" alt="PyPI version"/></a>
  <a href="https://pypi.org/project/tool-scorer/"><img src="https://img.shields.io/pypi/pyversions/tool-scorer.svg" alt="Python versions"/></a>
  <a href="https://github.com/yotambraun/toolscore/actions"><img src="https://github.com/yotambraun/toolscore/workflows/CI/badge.svg" alt="CI"/></a>
  <a href="https://pepy.tech/project/tool-scorer"><img src="https://static.pepy.tech/badge/tool-scorer" alt="Downloads"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License"/></a>
</p>

<p align="center">
  <a href="https://yotambraun.github.io/Toolscore/">Website</a> ·
  <a href="https://yotambraun.github.io/Toolscore/docs/">Docs</a> ·
  <a href="TUTORIAL.md">Tutorial</a> ·
  <a href="examples/">Examples</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

---

Toolscore grades MCP servers A–F and checks the tool calls your agents make. Then it goes one step further: **effect probes** check that a tool that answered "success" really changed something, and **honesty checks** compare what the tools returned with what the agent told the user. No model is called and no API key is needed, so the same run gives the same answer every time.

## Try it

```bash
uvx tool-scorer demo                                        # grade a bundled sample MCP server
uvx tool-scorer demo --truth                                # a tool that lies, and an agent that lies
uvx tool-scorer mcp test "python your_server.py" --probes   # your server: a command, a URL or a config entry
```

Real output of `toolscore demo --truth` (shortened; `…` marks the cuts):

```
1. A tool that reports success and does nothing. The sample server runs with a bug:
create_note on an existing title says it saved the note and changes nothing. …

╭────────────────────────────────────────────────────╮
│ MCP Scorecard: notes-server 1.1.0                  │
│ Grade C   Score 74%                                │
│ happy 80%  |  edge 100%  |  lint 91%  |  effect 0% │
│ MCP 2026-07-28 (stateless)                         │
╰────────────────────────────────────────────────────╯
…
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Probe      ┃ Tool        ┃ Result ┃ Confidence ┃ Detail                                  ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ bound      │ list_notes  │ pass   │ medium     │ limit bounded the result for [1, 2]     │
│ round-trip │ create_note │ FAIL   │ high       │ a second write to key 'tspefdcdf-title' │
│            │             │        │            │ reported success; state unchanged       │
│            │             │        │            │ (probe-silent-noop)                     │
└────────────┴─────────────┴────────┴────────────┴─────────────────────────────────────────┘
…
2. An agent that reports success after a tool refused. …

Honesty check  browser agent trace (bundled)  (2 tool calls)
Final answer (assistant message): 'Your order for the blue mug has been placed.'

  ERROR    call 2 evaluate ran code after call 1 click was refused ('disabled'): its code
overrides the refusal ('.disabled = false'); the final answer does not mention it
(escape-hatch-after-refusal)
…
Verdict: FLAGGED
```

The plain `toolscore demo` prints the scorecard alone (grade B, 86%) with its ranked "Top issues to fix".

## Found with Toolscore

Two bugs in the official [MCP memory server](https://github.com/modelcontextprotocol/servers/tree/main/src/memory), found with [Agent Eval Flow](https://github.com/guybass/agent-eval-flow) and Toolscore and fixed upstream. Both fixes are ports of @yotambraun's contributions ([#4886](https://github.com/modelcontextprotocol/servers/pull/4886), [#4888](https://github.com/modelcontextprotocol/servers/pull/4888)) with authorship kept, merged on 2026-10-05 by maintainer cliffhall; [#5035](https://github.com/modelcontextprotocol/servers/pull/5035) credits him "for the fix and the reproduction":

- [#5008](https://github.com/modelcontextprotocol/servers/pull/5008) *fix(memory): report entities that create_entities skipped* ([issue #4887](https://github.com/modelcontextprotocol/servers/issues/4887): `create_entities` silently dropped observations for existing entities).
- [#5035](https://github.com/modelcontextprotocol/servers/pull/5035) *fix(memory): keep unreadable lines when saving the graph* ([issue #4885](https://github.com/modelcontextprotocol/servers/issues/4885): unreadable lines were deleted by the next write).

The effect probes now catch #4887 on the published server with no configuration ([commands and output](examples/mcp_memory_probes/)):

| `@modelcontextprotocol/server-memory` | `create_entities` round trip | Grade |
| --- | --- | --- |
| `2026.8.31` (before the fix) | **FAIL** `probe-silent-noop`: "a second write to key 'tspd11f8d-name' reported success; state unchanged" | C (A by score, capped by the probe) |
| `2.0.1` | pass: "a same-key write was reported as skipped" | A |

The lint also flagged a description in [GitHub's MCP server](https://github.com/github/github-mcp-server) v1.12.2 that sends models to a tool that does not exist (`label_write`: "use the 'update_issue' tool"), and the built-in bounds probe flags `head: 0` and `tail: 0` returning the whole file on `server-filesystem@2.1.0` ([what it catches](https://yotambraun.github.io/Toolscore/docs/what_it_catches.html)). The [case study](https://github.com/guybass/agent-eval-flow/tree/main/examples/data/mcp-memory) has the protocol, the captures and the measurements.

## Who it's for

| You are | Start with | Recipe |
| --- | --- | --- |
| **MCP server author** | `toolscore mcp test "python server.py" --probes --badge mcp-grade.svg` | [Grade, probe and badge a server](https://yotambraun.github.io/Toolscore/docs/for_server_authors.html) |
| **Agent builder** | `toolscore init`, then `pytest`; or `toolscore eval contract.json trace.json` | [Tool-call tests in CI](https://yotambraun.github.io/Toolscore/docs/for_agent_builders.html) |
| **Security or platform team** | `toolscore mcp pin`, then `toolscore mcp verify-pin` in CI; `toolscore lint-config` | [Pin servers, gate unsafe calls](https://yotambraun.github.io/Toolscore/docs/for_security_teams.html) |
| **Researcher** | `toolscore agent run spec.yaml`, then `toolscore compare --runs runs.jsonl` | [Repeatable agent studies](https://yotambraun.github.io/Toolscore/docs/for_researchers.html) |

## What it checks

| Question | Command | Guide |
| --- | --- | --- |
| Is my MCP server well built? A–F grade, generated happy and edge cases, lint with stable rule IDs (tool poisoning, references to missing tools, annotations, output schemas), token cost, a README badge | `toolscore mcp test`, `mcp lint` | [MCP testing](https://yotambraun.github.io/Toolscore/docs/mcp_testing.html) |
| Did the tool really do it? Round trips, silent no-ops, lost data, ignored bounds | `toolscore mcp test --probes` | [Effect probes](https://yotambraun.github.io/Toolscore/docs/effect_probes.html) |
| Did the agent tell the truth? Success claimed after a failure, hidden warnings, code that overrides a refusal | `toolscore honesty trace.json` | [Honesty checks](https://yotambraun.github.io/Toolscore/docs/honesty_checks.html) |
| What does the agent do when a tool fails? | `toolscore mcp proxy --inject faults.json` | [Fault injection](https://yotambraun.github.io/Toolscore/docs/fault_injection.html) |
| Does the agent call the right tools, with the right arguments? Required, optional, forbidden and alternative calls; pytest snapshots | `toolscore eval`, `expect()`, `toolscore_snapshot` | [Contracts](https://yotambraun.github.io/Toolscore/docs/contracts.html), [snapshots](https://yotambraun.github.io/Toolscore/docs/snapshot_testing.html) |
| Destructive commands or credentials in tool arguments? | `toolscore eval --forbidden rules.json --fail-on-violations` | [Behavior and safety](https://yotambraun.github.io/Toolscore/docs/behavior_safety.html) |
| Do my `CLAUDE.md`, `AGENTS.md` and skills name tools that exist? Unknown tools, deleting with a read-only tool | `toolscore lint-config` | [Config lint](https://yotambraun.github.io/Toolscore/docs/config_lint.html) |
| What did my coding agent do yesterday? Claude Code and Codex CLI sessions, read-only, credentials redacted | `toolscore sessions list`, `toolscore honesty SESSION.jsonl` | [Coding sessions](https://yotambraun.github.io/Toolscore/docs/coding_sessions.html) |
| Did a server change under me? MCP rug pulls, new delete or exec capabilities | `toolscore mcp pin`, `mcp verify-pin`, `mcp diff` | [Pinning and diffs](https://yotambraun.github.io/Toolscore/docs/pinning_diff.html) |
| Is variant B really better? Wilson intervals, Fisher's exact test, pass^k, budgets, receipts | `toolscore agent run`, `compare --runs`, `select`, `regrade` | [Agent harness](https://yotambraun.github.io/Toolscore/docs/agent_harness.html), [comparing runs](https://yotambraun.github.io/Toolscore/docs/comparing_runs.html) |

Every check reports pass, fail or **unknown**: a trace without a final answer or without tool results is never counted as honest, and missing latency or cost is never 0.

## Works with

OpenAI (Chat Completions and Responses API) · Anthropic · Gemini · LangGraph · Pydantic AI · OpenAI Agents SDK (run results and live tracing) · Claude Agent SDK (messages and live hooks) · CrewAI · browser-use · Inspect AI (scorer) · Claude Code and Codex CLI sessions · OpenTelemetry GenAI spans · MCP sessions recorded with `toolscore mcp record` · MCP servers over stdio or Streamable HTTP, and Claude Desktop, Cursor, VS Code and Claude Code configs · pytest · GitHub Actions · Claude Code (plugin)

Pass a raw response or run result straight to `evaluate()`; the format is detected ([frameworks guide](https://yotambraun.github.io/Toolscore/docs/frameworks.html)):

```python
from toolscore import evaluate

response = client.responses.create(model="gpt-6-luna", input=[...], tools=[...])
result = evaluate(expected=[{"tool": "get_weather", "args": {"city": "NYC"}}], actual=response)
print(result.score, result.false_success)
```

Or assert in any test framework, or let the bundled pytest fixture record the calls once and replay them on every run (`toolscore init` scaffolds it for your framework):

```python
from toolscore import Regex, expect

expect(agent).on("book me a flight to NYC") \
    .calls("search_flights", destination="NYC") \
    .then_calls("book_flight", flight_id=Regex(r"FL-\d+")) \
    .does_not_call("cancel_booking") \
    .run()
```

## Install

```bash
pip install tool-scorer            # Python 3.10 to 3.14; the CLI is `toolscore`
pip install "tool-scorer[http]"    # remote MCP servers over Streamable HTTP
```

Optional extras: `[yaml]` for YAML configs, and `[llm]`, `[anthropic]`, `[gemini]` for the opt-in [LLM judge](https://yotambraun.github.io/Toolscore/docs/llm_judge.html), the only part that calls a model. Toolscore speaks MCP 2026-07-28 and falls back to the `initialize` handshake of earlier revisions, so it works with servers built on any SDK release.

## In CI

```yaml
- uses: yotambraun/toolscore@v1
  with:
    mcp-command: 'python my_server.py'     # or a URL; mcp-auth-env for a token
    mcp-fail-under: 'B'
    mcp-probes: 'true'
    mcp-pin-file: 'toolscore.lock.json'    # fail on drift from `toolscore mcp pin`
```

The action also gates agent traces (`gold-file`, `trace-file`, `threshold`, `fail-on-violations`, `fail-on-honesty`) and writes the scorecard to the job summary ([CI guide](https://yotambraun.github.io/Toolscore/docs/ci.html)).

In Claude Code, the plugin adds skills that run these steps with you (audit an MCP server, add tool-call tests, check agent honesty, pin servers):

```
/plugin marketplace add yotambraun/toolscore
/plugin install toolscore@toolscore
```

## Toolscore and Agent Eval Flow

Toolscore is tool-level truth: did each call happen, succeed, do what it reported, and get reported honestly. [Agent Eval Flow](https://github.com/guybass/agent-eval-flow) is study-level evaluation (design, pre-registration, grading, reports) and builds on Toolscore: `pip install "agent-eval-flow[toolscore]"`. `toolscore export --format aef` writes Toolscore's runs as neutral, versioned records for such frameworks. For production tracing and broad quality metrics, see the [comparison](https://yotambraun.github.io/Toolscore/docs/comparison.html).

## Learn more

- [Documentation](https://yotambraun.github.io/Toolscore/docs/): guides and the API reference
- [TUTORIAL.md](TUTORIAL.md): step by step, from a first score to CI
- [What Toolscore catches](https://yotambraun.github.io/Toolscore/docs/what_it_catches.html): real agents and real servers, with the output
- [examples/](examples/): runnable, offline examples with their real output
- [CHANGELOG.md](CHANGELOG.md): what is new in 1.11, with upgrade notes
- [CONTRIBUTING.md](CONTRIBUTING.md): development setup (`pip install -e ".[dev]"`, `pytest`, `ruff`, `mypy`)
- [The story behind Toolscore](https://medium.com/@yotambraun/stop-shipping-broken-llm-agents-toolscore-for-reliable-tool-using-ai-now-with-ci-cd-462913cf99e2) (Medium)

## License and citation

Apache License 2.0, see [LICENSE](LICENSE).

```bibtex
@software{toolscore,
  title = {Toolscore: MCP Server and Agent Tool-Call Testing},
  author = {Yotam Braun},
  year = {2026},
  url = {https://github.com/yotambraun/toolscore}
}
```
