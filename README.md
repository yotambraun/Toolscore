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

## 3-Line Quick Start

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
print(result.argument_f1)       # 0.7
```

No files, no config, no API keys. Just Python objects in, score out.

## What is Toolscore?

Toolscore is the simplest way to **unit-test LLM tool calls**. It compares the tool calls your agent _actually_ made against what you _expected_, and gives you a score.

- **Deterministic** - no LLM calls needed for evaluation (optional LLM judge available)
- **Local-first** - runs entirely on your machine, zero cloud dependencies
- **Zero API cost** - evaluation itself is free, always
- **Works with any provider** - OpenAI, Anthropic, Gemini, LangChain, MCP, or custom formats

## Installation

```bash
pip install tool-scorer
```

## Usage

### Python API (recommended)

```python
from toolscore import evaluate, assert_tools

# Get a detailed result
result = evaluate(
    expected=[{"tool": "search", "args": {"q": "test"}}],
    actual=[{"tool": "search", "args": {"q": "test"}}],
)
assert result.score == 1.0

# Or use the one-liner for pytest
assert_tools(
    expected=[{"tool": "search", "args": {"q": "test"}}],
    actual=[{"tool": "search", "args": {"q": "test"}}],
    min_score=0.9,
)
```

### With OpenAI / Anthropic / Gemini responses

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

### CLI

```bash
# Both `toolscore` and `tool-scorer` work
toolscore eval gold_calls.json trace.json

# Simplified output by default, use --verbose for full detail
toolscore eval gold_calls.json trace.json --verbose

# HTML report
toolscore eval gold_calls.json trace.json --html report.html

# Compare multiple models
toolscore compare gold.json gpt4.json claude.json -n gpt-4 -n claude-3
```

### Pytest Integration

```python
# test_my_agent.py
def test_agent_accuracy(toolscore_eval, toolscore_assertions):
    """Test that agent achieves high accuracy."""
    result = toolscore_eval("gold_calls.json", "trace.json")
    toolscore_assertions.assert_selection_accuracy(result, min_accuracy=0.9)
    toolscore_assertions.assert_argument_f1(result, min_f1=0.8)
```

Or use the simpler `assert_tools`:

```python
from toolscore import assert_tools

def test_agent():
    assert_tools(
        expected=[{"tool": "search", "args": {"q": "test"}}],
        actual=my_agent_output,
        min_score=0.9,
    )
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

## Metrics

The composite `result.score` is a weighted average of these core metrics:

| Metric | Weight | Description |
|--------|--------|-------------|
| **Selection Accuracy** | 40% | Did the agent call the right tools? |
| **Argument F1** | 30% | Did it pass the right arguments? |
| **Sequence Accuracy** | 20% | Were tools called in the right order? |
| **Redundancy** (inverted) | 10% | Were there unnecessary duplicate calls? |

Access individual metrics via properties:

```python
result.score               # Weighted composite (0.0 - 1.0)
result.selection_accuracy  # Tool name matching
result.argument_f1         # Argument precision/recall
result.sequence_accuracy   # Order correctness
```

Custom weights are supported:

```python
result = evaluate(
    expected=[...],
    actual=[...],
    weights={"selection_accuracy": 0.5, "argument_f1": 0.5, "sequence_accuracy": 0.0, "redundant_rate": 0.0},
)
```

### Additional Metrics (verbose mode)

When using `--verbose` or the file-based API, Toolscore also reports:
- Tool Invocation Accuracy
- Tool Correctness (coverage of expected tools)
- Trajectory Accuracy (multi-step path analysis)
- Detailed failure analysis with actionable error messages

## Regression Testing

Catch performance degradation in CI:

```bash
# Save a baseline
toolscore eval gold.json trace.json --save-baseline baseline.json

# Check for regressions (fails if accuracy drops >5%)
toolscore regression baseline.json new_trace.json --gold-file gold.json
```

## GitHub Action

```yaml
- uses: yotambraun/toolscore@v1
  with:
    gold-file: tests/gold_standard.json
    trace-file: tests/agent_trace.json
    threshold: '0.90'
```

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

These features are available for users who need them:

- **LLM-as-a-Judge**: `--llm-judge` flag for semantic tool name matching (requires OpenAI API key)
- **Schema Validation**: Validate argument types, ranges, and patterns against schemas
- **Side-Effect Validation**: Check HTTP responses, filesystem state, database rows
- **Cost Tracking**: Token usage and pricing estimation for OpenAI/Anthropic/Gemini
- **Multiple report formats**: HTML, JSON, CSV, Markdown
- **Synthetic test generation**: `toolscore generate --from-openai functions.json`

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
