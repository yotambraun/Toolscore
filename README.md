<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <img src="assets/logo.svg" alt="Toolscore Logo" width="360"/>
  </picture>
</p>

<h1 align="center">Toolscore</h1>

<p align="center">
  <em>Test MCP servers and the tool calls your agents make. Local, deterministic, no API key.</em>
</p>

[![Website](https://img.shields.io/badge/website-toolscore-2ea44f.svg)](https://yotambraun.github.io/Toolscore/)
[![PyPI version](https://badge.fury.io/py/tool-scorer.svg)](https://badge.fury.io/py/tool-scorer)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Downloads](https://static.pepy.tech/badge/tool-scorer)](https://pepy.tech/project/tool-scorer)
[![Python Versions](https://img.shields.io/pypi/pyversions/tool-scorer.svg)](https://pypi.org/project/tool-scorer/)
[![CI](https://github.com/yotambraun/toolscore/workflows/CI/badge.svg)](https://github.com/yotambraun/toolscore/actions)

**[Website](https://yotambraun.github.io/Toolscore/)** ·
**[Test your MCP server](https://yotambraun.github.io/Toolscore/mcp)** ·
**[Test your agent](https://yotambraun.github.io/Toolscore/agents)** ·
**[Compare](https://yotambraun.github.io/Toolscore/compare)** ·
**[Quickstart](https://yotambraun.github.io/Toolscore/quickstart)** ·
**[Docs](https://yotambraun.github.io/Toolscore/docs/)**

---

**Toolscore grades any MCP server A–F and checks the tool calls your agent makes against the ones you expect, so a broken tool or a drifting agent fails CI instead of production.** It runs offline, gives the same answer every time, and costs nothing per run.

```bash
uvx tool-scorer demo                                     # grade a bundled sample server, no setup
uvx tool-scorer mcp test "python your_server.py"         # your stdio server
uvx tool-scorer mcp test https://example.com/mcp --auth-env MCP_TOKEN   # or a remote one
```

Real output of `toolscore demo`:

```
╭──────────────────────────────────────╮
│ MCP Scorecard: notes-server 1.1.0    │
│ Grade B   Score 86%                  │
│ happy 80%  |  edge 100%  |  lint 91% │
│ MCP 2026-07-28 (stateless)           │
╰──────────────────────────────────────╯
                         Tools
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Tool         ┃ Scenarios ┃ Avg latency ┃ Def. tokens ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ create_note  │       6/6 │      0.6 ms │          80 │
│ list_notes   │       6/6 │      0.5 ms │          59 │
│ search_notes │       6/6 │      0.5 ms │          48 │
│ delete_note  │       6/6 │      0.5 ms │          52 │
│ export_notes │       3/6 │      0.5 ms │          64 │
└──────────────┴───────────┴─────────────┴─────────────┘
Tool definitions cost ~303 estimated tokens of context across 5 tool(s).

Top issues to fix
  1. export_notes  fails on valid input (export failed: storage backend not configured)
     -> The tool errors on well-formed arguments - check the handler and that the input schema matches what the tool actually accepts.
  2. delete_note  property 'note_id' is missing a 'type'
     -> Give the property a JSON-schema type (and an enum where the values are fixed) so the model does not have to guess.
  3. create_note  changes state but declares no readOnlyHint/destructiveHint annotations
     -> Declare annotations {"readOnlyHint": false, "destructiveHint": false} (or true if it can overwrite or delete), so clients know what it changes.
  4. search_notes  description is very short (< 10 chars)
     -> Describe what the tool does and when to use it - models choose tools by their description.
```

Install with `pip install tool-scorer` (add `[http]` for remote servers). It speaks MCP 2026-07-28 and falls back to the `initialize` handshake of earlier revisions, so it works with servers built on any SDK release.

| Plug in | How |
|---------|-----|
| MCP servers (stdio, Streamable HTTP, Claude Desktop / Cursor / VS Code / Claude Code configs) | `toolscore mcp test`, `mcp lint`, `mcp list`, `mcp record` |
| OpenAI (Chat Completions and Responses API), Anthropic, Gemini | pass the raw response to `evaluate()` |
| LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, CrewAI | pass the run result to `evaluate()` |
| OpenTelemetry GenAI spans, recorded MCP sessions | `toolscore eval gold.json trace.json` |
| pytest, GitHub Actions | snapshot fixture, `uses: yotambraun/toolscore@v1` |

## Found with Toolscore

Two bugs in the official [MCP memory server](https://github.com/modelcontextprotocol/servers/tree/main/src/memory), found with [Agent Eval Flow](https://github.com/guybass/agent-eval-flow) and Toolscore and fixed upstream. Both fixes are ports of @yotambraun's contributions ([#4886](https://github.com/modelcontextprotocol/servers/pull/4886), [#4888](https://github.com/modelcontextprotocol/servers/pull/4888)) with authorship kept, merged on 2026-10-05 by maintainer cliffhall; [#5035](https://github.com/modelcontextprotocol/servers/pull/5035) credits him "for the fix and the reproduction":

- [#5035](https://github.com/modelcontextprotocol/servers/pull/5035) *fix(memory): keep unreadable lines when saving the graph* ([issue #4885](https://github.com/modelcontextprotocol/servers/issues/4885): unreadable lines were deleted by the next write).
- [#5008](https://github.com/modelcontextprotocol/servers/pull/5008) *fix(memory): report entities that create_entities skipped* ([issue #4887](https://github.com/modelcontextprotocol/servers/issues/4887): `create_entities` silently dropped observations for existing entities).

The [case study](https://github.com/guybass/agent-eval-flow/tree/main/examples/data/mcp-memory) has the protocol, the captures and the measurements.

## Releases

| Version | Date | Highlights |
|---------|------|------------|
| **1.11.0** | Unreleased | MCP 2026-07-28 with fallback to the handshake · remote servers over Streamable HTTP · lint for behavior annotations and output schemas · grade badges · OpenAI Responses API · current models and prices |
| 1.10.0 | 2026-10-03 | Record real MCP sessions · behavior and safety checks · MCP lint for missing tools and tool poisoning · OpenTelemetry import |
| 1.9.1 | 2026-10-01 | MCP scorecard fixes found on the official MCP reference servers |

Full notes, including upgrade advice, in the [CHANGELOG](CHANGELOG.md).

## Test your agent's tool-calling

```python
from toolscore import expect, ANY, Regex

expect(agent).on("book me a flight to NYC") \
    .calls("search_flights", origin=ANY, destination="NYC") \
    .then_calls("book_flight", flight_id=Regex(r"FL-\d+")) \
    .does_not_call("cancel_booking") \
    .with_score(0.9) \
    .run()
```

## 60-Second Quickstart

```bash
pip install tool-scorer
toolscore init          # detects your framework, scaffolds a passing pytest suite
pytest                  # first run RECORDS your agent's tool calls as snapshots
toolscore approve --all # review, then approve them as the baseline
pytest                  # every run after this REPLAYS — and fails on drift
```

That's the whole loop. No hand-written expected-call files, no YAML. Your agent's own behavior becomes the regression test.

## See What It Catches

Four short scenarios, each with the output Toolscore printed. The first two come from a real agent and a real published MCP server; the last two use the sample traces in [`examples/`](examples/), so you can run them yourself.

### 1. Catch an agent that gives up after an error

A small agent (`gpt-4.1-mini`) was asked to read `/srv/acme-api/config/settings.json` through the official [filesystem MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem), which only allows its project folder. It tried that path once, got *Access denied*, and told the user it could not help. It never called `list_allowed_directories`, which would have shown it where the file was.

Record what your agent really does by putting `toolscore mcp record` where your MCP client starts the server. It relays every message unchanged and saves each tool call with its result, error and duration:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "toolscore",
      "args": ["mcp", "record", "-o", "session.json", "--",
               "npx", "-y", "@modelcontextprotocol/server-filesystem", "./acme-api"]
    }
  }
}
```

Then score the session against what the task needed (`[{"tool": "list_allowed_directories"}, {"tool": "read_text_file"}]`):

```
$ toolscore eval gold.json session.json

│ Overall Score      │  90.0% │
│ Selection Accuracy │ 100.0% │
│ Argument F1        │ 100.0% │
│ Sequence Accuracy  │  50.0% │

╭────────────────────────╮
│ Grade B   WARN (90.0%) │
╰────────────────────────╯

Required calls completed: 0 of 2 (missing or failed; not part of the default score)

Top issues to fix
  1. list_allowed_directories  expected call to `list_allowed_directories` never happened

Behavior and safety
  WARNING  1 of 1 tool calls failed (read_text_file)
```

The score judges the calls the agent *made*, and its one call used the right tool, so it reads 90%. The lines under the grade show what actually happened: neither required call succeeded. To make that count in the score, weight it: `--weight required_call_recall=0.3` turns this run into **Grade D, FAIL (69.2%)**.

### 2. Find tool descriptions that point to tools that don't exist

```
$ toolscore mcp lint "github-mcp-server stdio --toolsets all"     # v1.12.2

│ warning  │ label_write  │ refers to tool 'update_issue', which this server does not expose │
```

This is GitHub's official MCP server. In v1.12.2, `label_write` told models *"To set labels on issues, use the 'update_issue' tool"*, and no such tool exists, so a model that follows the description calls a tool that is not there. The lint reads tool descriptions, parameter descriptions and the server's own instructions; across this server's 254 tool definitions it reported its two stale references and nothing else. It also flags tool poisoning: hidden Unicode, text that tells the model to hide something from the user, and `<IMPORTANT>`-style instruction blocks.

### 3. Block destructive commands and leaked keys in CI

A deploy agent's trace ([`examples/guardrails`](examples/guardrails/)), checked against a two-rule policy file:

```
$ toolscore eval gold.json trace.json --forbidden forbidden.json --fail-on-violations

Required calls completed: 1 of 2 (missing or failed; not part of the default score)

Behavior and safety
  ERROR    call 2 run_shell matches forbidden rule 1: destructive shell command
  ERROR    call 3 http_post passes a credential (aws_access_key_id) in 'body.text': AKIA…LE
  WARNING  2 of 5 tool calls failed (deploy x2)
  WARNING  1 call repeats a failed call with the same arguments

ERROR 2 forbidden call(s) or credential(s) found (--fail-on-violations)     # exit code 1
```

```json
[
  {"tool": "run_shell", "args": {"command": {"$regex": "rm -rf"}}, "reason": "destructive shell command"},
  {"tool": "read_file", "args": {"path": {"$contains": ".ssh"}}, "reason": "private keys"}
]
```

Credentials are shown only as a redacted preview, in the findings and anywhere else the console, Markdown or HTML reports would print them. The detector looks for distinctive formats (OpenAI, Anthropic, GitHub, AWS, Google, Slack, Stripe, PEM private keys), so ordinary ids and hashes are not flagged.

### 4. Score the OpenTelemetry traces you already collect

Frameworks and observability platforms that follow the OpenTelemetry GenAI conventions already record every tool call as a span. Toolscore reads them directly, from an OTLP JSON export or from SDK span objects:

```python
import json
from toolscore import evaluate, from_otel

spans = json.load(open("examples/otel_genai_spans.json"))  # written by the OpenTelemetry SDK
for call in from_otel(spans):
    print(call["tool"], call["args"], "FAILED: " + call["error"] if call["is_error"] else "ok")

result = evaluate(expected=[{"tool": "search_orders"}, {"tool": "issue_refund"},
                            {"tool": "send_email"}], actual=spans)
print(result.required_call_recall)
```

```
search_orders {'customer': 'ada@example.com', 'status': 'open'} ok
issue_refund {'order_id': 'A-17', 'amount': 42.5} FAILED: Refund window has closed
send_email {'to': 'ada@example.com', 'subject': 'Your refund'} ok
0.6666666666666666
```

The agent called every tool the task needed, in order, yet the refund failed and it emailed the customer about "Your refund" anyway. A tool-name check passes this run; `required_call_recall` and the failed-call finding do not.

## Snapshot Testing — Jest for Agents

Stop hand-writing expected tool calls. Record them once, approve them, replay them forever.

```python
def test_books_a_flight(toolscore_snapshot):
    toolscore_snapshot(my_agent("book a flight to NYC"))
    # First run: records a pending snapshot and warns.
    # After `toolscore approve`: replays against the baseline, fails on drift.
```

The fixture ships with the package — no plugin install, no registration. Snapshots are plain JSON files under `.toolscore/snapshots/`, named after the pytest node id, so they review cleanly in PRs.

The workflow:

1. **Record** — the first `pytest` run captures your agent's tool calls into *unapproved* snapshots (a terminal summary tells you: `toolscore: 1 snapshot created (pending approval)`).
2. **Approve** — review with `toolscore snapshots show <name>`, then `toolscore approve --all` (or approve by name).
3. **Replay** — every subsequent run evaluates the agent against the approved baseline. Drift fails the test with a full expected-vs-actual diff.

Intentional behavior change? Re-record:

```bash
pytest --toolscore-update     # overwrite + re-approve baselines
```

CI is strict by design: snapshots are never created or auto-approved in CI — a missing or pending snapshot fails the build (downgrade to a warning with `--toolscore-allow-pending` for staged rollouts). You can also record outside pytest with `toolscore record -- <any command>` or from an existing trace file with `toolscore record --from-trace trace.json --name my_snap`.

## MCP Scorecard — Grade Any MCP Server

Point it at any MCP server: it generates happy-path *and* adversarial edge-case scenarios from each tool's schema, runs them, checks results against declared output schemas, lints the definitions, measures each tool's token cost, and returns an A–F grade plus a ranked **"Top issues to fix"** list (the output is at the [top of this page](#toolscore)).

```bash
toolscore mcp test "python my_server.py"                     # a local stdio server
toolscore mcp test https://example.com/mcp --auth-env TOKEN  # a remote server (pip install "tool-scorer[http]")

# or straight from your MCP client's config: Claude Desktop, Cursor and Claude Code
# (mcpServers) or VS Code (servers), with stdio or url entries:
uvx tool-scorer mcp test --config claude_desktop_config.json --server my-server
```

For remote servers, `--auth-env VAR` sends `Authorization: Bearer $VAR`, and `--header 'Name: ${VAR}'` sends any header; in config files, `${VAR}` and `${env:VAR}` in `url` and `headers` are read from the environment. Values are never printed. `--protocol auto|modern|legacy` chooses the protocol era (`auto` probes with `server/discover` and falls back to `initialize`).

Export a Markdown report — for a CI artifact or your server's own README — with `--report md --output SCORECARD.md`:

```markdown
# MCP Scorecard: notes-server 1.1.0

**Grade: B** &middot; Score 86%

- Happy-path pass rate: 80%
- Edge-case resilience: 100%
- Lint score: 91% (1 errors, 2 warnings)
- Tool-definition tokens (estimated): ~303 across 5 tool(s)
- Protocol: MCP 2026-07-28 (stateless)

## Tools

| Tool | Scenarios | Avg latency | Def. tokens |
| --- | --- | --- | --- |
| `create_note` | 6/6 | 0.6 ms | 80 |
| `list_notes` | 6/6 | 0.6 ms | 59 |
| `search_notes` | 6/6 | 0.5 ms | 48 |
| `delete_note` | 6/6 | 0.5 ms | 52 |
| `export_notes` | 3/6 | 0.6 ms | 64 |

## Top issues to fix

- **`export_notes`** — fails on valid input (export failed: storage backend not configured). _Fix:_ The tool errors on well-formed arguments - check the handler and that the input schema matches what the tool actually accepts.
- **`delete_note`** — property 'note_id' is missing a 'type'. _Fix:_ Give the property a JSON-schema type (and an enum where the values are fixed) so the model does not have to guess.
- **`create_note`** — changes state but declares no readOnlyHint/destructiveHint annotations. _Fix:_ Declare annotations {"readOnlyHint": false, "destructiveHint": false} (or true if it can overwrite or delete), so clients know what it changes.
- **`search_notes`** — description is very short (< 10 chars). _Fix:_ Describe what the tool does and when to use it - models choose tools by their description.
```

Gate CI with `--fail-under B` (exit 1 below the bar), or add `--ci` to write the verdict to your GitHub Actions job summary and fail on blocking issues. `toolscore mcp list` and `toolscore mcp lint` are also available standalone.

### Show the grade in your README

`--badge PATH` writes an SVG badge and `--badge-json PATH` a [shields.io endpoint](https://shields.io/badges/endpoint-badge) file, both from that run's grade; there is no option to set a grade by hand. The sample server's badge, from the run above: ![MCP grade](assets/sample-mcp-grade.svg)

```bash
toolscore mcp test "python my_server.py" --badge .github/badges/mcp-grade.svg
```

```markdown
[![MCP grade](.github/badges/mcp-grade.svg)](https://github.com/yotambraun/toolscore)
```

To keep it current, let CI regenerate and commit it ([full workflow](examples/github_actions/mcp-badge.yml)):

```yaml
- uses: yotambraun/toolscore@v1
  with:
    mcp-command: 'python my_server.py'
    mcp-fail-under: 'F'          # update the badge whatever the grade
    mcp-badge: .github/badges/mcp-grade.svg
- run: |
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add .github/badges/mcp-grade.svg
    git diff --cached --quiet || { git commit -m "chore: update MCP grade badge"; git push; }
```

### What the lint checks

Every issue has a rule ID (listed in the [MCP testing guide](https://yotambraun.github.io/Toolscore/docs/mcp_testing.html#lint-rules)). Beyond schema hygiene:

- **Behavior annotations**: a tool whose name says it writes or deletes but declares no `readOnlyHint`/`destructiveHint` (clients then treat it as possibly destructive), `readOnlyHint: true` on a `delete_*` tool (clients may run it without asking), and conflicting or non-boolean hints. Tools named with a read verb (`get_`, `list_`, `search_`...) are never judged by name. Warnings.
- **Output schemas**: when a tool declares an `outputSchema`, its successful results must carry conforming `structuredContent`. Keywords the checker does not know are not judged, so a mismatch it reports is real. Warnings.
- **References to tools the server does not expose**, in tool descriptions, parameter descriptions and the server's `instructions` (with a "did you mean" suggestion).
- **Tool poisoning**: hidden Unicode (tag characters and bidi controls), "ignore previous instructions", and text telling the model to hide something from the user are errors; `<IMPORTANT>`-style instruction blocks, which some servers also use for emphasis, are warnings.
- **Context cost**: the scorecard counts the tokens of the server's instructions alongside the tool definitions.

To score what an agent actually did against your server, record a session with `toolscore mcp record` (see [example 1](#1-catch-an-agent-that-gives-up-after-an-error)) and run `toolscore eval gold.json session.json`.

## Fluent Assertions and a Plain Score

Prefer a score over a chain? The core API is three lines:

```python
from toolscore import evaluate

result = evaluate(
    expected=[
        {"tool": "get_weather", "args": {"city": "NYC"}},
        {"tool": "send_email", "args": {"to": "user@example.com"}},
    ],
    actual=[
        {"tool": "get_weather", "args": {"city": "New York"}},
        {"tool": "send_email", "args": {"to": "user@example.com"}},
    ],
)

print(result.score)              # 0.85 — weighted composite
print(result.selection_accuracy) # 1.0  — right tools picked
print(result.argument_f1)        # 0.5  — argument match quality
```

One-liner for any test framework — `assert_tools(expected, actual, min_score=0.9)`. End-to-end in one call:

```python
from toolscore import test_agent

test_agent(
    agent=my_agent,                 # any callable: prompt in, response out
    input="What's the weather in NYC?",
    expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
    min_score=0.9,
)
```

Async agents are first-class: `await test_agent_async(...)`, or `await expect(my_async_agent).on(prompt).calls(...).run_async()`.

Omit `args` in an expected call (or use `.calls("tool")` with no kwargs) to assert the tool was called *without* checking its arguments. An explicit `"args": {}` means "expect zero arguments".

## Behavior and Safety Checks

The score answers *"did the agent make the expected calls?"*. Every evaluation also answers the questions the score does not:

| Question | Where to read it |
|----------|------------------|
| Did calls fail? Did the agent retry a failure unchanged? | `metrics["efficiency_metrics"]`: `error_count`, `error_rate`, `retry_after_error_count` |
| Was every required call made, and did it succeed? | `result.required_call_recall` (opt-in score weight `required_call_recall`) |
| Did the agent pass a credential into a tool? | `metrics["security_metrics"]` |
| Did it make a call it must never make? | `result.policy_violations` (with `forbidden=`) |

```python
import json
from toolscore import Contains, evaluate, expect

trace = json.load(open("examples/guardrails/trace.json"))   # your agent's tool calls

result = evaluate(
    expected=[{"tool": "run_shell", "args": {"command": "make test"}}],
    actual=trace,
    forbidden=[
        {"tool": "run_shell", "args": {"command": Contains("rm -rf")}, "reason": "destructive"},
        {"tool": "read_file", "args": {"path": Contains(".ssh")}},
    ],
    weights={"required_call_recall": 0.3},   # opt in: skipped or failed required calls lower the score
)
result.policy_violations   # [{"index": 1, "tool": "run_shell", "rule": 0, "reason": "destructive", ...}]

# The same rule in a fluent test:
expect(trace).does_not_call("run_shell", command=Contains("rm -rf")).run()
```

The console, Markdown and HTML reports list these findings under **Behavior and safety**. For harnesses that store evidence, `result.to_dict()` returns a complete, JSON-safe, versioned record: score, grade, weights, every metric, and every expected and actual call with its result, error and duration.

## Native Everywhere — Zero Glue

Pass raw responses straight into `evaluate()`, `expect()`, `test_agent()`, or the snapshot fixture. Toolscore auto-detects the format — no manual extraction:

| Source | Auto-detected | Explicit helper |
|--------|:---:|---------------|
| OpenAI (Chat Completions, legacy `function_call`) | Yes | `from_openai` |
| OpenAI Responses API (`function_call`, `mcp_call` items; outputs paired by `call_id`) | Yes | `from_openai_responses` |
| Anthropic (`tool_use` blocks) | Yes | `from_anthropic` |
| Google Gemini (`functionCall` parts) | Yes | `from_gemini` |
| LangGraph (state / message lists) | Yes | `from_langgraph` |
| Pydantic AI (run results) | Yes | `from_pydantic_ai` |
| OpenAI Agents SDK (run results) | Yes | `from_openai_agents` |
| Claude Agent SDK (message lists) | Yes | `from_claude_agent_sdk` |
| CrewAI (experimental) | Yes | `from_crewai` |
| MCP sessions from `toolscore mcp record`, JSON-RPC 2.0 traces | Yes | file-based `format="mcp"` |
| OpenTelemetry GenAI spans (OTLP JSON export or SDK spans) | Yes | `from_otel`, file-based `format="otel"` |
| LangChain / custom trace files | Yes | file-based `format="auto"` |

```python
response = client.responses.create(model="gpt-6-luna", input=[...], tools=[...])
result = evaluate(expected=[...], actual=response)   # just works
```

## Matchers — Flexible Where It Matters

Exact equality is the default; matchers loosen exactly the arguments you choose:

| Matcher | Matches | Example |
|---------|---------|---------|
| `ANY` | anything | `calls("search", q=ANY)` |
| `Regex(pattern)` | full string match | `Regex(r"FL-\d+")` |
| `Approx(value, rel, abs)` | numbers within tolerance | `Approx(40.71, rel=1e-2)` |
| `Contains(item)` | membership in str/list/dict | `Contains("metric")` |
| `OneOf(*values)` | any of the candidates | `OneOf("NYC", "New York")` |
| `IsType(*types)` | isinstance check (bool-safe) | `IsType(int)` |

```python
from toolscore import evaluate, Approx, Contains, IsType, OneOf

evaluate(
    expected=[{"tool": "get_weather", "args": {
        "city": OneOf("NYC", "New York"),
        "units": Contains("metric"),
        "lat": Approx(40.71, rel=1e-2),
        "days": IsType(int),
    }}],
    actual=[{"tool": "get_weather", "args": {
        "city": "NYC", "units": ["metric", "extended"], "lat": 40.7128, "days": 5,
    }}],
)
```

Matchers work everywhere expected args do: `evaluate`, `assert_tools`, `expect().calls(...)`, gold files.

## Failures You Can Actually Read

When a threshold is missed, Toolscore renders an aligned expected-vs-actual table with per-argument mismatches and targeted tips — in the exception message itself, so it lands directly in your pytest output:

```
                                   Expected vs Actual Tool Calls
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃   # ┃ Expected                     ┃ Actual                       ┃ Status                       ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│   1 │ search_flights(origin='SFO', │ search_flights(origin='SFO', │ destination: 'NYC' ≠ 'BOS'   │
│     │ destination='NYC')           │ destination='BOS')           │                              │
├─────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────┤
│   2 │ book_flight(flight_id='FL-1… │ cancel_booking(booking_id='… │ tool: 'book_flight' ≠        │
│     │                              │                              │ 'cancel_booking'             │
└─────┴──────────────────────────────┴──────────────────────────────┴──────────────────────────────┘
score 0.47 < 0.90 required  ·  selection 0.50  ·  args 0.40  ·  sequence 0.50

Tips:
  • Use --llm-judge flag to catch semantic equivalence
  • Check that your agent has access to all required tools
  • Verify tool names match exactly (case-sensitive)
```

(That is real output from a deliberately failing `assert_tools` — color in a TTY, plain text in CI logs.)

The composite `result.score` weighs selection accuracy (40%), argument F1 (30%), sequence accuracy (20%), and redundancy (10%); pass `weights={...}` (or `--weight NAME=VALUE` on the CLI) to re-balance (weights are renormalized to sum to 1.0). Selection accuracy judges the calls that were made, so add a `required_call_recall` weight when skipped or failed required calls should lower the score.

## Optional: LLM Judge for Every Provider

When `search_web` vs `web_search` is a semantic question, opt into an LLM judge — via OpenAI, Anthropic, Gemini, or any OpenAI-compatible endpoint (Ollama, vLLM, Groq):

```bash
toolscore eval gold.json trace.json --llm-judge                                  # OpenAI gpt-6-luna
toolscore eval gold.json trace.json --llm-judge --llm-model claude-haiku-5-5
toolscore eval gold.json trace.json --llm-judge --llm-model llama3.1 \
    --llm-base-url http://localhost:11434/v1                                     # local Ollama
```

```python
from toolscore import evaluate_trace, JudgeConfig

result = evaluate_trace("gold.json", "trace.json",
                        judge=JudgeConfig(model="gemini-3.5-flash-lite"))
```

The provider is inferred from the model name. No `temperature` is sent unless you set one: current Claude models and OpenAI's GPT-6 models at their default reasoning effort reject it. Install extras as needed: `tool-scorer[llm]` (OpenAI/compatible), `[anthropic]`, `[gemini]`. Everything else in Toolscore stays deterministic and offline.

## CI/CD

`toolscore init` writes a GitHub Actions workflow that replays your approved snapshots on every push. Or use the official action directly:

```yaml
# Gold-standard evaluation with a threshold
- uses: yotambraun/toolscore@v1
  with:
    gold-file: tests/gold_standard.json
    trace-file: tests/agent_trace.json
    threshold: '0.90'

# Safety gate — fail on forbidden calls or credentials in tool arguments
- uses: yotambraun/toolscore@v1
  with:
    gold-file: tests/gold_standard.json
    trace-file: tests/agent_trace.json
    forbidden-file: tests/forbidden.json
    fail-on-violations: 'true'

# MCP scorecard mode — grade your MCP server on every PR
- uses: yotambraun/toolscore@v1
  with:
    mcp-command: 'uvx my-mcp-server'      # or a URL; add mcp-auth-env for a token
    mcp-fail-under: 'B'
```

The action installs the Toolscore version that matches the action ref (`@v1` follows the latest 1.x release; pin `@v1.11.0` for a fixed version). It outputs `score`, `grade`, `required-call-recall` and `violations`, and in MCP mode `mcp-grade` and `mcp-score`, for later steps.

Baseline regression checks catch slow degradation:

```bash
toolscore eval gold.json trace.json --save-baseline baseline.json   # once
toolscore regression baseline.json new_trace.json --gold-file gold.json
# exit codes: 0 = PASS, 1 = regression detected, 2 = error
```

## Evaluate Whole Agent Runs

Toolscore checks tool calls and MCP servers. To evaluate complete agent runs (tasks, outcomes, evidence), [Agent Eval Flow](https://github.com/guybass/agent-eval-flow) builds on it: `pip install "agent-eval-flow[toolscore]"`, then `result.report(path, tools=True)` adds the Toolscore view of every tool call to its report.

## When to Use Toolscore vs. the Platforms

Toolscore is the deterministic, in-CI health-check for tool-calling: it runs in your test suite, for free, and fails the build on drift. Observability and eval platforms watch your agent in production. Use both.

| You want to... | Use |
|----------------|-----|
| Fail the CI build when tool calls drift, deterministically, $0 per run | **Toolscore** |
| Grade and lint an MCP server, including missing-tool references and tool poisoning | **Toolscore** (`toolscore mcp test`, `toolscore mcp lint`) |
| Check real agent sessions (MCP recordings, OpenTelemetry spans) for failed calls, leaked credentials and forbidden calls | **Toolscore** |
| Score production traces across many quality dimensions (hallucination, toxicity, RAG) | [DeepEval](https://github.com/confident-ai/deepeval), [MLflow](https://mlflow.org/) |
| Trace, monitor, and debug agents in production | [LangSmith](https://smith.langchain.com/), [Arize Phoenix](https://phoenix.arize.com/) |
| Evaluate RAG retrieval/faithfulness | [Ragas](https://github.com/explodinggradients/ragas) |
| Safety-focused evaluation harnesses | [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) |

Toolscore does one thing well: it verifies your agent calls the right tools, with the right arguments, in the right order — before you ship.

## Learn More

- [Documentation](https://yotambraun.github.io/Toolscore/docs/) — full API reference and guides
- [TUTORIAL.md](TUTORIAL.md) — step-by-step walkthrough, from first score to CI
- [CHANGELOG.md](CHANGELOG.md) — what's new
- [Medium article](https://medium.com/@yotambraun/stop-shipping-broken-llm-agents-toolscore-for-reliable-tool-using-ai-now-with-ci-cd-462913cf99e2) — the story behind Toolscore

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check toolscore tests examples
mypy toolscore
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Citation

```bibtex
@software{toolscore,
  title = {Toolscore: MCP Server and Agent Tool-Call Testing},
  author = {Yotam Braun},
  year = {2026},
  url = {https://github.com/yotambraun/toolscore}
}
```
