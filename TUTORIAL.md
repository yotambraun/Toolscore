# Toolscore Tutorial: Complete Guide

This tutorial walks you through the complete workflow of using Toolscore to test LLM tool usage — from your first score to snapshot baselines, MCP scorecards, and CI.

## Table of Contents
1. [Overview](#overview)
2. [Quick Start (3 Lines)](#quick-start-3-lines)
3. [Setup](#setup)
4. [Snapshot Testing: Record, Approve, Replay](#snapshot-testing-record-approve-replay)
5. [Fluent API & Matchers](#fluent-api--matchers)
6. [Step 1: Capture Tool Usage Traces](#step-1-capture-tool-usage-traces)
7. [Step 2: Create Gold Standards](#step-2-create-gold-standards)
8. [Step 3: Evaluate and Generate Reports](#step-3-evaluate-and-generate-reports)
9. [Understanding the Metrics](#understanding-the-metrics)
10. [Self-Explaining Failures](#self-explaining-failures)
11. [MCP Scorecard](#mcp-scorecard)
12. [LLM Judge for Every Provider](#llm-judge-for-every-provider)
13. [Async Agents](#async-agents)
14. [Regression Testing](#regression-testing)
15. [CI/CD Integration](#cicd-integration)
16. [Advanced Usage](#advanced-usage)
    - [Pytest Integration](#pytest-integration)
    - [Integration Helpers](#integration-helpers)
    - [LangChain Support](#langchain-support)
    - [Custom Trace Format](#custom-trace-format)
    - [Batch Evaluation](#batch-evaluation)

## Overview

**What is Toolscore?**

Toolscore is the instant, free, deterministic health-check for LLM tool-calling. It checks whether your LLM agent calls the right tools, with the right arguments, in the right order — and whether an MCP server's tools can actually be used by an LLM — deterministically, locally, with zero API cost.

**What Toolscore does:**
- Evaluates tool-calling accuracy with a single composite score
- Records your agent's tool calls as snapshots and replays them as regression tests
- Accepts raw responses from OpenAI, Anthropic, Gemini, LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, and CrewAI — no glue code
- Tests, lints, and grades MCP servers

**What Toolscore does NOT do:**
- Call LLM APIs for scoring (the optional LLM judge is strictly opt-in)
- Execute your actual tools
- Train or fine-tune models

## Quick Start (3 Lines)

The simplest way to use Toolscore — no files, no config:

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

print(result.score)              # 0.85 (composite score)
print(result.selection_accuracy) # 1.0
print(result.argument_f1)        # 0.5
```

**Auto-detect provider responses** — pass raw OpenAI/Anthropic/Gemini/framework responses directly:

```python
from openai import OpenAI
from toolscore import evaluate

client = OpenAI()
response = client.chat.completions.create(model="gpt-4o", messages=[...], tools=[...])

# No from_openai() needed — auto-detected!
result = evaluate(expected=[...], actual=response)
```

For pytest, use the one-liner:

```python
from toolscore import assert_tools

def test_my_agent():
    assert_tools(
        expected=[{"tool": "search", "args": {"q": "test"}}],
        actual=my_agent_result,  # raw LLM response or list of dicts
        min_score=0.9,
    )
```

**End-to-end agent testing** with `test_agent()`:

```python
from toolscore import test_agent

result = test_agent(
    agent=my_agent_fn,          # any callable that returns an LLM response
    input="What's the weather?",
    expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
    min_score=0.9,              # optional: raises if below
)
```

**Argument-checking semantics** (important):

- `{"tool": "search"}` with `args` **omitted** means "the tool must be called — accept whatever arguments it got".
- `{"tool": "search", "args": {}}` with an **explicit empty dict** means "expect the tool to be called with **zero** arguments".

## Setup

### 1. Install Toolscore

```bash
# Install from PyPI (recommended)
pip install tool-scorer

# Or clone from source
git clone https://github.com/yotambraun/toolscore.git
cd toolscore

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"
```

### 2. Optional Dependencies

Install additional features as needed:

```bash
# HTTP validation support
pip install tool-scorer[http]

# LLM judge via OpenAI or any OpenAI-compatible endpoint (Ollama, vLLM, Groq)
pip install tool-scorer[llm]

# LLM judge via Anthropic
pip install tool-scorer[anthropic]

# LLM judge via Google Gemini
pip install tool-scorer[gemini]

# LangChain support
pip install tool-scorer[langchain]

# All optional features
pip install tool-scorer[all]
```

### 3. Set Up API Keys (Optional)

Only needed if you capture traces from a provider or use the LLM judge:

```bash
# Create .env file
echo "OPENAI_API_KEY=your-key-here" > .env
echo "ANTHROPIC_API_KEY=your-key-here" >> .env
echo "GOOGLE_API_KEY=your-key-here" >> .env
```

**Note:** `.env` is already in `.gitignore` - your keys are safe!

## Snapshot Testing: Record, Approve, Replay

The fastest way to get a real regression test is to not write expected calls at all. Record your agent's behavior once, review and approve it, then replay it forever — Jest snapshots for agents.

### The 60-second path

```bash
pip install tool-scorer
toolscore init          # detects your framework, scaffolds a passing pytest suite
pytest                  # first run records snapshots
toolscore approve --all # review, then bless them as the baseline
pytest                  # replays against the baseline from now on
```

`toolscore init` writes `tests/test_agent_tools.py` (with a stand-in agent you replace with your own) and a GitHub Actions workflow.

### The pytest fixture

The `toolscore_snapshot` fixture ships with the package — no plugin registration needed:

```python
def my_agent(prompt: str):
    # your real agent here — return the raw response or a list of call dicts
    return [
        {"tool": "search_flights", "args": {"origin": "SFO", "destination": "NYC"}},
        {"tool": "book_flight", "args": {"flight_id": "FL-1234"}},
    ]

def test_books_a_flight(toolscore_snapshot):
    toolscore_snapshot(my_agent("book a flight to NYC"))
```

What happens on each run:

1. **First run** — the calls are recorded into an *unapproved* snapshot under `.toolscore/snapshots/` and the test passes with a warning. The terminal summary says: `toolscore: 1 snapshot created (pending approval)`.
2. **After `toolscore approve --all`** — the snapshot is the baseline. Every run replays the agent and compares; drift fails the test with a full expected-vs-actual diff.
3. **In CI** — missing or unapproved snapshots **fail the build**. Snapshots are recorded and approved locally, never minted in CI. (Use `--toolscore-allow-pending` to downgrade that to a warning during rollout.)

Useful knobs:

```python
def test_with_options(toolscore_snapshot):
    toolscore_snapshot(
        my_agent("book a flight"),
        min_score=0.95,        # tolerate small drift (default 1.0 = exact replay)
        name="booking-happy",  # explicit name (default: pytest node id)
    )
```

### Re-recording on intentional change

```bash
pytest --toolscore-update            # overwrite + re-approve all snapshots used
# or: TOOLSCORE_RECORD_UPDATE=1 pytest
```

### Snapshot CLI

```bash
toolscore record -- pytest tests/ -k booking   # record via any command
toolscore record --from-trace trace.json --name my_snap   # record from a trace file
toolscore approve my_snap                      # approve one snapshot
toolscore approve --all                        # approve everything pending
toolscore snapshots list                       # status of all snapshots
toolscore snapshots show my_snap               # inspect recorded calls
toolscore snapshots rm my_snap --yes           # delete one
```

Snapshots are plain JSON files — commit them, and review changes to them like any other diff.

## Fluent API & Matchers

For explicit expectations, `expect()` reads like the sentence you would say out loud:

```python
from toolscore import expect, ANY, Regex

expect(agent).on("book me a flight to NYC") \
    .calls("search_flights", origin=ANY, destination="NYC") \
    .then_calls("book_flight", flight_id=Regex(r"FL-\d+")) \
    .does_not_call("cancel_booking") \
    .with_score(0.9) \
    .run()
```

- The subject may be an **agent callable** (pair with `.on(prompt)`) or an **already-produced result** (raw provider response or list of call dicts — skip `.on()`).
- `.calls("tool")` with **no kwargs** checks only that the tool was called — arguments are not checked.
- `.calls("tool", q="x")` checks the given arguments; matchers can stand in for any value.
- `.does_not_call("tool")` fails the test if the forbidden tool appears.
- `.with_weights(...)` and `.with_strict_args()` are also available; `.run()` returns the full `EvaluationResult`.

### Matchers

| Matcher | Matches | Example |
|---------|---------|---------|
| `ANY` | anything | `calls("search", q=ANY)` |
| `Regex(pattern)` | full string match | `Regex(r"FL-\d+")` |
| `Approx(value, rel, abs)` | numbers within tolerance | `Approx(40.71, rel=1e-2)` |
| `Contains(item)` | membership in str/list/dict | `Contains("metric")` |
| `OneOf(*values)` | any of the candidates | `OneOf("NYC", "New York")` |
| `IsType(*types)` | isinstance check (bool-safe) | `IsType(int)` |

Matchers work anywhere expected arguments appear — `evaluate`, `assert_tools`, `expect`, even gold-standard comparisons in memory:

```python
from toolscore import evaluate, Approx, Contains, IsType, OneOf

result = evaluate(
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
assert result.score > 0.999
```

## Step 1: Capture Tool Usage Traces

For file-based workflows you need traces from your LLM interactions. (If you test in pytest, you usually don't need files at all — pass responses directly to `evaluate()` / `expect()` / `toolscore_snapshot`.)

### Option A: Capture from OpenAI

Create `capture_openai_trace.py`:

```python
#!/usr/bin/env python3
"""Capture tool usage trace from OpenAI API."""
import json
import os
from openai import OpenAI

# Load API key from environment
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Define tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "make_file",
            "description": "Create a new file with specified content",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "lines_of_text": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["filename", "lines_of_text"]
            }
        }
    }
]

# Make API call
messages = [
    {"role": "user", "content": "Create a file called poem.txt with a two-line poem about AI"}
]

response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools,
    tool_choice="auto"
)

# Save the trace
trace = []
for choice in response.choices:
    if choice.message.tool_calls:
        trace.append({
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in choice.message.tool_calls
            ]
        })

with open("my_trace_openai.json", "w") as f:
    json.dump(trace, f, indent=2)

print("Trace saved to my_trace_openai.json")
```

### Option B: Capture from Anthropic

Create `capture_anthropic_trace.py`:

```python
#!/usr/bin/env python3
"""Capture tool usage trace from Anthropic API."""
import json
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

tools = [
    {
        "name": "make_file",
        "description": "Create a new file with specified content",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "lines_of_text": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["filename", "lines_of_text"]
        }
    }
]

message = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    tools=tools,
    messages=[
        {"role": "user", "content": "Create a file called poem.txt with a two-line poem about AI"}
    ]
)

trace = [{"role": "assistant", "content": [b.model_dump() for b in message.content]}]

with open("my_trace_anthropic.json", "w") as f:
    json.dump(trace, f, indent=2)

print("Trace saved to my_trace_anthropic.json")
```

### Option C: Use Existing Traces

Toolscore includes example traces in the `examples/` directory. You can use these to get started immediately!

## Step 2: Create Gold Standards

A gold standard defines the **expected** tool usage for a task. It's your "correct answer" reference.

Create `my_gold_standard.json`:

```json
[
  {
    "tool": "make_file",
    "args": {
      "filename": "poem.txt",
      "lines_of_text": ["Line 1 about AI", "Line 2 about AI"]
    },
    "description": "Create a file with a poem",
    "side_effects": {
      "file_exists": "poem.txt"
    }
  }
]
```

**Gold Standard Fields:**
- `tool` (required): Tool/function name
- `args` (optional): Expected arguments. **Omit it entirely** (or set it to `null`) to assert only that the tool is called, without checking arguments. An explicit `{}` means "expect zero arguments".
- `description` (optional): Human-readable description
- `side_effects` (optional): Expected side effects to validate

**Tips for Creating Gold Standards:**
1. Focus on required arguments - don't specify every detail
2. Omit `args` for tools where you only care that they were called
3. Think about what the agent SHOULD do, not what it COULD do
4. Use `side_effects` for critical validations (file creation, API calls, etc.)

## Step 3: Evaluate and Generate Reports

Now evaluate your trace against the gold standard!

### CLI Usage

```bash
# Basic evaluation
toolscore eval my_gold_standard.json my_trace_openai.json

# With HTML report
toolscore eval my_gold_standard.json my_trace_openai.json --html report.html

# Specify format explicitly
toolscore eval my_gold_standard.json my_trace_openai.json --format openai
```

### Python API Usage (In-Memory)

The simplest approach - no files needed:

```python
from toolscore import evaluate

result = evaluate(
    expected=[
        {"tool": "make_file", "args": {"filename": "poem.txt", "lines_of_text": ["Roses are red"]}},
    ],
    actual=my_agent_tool_calls,  # list of dicts from your agent
)

print(f"Overall Score: {result.score:.1%}")
print(f"Selection Accuracy: {result.selection_accuracy:.1%}")
print(f"Argument F1: {result.argument_f1:.1%}")
print(f"Sequence Accuracy: {result.sequence_accuracy:.1%}")
```

Custom weights are supported — provided values are merged with the defaults and **renormalized to sum to 1.0**:

```python
result = evaluate(
    expected=[{"tool": "search", "args": {"q": "x"}}],
    actual=[{"tool": "search", "args": {"q": "x"}}],
    weights={"selection_accuracy": 0.5, "argument_f1": 0.5,
             "sequence_accuracy": 0.0, "redundant_rate": 0.0},
)
```

### With Provider / Framework Responses

Pass raw responses directly — Toolscore auto-detects OpenAI, Anthropic, Gemini, LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, and CrewAI formats:

```python
from openai import OpenAI
from toolscore import evaluate

client = OpenAI()
response = client.chat.completions.create(model="gpt-4o", messages=[...], tools=[...])

# No from_openai() needed — auto-detected!
result = evaluate(expected=[...], actual=response)
```

You can still use the explicit helpers (`from_openai()`, `from_anthropic()`, `from_gemini()`, `from_langgraph()`, ...) if you prefer.

### Python API Usage (File-Based)

The file-based API is still supported for existing workflows:

```python
from toolscore import evaluate_trace

result = evaluate_trace(
    gold_file="my_gold_standard.json",
    trace_file="my_trace_openai.json",
    format="auto"
)

print(f"Overall Score: {result.score:.1%}")
print(f"Selection Accuracy: {result.selection_accuracy:.1%}")
print(f"Argument F1: {result.argument_f1:.1%}")
```

## Understanding the Metrics

### 1. Invocation Accuracy
**What it measures:** Did the agent invoke tools when needed and avoid them when not needed?

- `1.0` = Perfect - invoked exactly when required
- `< 1.0` = Missed some tool calls or invoked unnecessarily

### 2. Selection Accuracy
**What it measures:** Did the agent choose the correct tools?

- `1.0` = All tool names match gold standard
- `0.5` = Half of the tools were correct
- `0.0` = Wrong tools chosen

### 3. Sequence Accuracy & Edit Distance
**What it measures:** Did the agent call tools in the right order?

- Edit distance = Number of insertions/deletions/substitutions needed
- Sequence accuracy = 1 - (normalized edit distance)

### 4. Argument F1 Score
**What it measures:** How well did arguments match?

- **Precision:** Of the arguments provided, how many were correct?
- **Recall:** Of the required arguments, how many were provided?
- **F1:** Harmonic mean of precision and recall

Gold calls with `args` omitted are excluded from argument checking entirely — they count as a full match as long as the tool was called.

### 5. Redundant Call Rate
**What it measures:** Did the agent make unnecessary duplicate calls?

- `0.0` = No redundant calls
- `> 0.0` = Some calls were unnecessary

### 6. Side-Effect Success Rate
**What it measures:** Did expected side effects occur?

Only applicable if you specify `side_effects` in your gold standard and have validators enabled.

### The Composite Score

`result.score` is a weighted average: selection accuracy (40%), argument F1 (30%), sequence accuracy (20%), and inverted redundancy (10%). Override with `weights=` (values are renormalized to sum to 1.0).

## Self-Explaining Failures

Toolscore doesn't just give you a number — failed assertions render an aligned expected-vs-actual table with per-argument mismatches and tips, directly in the exception message:

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
```

The CLI's `--verbose` mode adds a "What Went Wrong" breakdown:

- **MISSING**: Expected tool was never called - check if your agent has access to the tool
- **EXTRA**: Tool was called but not expected - may indicate unnecessary calls
- **MISMATCH**: Wrong tool or argument at a specific position

Tips are generated from the failure pattern — e.g. similar tool names suggest `--llm-judge`, low recall suggests missing required arguments.

## MCP Scorecard

Toolscore can test any MCP (Model Context Protocol) server: it spins the server up over stdio, generates happy-path and edge-case scenarios from each tool's input schema, executes them, lints the tool definitions, measures each tool's token cost, and prints an A–F grade with a ranked **Top issues to fix** list.

The fastest way to try it — zero setup, no API key — is the bundled demo:

```bash
toolscore demo                 # grade a bundled sample MCP server
uvx tool-scorer demo           # ...or zero-install via uvx
```

Then point it at your own server:

```bash
# By launch command (quoted as one string):
toolscore mcp test "python my_server.py"

# Or from a Claude Desktop style config:
toolscore mcp test --config claude_desktop_config.json --server my-server

# Zero-install, via uvx:
uvx tool-scorer mcp test "python my_server.py"
```

Useful variants:

```bash
toolscore mcp list "python my_server.py"     # show advertised tools
toolscore mcp lint "python my_server.py"     # schema lint only (exit 1 on errors)
toolscore mcp test "python my_server.py" --cases 5 --no-edge-cases
toolscore mcp test "python my_server.py" --report md --output SCORECARD.md
toolscore mcp test "python my_server.py" --fail-under B    # CI gate: exit 1 below B
toolscore mcp test "python my_server.py" --ci              # write verdict to $GITHUB_STEP_SUMMARY, fail on blocking issues
```

The score blends happy-path pass rate (60%), edge-case resilience (20%), and schema lint cleanliness (20%); grades follow the usual bands (>= 0.9 is an A). The console verdict and Markdown report list the top issues to fix with concrete suggestions plus a per-tool token-cost breakdown; the Markdown report is designed to paste into your server's README or a PR comment.

## LLM Judge for Every Provider

All core metrics are deterministic. When tool names differ only semantically (`search_web` vs `web_search`), you can opt into an LLM judge via OpenAI, Anthropic, Gemini, or any OpenAI-compatible endpoint.

### CLI

```bash
toolscore eval gold.json trace.json --llm-judge                       # gpt-4o-mini (OpenAI)
toolscore eval gold.json trace.json --llm-judge --llm-model claude-3-5-haiku-latest
toolscore eval gold.json trace.json --llm-judge --llm-model gemini-2.0-flash

# Local model via Ollama (or any OpenAI-compatible server):
toolscore eval gold.json trace.json --llm-judge \
    --llm-model llama3.1 --llm-base-url http://localhost:11434/v1
```

The provider is inferred from the model name (`claude-*` -> Anthropic, `gemini-*` -> Gemini, a base URL -> OpenAI-compatible, otherwise OpenAI). Force it with `--llm-provider`.

### Python

`evaluate_trace()` takes a single `judge` parameter (this replaces the old `use_llm_judge` / `llm_judge_model` / `llm_judge_api_key` keyword arguments):

```python
from toolscore import evaluate_trace, JudgeConfig

# Disabled (default):
result = evaluate_trace("gold.json", "trace.json")

# Default judge (gpt-4o-mini via OPENAI_API_KEY):
result = evaluate_trace("gold.json", "trace.json", judge=True)

# Model-name shorthand:
result = evaluate_trace("gold.json", "trace.json", judge="claude-3-5-haiku-latest")

# Full control:
result = evaluate_trace("gold.json", "trace.json", judge=JudgeConfig(
    model="llama3.1",
    base_url="http://localhost:11434/v1",   # implies an OpenAI-compatible endpoint
))

print(result.metrics["semantic_metrics"])
```

API keys come from `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`, or `JudgeConfig(api_key=...)`. Install the matching extra: `tool-scorer[llm]`, `[anthropic]`, or `[gemini]`.

## Async Agents

Async agents are first-class citizens:

```python
import asyncio
from toolscore import test_agent_async, expect, ANY

async def my_async_agent(prompt: str):
    # await your framework here; return the raw response or call dicts
    return [{"tool": "get_weather", "args": {"city": "NYC"}}]

async def main():
    # End-to-end helper:
    result = await test_agent_async(
        agent=my_async_agent,
        input="What's the weather in NYC?",
        expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
        min_score=0.9,
    )

    # Fluent API:
    await (
        expect(my_async_agent)
        .on("What's the weather in NYC?")
        .calls("get_weather", city=ANY)
        .run_async()
    )

asyncio.run(main())
```

`test_agent_async` and `.run_async()` accept sync callables too. Passing an async agent to the sync `test_agent()` / `.run()` raises a clear `TypeError` pointing you at the async variant.

With pytest, use `pytest-asyncio` (or anyio) and call these from `async def` tests.

## Regression Testing

Regression testing lets you catch performance degradation automatically in CI/CD.

### Step 1: Create a Baseline

First, establish a baseline from your best evaluation:

```bash
toolscore eval gold.json trace.json --save-baseline baseline.json
```

This saves:
- All metric values
- Gold file hash (for verification)
- Timestamp
- Version information

### Step 2: Run Regression Checks

In CI/CD, compare new evaluations against the baseline:

```bash
# Basic regression check (5% threshold)
toolscore regression baseline.json new_trace.json --gold-file gold.json

# Custom threshold (10% allowed regression)
toolscore regression baseline.json trace.json -g gold.json -t 0.10

# Save comparison report
toolscore regression baseline.json trace.json -g gold.json -o comparison.json
```

### Exit Codes

- `0`: PASS - No regression detected
- `1`: FAIL - Regression detected (accuracy dropped beyond threshold)
- `2`: ERROR - Invalid files or other errors

## CI/CD Integration

### Snapshot replay (recommended)

`toolscore init` writes `.github/workflows/toolscore.yml` for you. The model: snapshots are recorded and approved locally and committed; CI only replays them. A missing or unapproved snapshot fails the build — CI never invents baselines.

```yaml
jobs:
  toolscore:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install tool-scorer pytest
      - run: pytest tests/ -q
```

### GitHub Action

For file-based evaluation or MCP scorecards, use the official action:

```yaml
# Threshold mode
- uses: yotambraun/toolscore@v1
  with:
    gold-file: tests/gold_standard.json
    trace-file: tests/agent_trace.json
    threshold: '0.90'

# Regression mode
- uses: yotambraun/toolscore@v1
  with:
    gold-file: tests/gold_standard.json
    trace-file: tests/agent_trace.json
    baseline-file: tests/baseline.json
    regression-threshold: '0.05'

# MCP scorecard mode
- uses: yotambraun/toolscore@v1
  with:
    mcp-command: 'uvx my-mcp-server'
    mcp-fail-under: 'B'
```

### Best Practices

1. **Commit your snapshots and baselines** - keep `.toolscore/snapshots/` and `baseline.json` in version control
2. **Update on intentional change** - `pytest --toolscore-update` locally, review the diff, commit
3. **Use meaningful thresholds** - 5% is a good regression default; snapshots default to exact replay
4. **Review regressions** - Not all regressions are bugs; some may be acceptable tradeoffs

## Advanced Usage

### Pytest Integration

The simplest way to test in pytest - use `assert_tools`:

```python
from toolscore import assert_tools

def test_my_agent():
    """One-liner agent test."""
    assert_tools(
        expected=[{"tool": "search", "args": {"q": "test"}}],
        actual=my_agent_output,  # raw LLM response or list of dicts
        min_score=0.9,
    )
```

Data-driven tests with `@toolscore.cases()`:

```python
import toolscore

@toolscore.cases([
    {"input": "weather NYC", "expected": [{"tool": "get_weather", "args": {"city": "NYC"}}]},
    {"input": "email bob",   "expected": [{"tool": "send_email", "args": {"to": "bob"}}]},
])
def test_my_agent(input, expected):
    response = my_agent(input)
    toolscore.assert_tools(expected=expected, actual=response, min_score=0.9)
```

File-based fixtures for gold/trace workflows:

```python
# test_my_agent.py
def test_agent_meets_accuracy_threshold(toolscore_eval, toolscore_assert):
    """Verify agent achieves minimum accuracy requirements."""
    result = toolscore_eval("gold_calls.json", "trace.json")

    toolscore_assert.assert_invocation_accuracy(result, threshold=0.9)
    toolscore_assert.assert_selection_accuracy(result, threshold=0.9)
    toolscore_assert.assert_argument_f1(result, min_f1=0.8)
    toolscore_assert.assert_sequence_accuracy(result, threshold=0.8)
```

Configure directories via CLI options:

```bash
pytest --toolscore-gold-dir tests/gold_standards --toolscore-trace-dir tests/traces
```

### Integration Helpers

Extract tool calls explicitly when you want them as plain dicts:

```python
from toolscore.integrations import (
    from_openai, from_anthropic, from_gemini,
    from_langgraph, from_pydantic_ai, from_openai_agents,
    from_claude_agent_sdk, from_crewai, auto_extract,
)

calls = from_openai(openai_response)
calls = from_anthropic(anthropic_message)
calls = from_langgraph(graph_state)
calls = auto_extract(anything)   # the auto-detector used internally

from toolscore import evaluate
result = evaluate(expected=[...], actual=calls)
```

### Interactive Tutorials

Toolscore includes Jupyter notebooks for hands-on learning:

1. **Quickstart Tutorial** (`examples/notebooks/01_quickstart.ipynb`)
2. **Custom Formats** (`examples/notebooks/02_custom_formats.ipynb`)
3. **Advanced Metrics** (`examples/notebooks/03_advanced_metrics.ipynb`)

Run locally:
```bash
cd examples/notebooks
jupyter notebook
```

### LangChain Support

Toolscore supports LangChain agent traces in both legacy and modern formats:

**Legacy format (AgentAction):**
```python
import json

# Your LangChain agent execution
result = agent_executor.invoke({"input": "Search for Python tutorials"})

# Extract tool calls from result
trace = []
for step in result['intermediate_steps']:
    action, observation = step
    trace.append({
        "tool": action.tool,
        "tool_input": action.tool_input,
        "log": action.log
    })

with open("langchain_trace.json", "w") as f:
    json.dump(trace, f, indent=2)
```

**Modern format (ToolCall):**
```python
trace = [
    {
        "name": "search",
        "args": {"query": "Python tutorials"},
        "id": "call_123"
    }
]
```

Evaluate LangChain traces:
```bash
toolscore eval gold_calls.json langchain_trace.json --format langchain
# Or use auto-detection
toolscore eval gold_calls.json langchain_trace.json --format auto
```

### Custom Trace Format

If you have a custom format:

```json
{
  "calls": [
    {
      "tool": "my_tool",
      "args": {"param": "value"},
      "result": "success"
    }
  ]
}
```

Toolscore can auto-detect it!

### Batch Evaluation

Evaluate multiple traces:

```python
import glob
from toolscore import evaluate_trace

gold_file = "my_gold_standard.json"
results = []

for trace_file in glob.glob("traces/*.json"):
    result = evaluate_trace(gold_file, trace_file, format="auto")
    results.append({
        "file": trace_file,
        "accuracy": result.metrics['selection_accuracy']
    })

# Find best performer
best = max(results, key=lambda x: x['accuracy'])
print(f"Best trace: {best['file']} ({best['accuracy']:.1%})")
```

## Real-World Workflow Example

A complete workflow for a new agent:

```bash
# 1. Scaffold and record
toolscore init
pytest                          # records snapshots
toolscore snapshots list        # review what was recorded
toolscore approve --all

# 2. Grade your MCP server (if you ship one)
toolscore mcp test "python my_server.py" --report md --output SCORECARD.md

# 3. Wire CI
git add .toolscore/snapshots .github/workflows/toolscore.yml SCORECARD.md
git commit -m "test: add toolscore snapshot suite and MCP scorecard"

# 4. Iterate — when behavior intentionally changes:
pytest --toolscore-update
git diff .toolscore/snapshots   # review the drift, then commit
```

## Next Steps

- Check out more examples in `examples/`
- Read the full docs at https://tool-scorer.readthedocs.io
- Read `CONTRIBUTING.md` to contribute new metrics
- Star the repo on GitHub if this helps your project!

## Support

- **Issues:** https://github.com/yotambraun/toolscore/issues
- **Discussions:** https://github.com/yotambraun/toolscore/discussions

Happy evaluating!
