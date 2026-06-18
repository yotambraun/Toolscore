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

[![PyPI version](https://badge.fury.io/py/tool-scorer.svg)](https://badge.fury.io/py/tool-scorer)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Downloads](https://static.pepy.tech/badge/tool-scorer)](https://pepy.tech/project/tool-scorer)
[![Python Versions](https://img.shields.io/pypi/pyversions/tool-scorer.svg)](https://pypi.org/project/tool-scorer/)
[![CI](https://github.com/yotambraun/toolscore/workflows/CI/badge.svg)](https://github.com/yotambraun/toolscore/actions)
[![GitHub stars](https://img.shields.io/github/stars/yotambraun/toolscore?style=social)](https://github.com/yotambraun/toolscore)

---

**Toolscore is the instant, free, deterministic health-check for LLM tool-calling.** Point it at an MCP server or an agent and get a clear *"here's your grade and exactly what's broken"* verdict — deterministically, offline, with zero API cost. No LLM judge, no cloud, no per-test bill.

It's two sides of the same handshake between an LLM and a tool:

- **Building an MCP server?** `toolscore mcp test` runs your server through generated happy-path *and* adversarial edge-case scenarios and grades whether an LLM can actually use it — catching broken tools, untyped schemas, and context bloat *before you publish*.
- **Building an agent?** Snapshot your agent's tool-calls and fail CI the instant a prompt or model change makes it call the wrong tool, with the wrong arguments, in the wrong order.

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

The first standard testing tool for MCP servers. Point it at any server — it auto-generates happy-path and edge-case scenarios from each tool's schema, executes them, lints the tool definitions, and prints an A–F grade:

```bash
toolscore mcp test "python my_server.py"

# or straight from your Claude Desktop config, zero install:
uvx tool-scorer mcp test --config claude_desktop_config.json --server my-server
```

```
╭─────────────────────────────────────╮
│ MCP Scorecard: fake-mcp 0.1.0       │
│ Grade F   Score 47%                 │
│ happy 43%  |  edge 20%  |  lint 85% │
╰─────────────────────────────────────╯
                 Tools
┏━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Tool       ┃ Scenarios ┃ Avg latency ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ add        │       4/6 │      0.1 ms │
│ flaky      │       0/5 │      0.0 ms │
│ bad_schema │       0/1 │      0.0 ms │
└────────────┴───────────┴─────────────┘
```

Export a Markdown scorecard for your server's README with `--report md --output SCORECARD.md`. Here is the real output for the deliberately broken demo server above:

```markdown
# MCP Scorecard: fake-mcp 0.1.0

**Grade: F** &middot; Score 47%

- Happy-path pass rate: 43%
- Edge-case resilience: 20%
- Lint score: 85% (1 errors, 2 warnings)

## Tools

| Tool | Scenarios | Avg latency |
| --- | --- | --- |
| `add` | 4/6 | 0.1 ms |
| `flaky` | 0/5 | 0.0 ms |
| `bad_schema` | 0/1 | 0.0 ms |

## Lint

- warning &middot; `flaky`: properties defined but no 'required' list declared
- warning &middot; `bad_schema`: missing description
- **error** &middot; `bad_schema`: missing or empty inputSchema
```

Gate CI on quality with `--fail-under B` (exit code 1 below the bar). `toolscore mcp list` and `toolscore mcp lint` are also available standalone.

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
| MCP (JSON-RPC 2.0 traces) | Yes | file-based `format="mcp"` |
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

The composite `result.score` weighs selection accuracy (40%), argument F1 (30%), sequence accuracy (20%), and redundancy (10%); pass `weights={...}` to re-balance (weights are renormalized to sum to 1.0).

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

# MCP scorecard mode — grade your MCP server on every PR
- uses: yotambraun/toolscore@v1
  with:
    mcp-command: 'uvx my-mcp-server'
    mcp-fail-under: 'B'
```

Baseline regression checks catch slow degradation:

```bash
toolscore eval gold.json trace.json --save-baseline baseline.json   # once
toolscore regression baseline.json new_trace.json --gold-file gold.json
# exit codes: 0 = PASS, 1 = regression detected, 2 = error
```

## When to Use Toolscore vs. the Platforms

Toolscore is the pytest of tool-calling: it runs in your test suite, deterministically, for free. Observability and eval platforms watch your agent in production. Use both.

| You want to... | Use |
|----------------|-----|
| Fail the CI build when tool calls drift, deterministically, $0 per run | **Toolscore** |
| Grade and lint an MCP server | **Toolscore** (`toolscore mcp test`) |
| Score production traces across many quality dimensions (hallucination, toxicity, RAG) | [DeepEval](https://github.com/confident-ai/deepeval), [MLflow](https://mlflow.org/) |
| Trace, monitor, and debug agents in production | [LangSmith](https://smith.langchain.com/), [Arize Phoenix](https://phoenix.arize.com/) |
| Evaluate RAG retrieval/faithfulness | [Ragas](https://github.com/explodinggradients/ragas) |
| Safety-focused evaluation harnesses | [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) |

Toolscore does one thing well: it verifies your agent calls the right tools, with the right arguments, in the right order — before you ship.

## Learn More

- [Documentation](https://tool-scorer.readthedocs.io) — full API reference and guides
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
