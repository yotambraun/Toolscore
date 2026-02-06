<p align="center">
  <img src="assets/logo.png" alt="Toolscore Logo" width="200"/>
</p>

<h1 align="center">Toolscore</h1>

<p align="center">
  <em>Lightweight tool-call testing for LLM agents &mdash; deterministic, local, zero API cost</em>
</p>

[![PyPI version](https://badge.fury.io/py/tool-scorer.svg)](https://badge.fury.io/py/tool-scorer)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Downloads](https://static.pepy.tech/badge/tool-scorer)](https://pepy.tech/project/tool-scorer)
[![Python Versions](https://img.shields.io/pypi/pyversions/tool-scorer.svg)](https://pypi.org/project/tool-scorer/)
[![CI](https://github.com/yotambraun/toolscore/workflows/CI/badge.svg)](https://github.com/yotambraun/toolscore/actions)

---

## Why Toolscore?

You ship an LLM agent. It calls tools — search APIs, databases, file ops. But after a prompt tweak or model upgrade, how do you know it still calls the *right* tools with the *right* arguments in the *right* order?

Toolscore gives you a deterministic score for that — no API calls, no cloud, no cost.

- **Prompt changed** — did tool calls break?
- **Switched from GPT-4o to Claude** — same behavior?
- **CI/CD** — catch regressions before production

## Quick Start

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

print(result.score)              # 0.85 — overall quality (weighted composite)
print(result.selection_accuracy) # 1.0  — right tools picked
print(result.argument_f1)        # 0.7  — 70% of arguments correct
```

No files, no config, no API keys. Just Python objects in, score out.

## Installation

```bash
pip install tool-scorer
```

## What You Get

| Feature | How |
|---------|-----|
| In-memory evaluation | `evaluate(expected, actual)` |
| One-liner test assertion | `assert_tools(expected, actual, min_score=0.9)` |
| OpenAI/Anthropic/Gemini extraction | `from_openai(response)`, `from_anthropic()`, `from_gemini()` |
| 6 CLI commands | `toolscore eval`, `compare`, `regression`, `init`, `generate`, `validate` |
| Self-explaining failures | Shows MISSING / EXTRA / MISMATCH with actionable tips |
| Regression testing | Save baselines, catch degradation in CI |
| Pytest plugin | Fixtures, markers, assertion helpers |
| GitHub Action | One-click CI/CD setup |
| 4 report formats | HTML, JSON, CSV, Markdown |
| 6 trace formats | OpenAI, Anthropic, Gemini, LangChain, MCP, Custom (auto-detected) |

## Python API

### Basic evaluation

```python
from toolscore import evaluate, assert_tools

# Get a detailed result
result = evaluate(
    expected=[{"tool": "search", "args": {"q": "test"}}],
    actual=[{"tool": "search", "args": {"q": "test"}}],
)
assert result.score == 1.0
```

### With LLM provider responses

No need to manually extract tool calls from API responses:

```python
from openai import OpenAI
from toolscore import evaluate
from toolscore.integrations import from_openai

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    tools=[...],
)

actual = from_openai(response)
result = evaluate(expected=[...], actual=actual)
```

Also available: `from_anthropic()` and `from_gemini()`.

### One-liner for tests

```python
from toolscore import assert_tools

assert_tools(
    expected=[{"tool": "search", "args": {"q": "test"}}],
    actual=[{"tool": "search", "args": {"q": "test"}}],
    min_score=0.9,  # raises ToolScoreAssertionError if below
)
```

## When Things Go Wrong

Toolscore doesn't just give you a number — it tells you *what* went wrong and *how* to fix it. Here's a failing evaluation:

```python
result = evaluate(
    expected=[
        {"tool": "search_web", "args": {"query": "Python tutorials"}},
        {"tool": "summarize", "args": {"text": "..."}},
    ],
    actual=[
        {"tool": "web_search", "args": {"query": "Python tutorials"}},
        {"tool": "send_email", "args": {"to": "user@example.com"}},
    ],
)
print(result.score)  # 0.35
```

Run the CLI with `--verbose` to see exactly what happened:

```
toolscore eval gold.json trace.json --verbose

  Toolscore Evaluation Results

  Expected calls: 2
  Actual calls:   2

  Metric              Score     Details
  Selection Accuracy  0.0%      0 of 2 correct
  Argument F1         50.0%     P:100.0% R:50.0%
  Sequence Accuracy   0.0%      Edit distance: 2

  What Went Wrong:
    MISSING: Expected tool 'search_web' was never called
    MISMATCH: Position 0 — expected 'search_web', got 'web_search' (similar name?)
    EXTRA: Tool 'send_email' was called but not expected

  Tips:
    TIP: 'search_web' and 'web_search' look similar — use --llm-judge to check semantic equivalence
    TIP: Review prompt instructions for tool naming conventions
```

## Pytest Integration

The simplest approach — `assert_tools` works anywhere:

```python
from toolscore import assert_tools

def test_my_agent():
    actual = my_agent("What's the weather in NYC?")
    assert_tools(
        expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
        actual=actual,
        min_score=0.9,
    )
```

For file-based workflows, use the built-in fixtures:

```python
def test_agent_accuracy(toolscore_eval, toolscore_assert):
    """Test that agent achieves high accuracy."""
    result = toolscore_eval("gold_calls.json", "trace.json")
    toolscore_assert.assert_selection_accuracy(result, min_accuracy=0.9)
    toolscore_assert.assert_argument_f1(result, min_f1=0.8)
```

Configure directories via CLI options:

```bash
pytest --toolscore-gold-dir tests/gold_standards --toolscore-trace-dir tests/traces
```

## CLI

Six commands cover the full workflow:

```bash
toolscore eval gold.json trace.json              # Evaluate
toolscore eval gold.json trace.json --verbose     # Full detail + failure analysis
toolscore eval gold.json trace.json --html report.html  # HTML report
toolscore compare gold.json gpt4.json claude.json # Side-by-side model comparison
toolscore regression baseline.json trace.json -g gold.json  # CI regression check
toolscore init                                    # Scaffold a new project
toolscore generate --from-openai funcs.json       # Synthetic test data from schemas
toolscore validate trace.json                     # Check trace format
```

## Metrics Deep Dive

The composite `result.score` is a weighted average of four core metrics:

| Metric | Weight | Plain English |
|--------|--------|---------------|
| **Selection Accuracy** | 40% | Did it pick the right tools? |
| **Argument F1** | 30% | Did it pass the right arguments? |
| **Sequence Accuracy** | 20% | Did it call them in the right order? |
| **Redundancy** (inverted) | 10% | Did it avoid unnecessary repeat calls? |

Custom weights are supported:

```python
result = evaluate(
    expected=[...],
    actual=[...],
    weights={
        "selection_accuracy": 0.5,
        "argument_f1": 0.5,
        "sequence_accuracy": 0.0,
        "redundant_rate": 0.0,
    },
)
```

Additional metrics available in verbose mode: invocation accuracy, tool correctness, trajectory accuracy, cost tracking, latency.

## CI/CD & Regression Testing

### GitHub Action

```yaml
- uses: yotambraun/toolscore@v1
  with:
    gold-file: tests/gold_standard.json
    trace-file: tests/agent_trace.json
    threshold: '0.90'
```

### Regression testing

Save a baseline, then check for regressions on every run:

```bash
# Save a baseline
toolscore eval gold.json trace.json --save-baseline baseline.json

# Check for regressions (fails if accuracy drops >5%)
toolscore regression baseline.json new_trace.json --gold-file gold.json
```

Exit codes: `0` = PASS, `1` = FAIL (regression detected), `2` = ERROR — plug directly into CI.

## Supported Formats

| Provider | Format | Auto-detected |
|----------|--------|---------------|
| OpenAI | `tool_calls` / `function_call` | Yes |
| Anthropic | `tool_use` content blocks | Yes |
| Google Gemini | `functionCall` parts | Yes |
| MCP | JSON-RPC 2.0 | Yes |
| LangChain | `tool` / `tool_input` | Yes |
| Custom | `{"calls": [{"tool": ..., "args": ...}]}` | Yes |

## Advanced Features

### LLM-as-a-Judge

Semantic tool name matching when exact names don't line up (requires OpenAI API key):

```bash
toolscore eval gold.json trace.json --llm-judge
```

### Cost Tracking

Token usage and pricing estimation for OpenAI, Anthropic, and Gemini models:

```python
from toolscore.metrics.cost_estimator import calculate_llm_cost, estimate_trace_cost

cost = calculate_llm_cost("gpt-4o", input_tokens=1000, output_tokens=500)
trace_cost = estimate_trace_cost("gpt-4o", trace_calls)
```

### Schema Validation

Validate argument types, ranges, and patterns against JSON schemas:

```python
from toolscore.validators.schema import validate_argument_schema

valid, errors = validate_argument_schema(call, schema={
    "query": {"type": "string", "minLength": 1},
    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
})
```

### Side-Effect Validation

Verify HTTP responses, files created, and database rows after tool execution:

```bash
toolscore eval gold.json trace.json  # side-effect validation is on by default
```

### Trace Capture

Record production tool calls with the `@capture_trace` decorator:

```python
from toolscore import capture_trace

@capture_trace(name="my-agent")
def run_agent(prompt):
    # ... your agent code ...
    return result
```

### Synthetic Test Generation

Generate gold-standard test cases from OpenAI function schemas:

```bash
toolscore generate --from-openai functions.json -n 10 --output gold.json
```

### Interactive Debug

Step through mismatches one by one:

```bash
toolscore eval gold.json trace.json --debug
```

### Multi-Model Comparison

Compare two or more models side by side:

```bash
toolscore compare gold.json gpt4.json claude.json -n gpt-4 -n claude-3
```

## When to Use Toolscore vs. Alternatives

| Use case | Recommendation |
|----------|---------------|
| **Fast, deterministic tool-call checks in CI without API costs** | **Toolscore** |
| **Comprehensive LLM evaluation across multiple dimensions** (hallucination, toxicity, RAG, tool calls, etc.) | [DeepEval](https://github.com/confident-ai/deepeval) |
| **RAG pipeline evaluation** (retrieval quality, answer faithfulness) | [Ragas](https://github.com/explodinggradients/ragas) |
| **Government/safety-focused AI evaluation** | [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) |
| **Tracing and observability for LangChain apps** | [LangSmith](https://smith.langchain.com/) |

Toolscore does **one thing well**: it checks whether your agent called the right tools with the right arguments, deterministically, with zero cost. If you need broader LLM evaluation, the tools above are excellent choices.

## File-Based API

The original file-based API is still fully supported:

```python
from toolscore import evaluate_trace

result = evaluate_trace(
    gold_file="gold_calls.json",
    trace_file="trace.json",
    format="auto",
)
print(result.score)
print(result.selection_accuracy)
```

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
