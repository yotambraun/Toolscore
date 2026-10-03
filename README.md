<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <img src="assets/logo.svg" alt="Toolscore Logo" width="360"/>
  </picture>
</p>

<h1 align="center">Toolscore</h1>

<p align="center">
  <em>The instant, free, deterministic health-check for LLM tool-calling</em>
</p>

[![Website](https://img.shields.io/badge/website-toolscore-2ea44f.svg)](https://yotambraun.github.io/Toolscore/)
[![PyPI version](https://badge.fury.io/py/tool-scorer.svg)](https://badge.fury.io/py/tool-scorer)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Downloads](https://static.pepy.tech/badge/tool-scorer)](https://pepy.tech/project/tool-scorer)
[![Python Versions](https://img.shields.io/pypi/pyversions/tool-scorer.svg)](https://pypi.org/project/tool-scorer/)
[![CI](https://github.com/yotambraun/toolscore/workflows/CI/badge.svg)](https://github.com/yotambraun/toolscore/actions)
[![GitHub stars](https://img.shields.io/github/stars/yotambraun/toolscore?style=social)](https://github.com/yotambraun/toolscore)

### [**Visit the website → yotambraun.github.io/Toolscore**](https://yotambraun.github.io/Toolscore/)

**[Website](https://yotambraun.github.io/Toolscore/)** ·
**[Test your MCP server](https://yotambraun.github.io/Toolscore/mcp)** ·
**[Test your agent](https://yotambraun.github.io/Toolscore/agents)** ·
**[Compare](https://yotambraun.github.io/Toolscore/compare)** ·
**[Quickstart](https://yotambraun.github.io/Toolscore/quickstart)** ·
**[Docs](https://yotambraun.github.io/Toolscore/docs/)**

---

**Toolscore is the instant, free, deterministic health-check for LLM tool-calling.** Point it at an MCP server or an agent and get a clear *"here's your grade and exactly what's broken"* verdict — deterministically, offline, with zero API cost. No LLM judge, no cloud, no per-test bill.

It's two sides of the same handshake between an LLM and a tool:

- **Building an MCP server?** `toolscore mcp test` runs your server through generated happy-path *and* adversarial edge-case scenarios and grades whether an LLM can actually use it — catching broken tools, untyped schemas, and context bloat *before you publish*.
- **Building an agent?** Snapshot your agent's tool-calls and fail CI the instant a prompt or model change makes it call the wrong tool, with the wrong arguments, in the wrong order.
- **Already running agents?** Record real MCP sessions or import OpenTelemetry spans, and see what the score alone hides: failed calls, blind retries, required calls that never succeeded, credentials passed into tools, and calls your agent must never make.

## Releases

| Version | Date | Highlights |
|---------|------|------------|
| **1.10.0** | 2026-10-03 | Record real MCP sessions · behavior and safety checks (failed calls, blind retries, required calls completed, credentials in tool arguments, forbidden calls) · MCP lint for missing tools and tool poisoning · OpenTelemetry import · MCP trace fixes |
| 1.9.1 | 2026-10-01 | MCP scorecard fixes found on the official MCP reference servers |
| 1.9.0 | 2026-09-28 | Loop detection (`identical_rate`) · one-to-one argument pairing |
| 1.8.1 | 2026-06-19 | Snapshot testing · MCP scorecard · fluent `expect()` and matchers · native framework support · LLM judge for every provider |

Full notes, including upgrade advice, in the [CHANGELOG](CHANGELOG.md).

## See it in 10 seconds

```bash
# Grade a bundled sample MCP server — no install, no API key, no setup:
uvx tool-scorer demo

# Then point it at your own server:
uvx tool-scorer mcp test "python your_server.py"
```

You get an A–F scorecard, a ranked **"Top issues to fix"** list with concrete fixes, and a per-tool token-cost breakdown — in seconds, offline. Add `--ci` to gate your build (it writes the verdict to your GitHub Actions job summary and fails on blocking issues).

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

Point it at any MCP server — it auto-generates happy-path *and* adversarial edge-case scenarios from each tool's schema, runs them, lints the definitions, measures each tool's token cost, and returns an A–F grade plus a ranked **"Top issues to fix"** list. The fastest way to see it (zero install, no setup) is `toolscore demo`; against your own server:

```bash
toolscore mcp test "python my_server.py"

# or straight from your Claude Desktop config, zero install:
uvx tool-scorer mcp test --config claude_desktop_config.json --server my-server
```

```
╭──────────────────────────────────────╮
│ MCP Scorecard: notes-server 1.0.0    │
│ Grade B   Score 87%                  │
│ happy 80%  |  edge 100%  |  lint 93% │
╰──────────────────────────────────────╯
                         Tools
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Tool         ┃ Scenarios ┃ Avg latency ┃ Def. tokens ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ create_note  │       6/6 │      0.1 ms │          80 │
│ list_notes   │       6/6 │      0.1 ms │          59 │
│ search_notes │       6/6 │      0.1 ms │          48 │
│ delete_note  │       6/6 │      0.1 ms │          52 │
│ export_notes │       3/6 │      0.1 ms │          64 │
└──────────────┴───────────┴─────────────┴─────────────┘
Tool definitions cost ~303 estimated tokens of context across 5 tool(s).

Top issues to fix
  1. export_notes  fails on valid input (export failed: storage backend not configured)
     -> The tool errors on well-formed arguments — check the handler and the input schema.
  2. delete_note   property 'note_id' is missing a 'type'
     -> Give the property a JSON-schema type (and an enum where values are fixed).
  3. search_notes  description is very short (< 10 chars)
     -> Describe what the tool does and when to use it.
```

Export a Markdown report — for a CI artifact or your server's own README — with `--report md --output SCORECARD.md`:

```markdown
# MCP Scorecard: notes-server 1.0.0

**Grade: B** &middot; Score 87%

- Happy-path pass rate: 80%
- Edge-case resilience: 100%
- Lint score: 93% (1 errors, 1 warnings)
- Tool-definition tokens (estimated): ~303 across 5 tool(s)

## Tools

| Tool | Scenarios | Avg latency | Def. tokens |
| --- | --- | --- | --- |
| `create_note` | 6/6 | 0.1 ms | 80 |
| `list_notes` | 6/6 | 0.1 ms | 59 |
| `search_notes` | 6/6 | 0.1 ms | 48 |
| `delete_note` | 6/6 | 0.1 ms | 52 |
| `export_notes` | 3/6 | 0.1 ms | 64 |

## Top issues to fix

- **`export_notes`** — fails on valid input (export failed: storage backend not configured). _Fix:_ The tool errors on well-formed arguments — check the handler and that the input schema matches what the tool actually accepts.
- **`delete_note`** — property 'note_id' is missing a 'type'. _Fix:_ Give the property a JSON-schema type (and an enum where the values are fixed) so the model does not have to guess.
- **`search_notes`** — description is very short (< 10 chars). _Fix:_ Describe what the tool does and when to use it — models choose tools by their description.
```

Gate CI with `--fail-under B` (exit 1 below the bar), or add `--ci` to write the verdict to your GitHub Actions job summary and fail on blocking issues. `toolscore mcp list` and `toolscore mcp lint` are also available standalone.

What the lint checks, beyond schema hygiene:

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
response = client.chat.completions.create(model="gpt-4o", messages=[...], tools=[...])
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
toolscore eval gold.json trace.json --llm-judge                                  # OpenAI default
toolscore eval gold.json trace.json --llm-judge --llm-model claude-3-5-haiku-latest
toolscore eval gold.json trace.json --llm-judge --llm-model llama3.1 \
    --llm-base-url http://localhost:11434/v1                                     # local Ollama
```

```python
from toolscore import evaluate_trace, JudgeConfig

result = evaluate_trace("gold.json", "trace.json",
                        judge=JudgeConfig(model="gemini-2.0-flash"))
```

The provider is inferred from the model name. Install extras as needed: `tool-scorer[llm]` (OpenAI/compatible), `[anthropic]`, `[gemini]`. Everything else in Toolscore stays deterministic and offline.

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
    mcp-command: 'uvx my-mcp-server'
    mcp-fail-under: 'B'
```

The action also outputs `score`, `grade`, `required-call-recall` and `violations` for later steps.

Baseline regression checks catch slow degradation:

```bash
toolscore eval gold.json trace.json --save-baseline baseline.json   # once
toolscore regression baseline.json new_trace.json --gold-file gold.json
# exit codes: 0 = PASS, 1 = regression detected, 2 = error
```

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
ruff check toolscore
mypy toolscore
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Citation

```bibtex
@software{toolscore,
  title = {Toolscore: Lightweight Tool-Call Testing for LLM Agents},
  author = {Yotam Braun},
  year = {2025},
  url = {https://github.com/yotambraun/toolscore}
}
```
