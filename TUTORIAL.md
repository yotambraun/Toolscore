# Toolscore Tutorial: Complete Guide

This tutorial walks you through the complete workflow of using Toolscore to evaluate LLM tool usage.

## Table of Contents
1. [Overview](#overview)
2. [Quick Start (3 Lines)](#quick-start-3-lines)
3. [Setup](#setup)
4. [Step 1: Capture Tool Usage Traces](#step-1-capture-tool-usage-traces)
5. [Step 2: Create Gold Standards](#step-2-create-gold-standards)
6. [Step 3: Evaluate and Generate Reports](#step-3-evaluate-and-generate-reports)
7. [Understanding the Metrics](#understanding-the-metrics)
8. [Self-Explaining Metrics](#self-explaining-metrics)
9. [Regression Testing](#regression-testing)
10. [CI/CD Integration](#cicd-integration)
11. [Advanced Usage](#advanced-usage)
    - [Pytest Integration](#pytest-integration)
    - [Integration Helpers](#integration-helpers)
    - [LangChain Support](#langchain-support)
    - [Custom Trace Format](#custom-trace-format)
    - [Batch Evaluation](#batch-evaluation)

## Overview

**What is Toolscore?**

Toolscore is the simplest way to unit-test LLM tool calls. It compares actual tool calls against expected behavior and gives you a score - deterministically, locally, with zero API cost.

**What Toolscore does:**
- Evaluates tool calling accuracy with a single composite score
- Compares expected vs actual tool calls as Python objects (no files needed)
- Integrates directly with OpenAI, Anthropic, and Gemini responses

**What Toolscore does NOT do:**
- Call LLM APIs directly (you capture traces separately)
- Execute actual tool calls
- Train or fine-tune models

## Quick Start (3 Lines)

The simplest way to use Toolscore - no files, no config:

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

For pytest, use the one-liner:

```python
from toolscore import assert_tools

def test_my_agent():
    assert_tools(
        expected=[{"tool": "search", "args": {"q": "test"}}],
        actual=my_agent_result,
        min_score=0.9,
    )
```

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

# LLM-as-a-judge metrics (OpenAI API)
pip install tool-scorer[llm]

# LangChain support
pip install tool-scorer[langchain]

# All optional features
pip install tool-scorer[all]
```

### 3. Set Up API Keys (Optional)

If you plan to capture traces from OpenAI or Anthropic, or use LLM-as-a-judge metrics, create a `.env` file:

```bash
# Create .env file
echo "OPENAI_API_KEY=your-key-here" > .env
echo "ANTHROPIC_API_KEY=your-key-here" >> .env
```

**Note:** `.env` is already in `.gitignore` - your keys are safe!

## Step 1: Capture Tool Usage Traces

Before you can evaluate, you need to capture traces from your LLM interactions.

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
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"}
                },
                "required": ["filename"]
            }
        }
    }
]

# Make API call
messages = [
    {"role": "user", "content": "Create a file called poem.txt with a two-line poem about AI"}
]

response = client.chat.completions.create(
    model="gpt-4",
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

# Save trace to file
with open("my_trace_openai.json", "w") as f:
    json.dump(trace, f, indent=2)

print("✓ Trace saved to my_trace_openai.json")
```

Run it:
```bash
python capture_openai_trace.py
```

### Option B: Capture from Anthropic

Create `capture_anthropic_trace.py`:

```python
#!/usr/bin/env python3
"""Capture tool usage trace from Anthropic API."""
import json
import os
from anthropic import Anthropic

# Load API key from environment
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Define tools
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
    },
    {
        "name": "read_file",
        "description": "Read contents of a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"}
            },
            "required": ["filename"]
        }
    }
]

# Make API call
message = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    tools=tools,
    messages=[
        {"role": "user", "content": "Create a file called poem.txt with a two-line poem about AI"}
    ]
)

# Save the trace (simplified - just the content)
trace = [{"role": "assistant", "content": message.content, "stop_reason": message.stop_reason}]

# Save trace to file
with open("my_trace_anthropic.json", "w") as f:
    json.dump(trace, f, indent=2)

print("✓ Trace saved to my_trace_anthropic.json")
```

Run it:
```bash
python capture_anthropic_trace.py
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
- `args` (required): Expected arguments (can be partial - only required fields)
- `description` (optional): Human-readable description
- `side_effects` (optional): Expected side effects to validate

**Tips for Creating Gold Standards:**
1. Focus on required arguments - don't specify every detail
2. Think about what the agent SHOULD do, not what it COULD do
3. Use `side_effects` for critical validations (file creation, API calls, etc.)

## Step 3: Evaluate and Generate Reports

Now evaluate your trace against the gold standard!

### CLI Usage

```bash
# Basic evaluation
tool-scorer eval my_gold_standard.json my_trace_openai.json

# With HTML report
tool-scorer eval my_gold_standard.json my_trace_openai.json --html report.html

# Specify format explicitly
tool-scorer eval my_gold_standard.json my_trace_openai.json --format openai
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

### With OpenAI / Anthropic Responses

Use integration helpers to extract tool calls directly from API responses:

```python
from openai import OpenAI
from toolscore import evaluate
from toolscore.integrations import from_openai

client = OpenAI()
response = client.chat.completions.create(model="gpt-4o", messages=[...], tools=[...])

actual = from_openai(response)
result = evaluate(expected=[...], actual=actual)
```

Also available: `from_anthropic()` and `from_gemini()`.

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

### 5. Redundant Call Rate
**What it measures:** Did the agent make unnecessary duplicate calls?

- `0.0` = No redundant calls
- `> 0.0` = Some calls were unnecessary

### 6. Side-Effect Success Rate
**What it measures:** Did expected side effects occur?

Only applicable if you specify `side_effects` in your gold standard and have validators enabled.

### 7. LLM-as-a-judge Semantic Correctness (Optional)
**What it measures:** Beyond exact string matching, are the tool calls semantically equivalent?

This optional metric uses OpenAI API to evaluate semantic similarity. Useful for catching cases where tool names or arguments differ slightly but intentions match (e.g., `search_web` vs `web_search`).

```python
# Requires: pip install tool-scorer[llm]
# Set OPENAI_API_KEY in .env or environment
from toolscore.metrics import calculate_semantic_correctness

result = calculate_semantic_correctness(gold_calls, trace_calls, model="gpt-4o-mini")
print(f"Semantic Score: {result['semantic_score']:.2%}")
print(f"Explanations: {result['explanations']}")
```

## Self-Explaining Metrics

Toolscore v1.4+ includes **self-explaining metrics** that tell you exactly what went wrong and how to fix it.

### What You'll See

When you run an evaluation, you'll see output like this:

```
Core Metrics
Metric              Score     Details
Selection Accuracy  75.0%     3 of 4 correct
Tool Correctness    66.7%     2 of 3 expected tools called
Argument F1         80.0%     Precision: 85.0%, Recall: 75.0%

What Went Wrong:
   MISSING: Expected tool 'search_web' was never called
   MISMATCH: Position 2: Expected 'summarize' but got 'summary' (similar names)
   EXTRA: Tool 'log_debug' was called but not expected

Tips:
   TIP: 'search_web' might be equivalent to 'web_search' - use --llm-judge to verify
   TIP: Use --llm-judge flag to catch semantic equivalence
```

### Categories Explained

- **MISSING**: Expected tool was never called - check if your agent has access to the tool
- **EXTRA**: Tool was called but not expected - may indicate unnecessary calls
- **MISMATCH**: Wrong tool or argument at a specific position

### Tips

Tips are automatically generated based on detected issues:
- Tool name mismatches suggest using `--llm-judge` for semantic matching
- Low precision suggests the agent is passing extra/wrong arguments
- Low recall suggests required arguments are missing

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

### Understanding Results

**PASS output:**
```
PASS: No significant changes (threshold: 5%)

Metric              Baseline    Current     Delta      Status
Selection           92.0%       93.1%       +1.1%      OK
Invocation          88.0%       87.2%       -0.8%      OK
Arguments F1        85.0%       84.5%       -0.5%      OK
```

**FAIL output:**
```
FAIL: 1 regression(s) detected (threshold: 5%)

Metric              Baseline    Current     Delta      Status
Selection           92.0%       78.0%       -14.0%     REGRESSION
Invocation          88.0%       87.2%       -0.8%      OK
```

### Exit Codes

- `0`: PASS - No regression detected
- `1`: FAIL - Regression detected (accuracy dropped beyond threshold)
- `2`: ERROR - Invalid files or other errors

## CI/CD Integration

### GitHub Action

The easiest way to add Toolscore to your CI:

```yaml
name: Agent Evaluation
on: [push, pull_request]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: yotambraun/toolscore@v1
        with:
          gold-file: tests/gold_standard.json
          trace-file: tests/agent_trace.json
          threshold: '0.90'
```

### With Regression Testing

```yaml
- uses: yotambraun/toolscore@v1
  with:
    gold-file: tests/gold_standard.json
    trace-file: tests/agent_trace.json
    baseline-file: tests/baseline.json
    regression-threshold: '0.05'
```

### Manual GitHub Actions Setup

If you need more control:

```yaml
jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Toolscore
        run: pip install tool-scorer

      - name: Run Evaluation
        run: |
          toolscore eval tests/gold.json tests/trace.json \
            --html report.html \
            --save-baseline current_baseline.json

      - name: Run Regression Check
        run: |
          toolscore regression tests/baseline.json tests/trace.json \
            --gold-file tests/gold.json \
            --threshold 0.05

      - name: Upload Report
        uses: actions/upload-artifact@v4
        with:
          name: evaluation-report
          path: report.html
```

### Best Practices

1. **Commit your baseline** - Keep `baseline.json` in version control
2. **Update baseline on releases** - When you intentionally change behavior
3. **Use meaningful thresholds** - 5% is a good default, adjust based on your tolerance
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
        actual=my_agent_output,
        min_score=0.9,
    )
```

Toolscore also includes a pytest plugin with fixtures:

```python
# test_my_agent.py
def test_agent_meets_accuracy_threshold(toolscore_eval, toolscore_assertions):
    """Verify agent achieves minimum accuracy requirements."""
    result = toolscore_eval("gold_calls.json", "trace.json")

    toolscore_assertions.assert_invocation_accuracy(result, min_accuracy=0.9)
    toolscore_assertions.assert_selection_accuracy(result, min_accuracy=0.9)
    toolscore_assertions.assert_argument_f1(result, min_f1=0.8)
    toolscore_assertions.assert_sequence_accuracy(result, min_accuracy=0.8)
```

### Integration Helpers

Extract tool calls directly from LLM provider responses:

```python
from toolscore.integrations import from_openai, from_anthropic, from_gemini

# OpenAI
response = openai_client.chat.completions.create(...)
calls = from_openai(response)

# Anthropic
response = anthropic_client.messages.create(...)
calls = from_anthropic(response)

# Gemini
response = gemini_model.generate_content(...)
calls = from_gemini(response)

# Then evaluate
from toolscore import evaluate
result = evaluate(expected=[...], actual=calls)
```

### Interactive Tutorials

Toolscore includes Jupyter notebooks for hands-on learning:

1. **Quickstart Tutorial** (`examples/notebooks/01_quickstart.ipynb`)
   - 5-minute introduction to Toolscore
   - Load gold standards and traces
   - Run evaluations and interpret metrics
   - Generate HTML/JSON reports

2. **Custom Formats** (`examples/notebooks/02_custom_formats.ipynb`)
   - Work with custom trace formats
   - Create gold standards for custom workflows
   - Best practices for format design

3. **Advanced Metrics** (`examples/notebooks/03_advanced_metrics.ipynb`)
   - Deep dive into each metric
   - Real-world examples and scenarios
   - Metric selection guide
   - Tips for improving scores

Run locally:
```bash
cd examples/notebooks
jupyter notebook
```

Or open in Google Colab for instant experimentation (no installation required!).

### LangChain Support

Toolscore supports LangChain agent traces in both legacy and modern formats:

**Legacy format (AgentAction):**
```python
from langchain.agents import AgentExecutor
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

# Save trace
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
tool-scorer eval gold_calls.json langchain_trace.json --format langchain
# Or use auto-detection
tool-scorer eval gold_calls.json langchain_trace.json --format auto
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

### Programmatic Report Generation

```python
from toolscore.reports import generate_html_report, generate_json_report

# Generate reports programmatically
json_report = generate_json_report(result)
html_report = generate_html_report(result)

# Save to files
with open("report.json", "w") as f:
    f.write(json_report)

with open("report.html", "w") as f:
    f.write(html_report)
```

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

Here's a complete workflow for evaluating a new LLM model:

```bash
# 1. Define your gold standard
cat > gold_standard.json << EOF
[
  {"tool": "search_web", "args": {"query": "Python tutorials"}},
  {"tool": "summarize", "args": {"text": "..."}}
]
EOF

# 2. Capture traces from different models
python capture_openai_trace.py   # GPT-4
python capture_anthropic_trace.py # Claude

# 3. Evaluate both
tool-scorer eval gold_standard.json trace_gpt4.json --html gpt4_report.html
tool-scorer eval gold_standard.json trace_claude.json --html claude_report.html

# 4. Compare results
echo "GPT-4 Results:"
tool-scorer eval gold_standard.json trace_gpt4.json

echo "\nClaude Results:"
tool-scorer eval gold_standard.json trace_claude.json
```

## Next Steps

- Check out more examples in `examples/`
- Read `CONTRIBUTING.md` to contribute new metrics
- Star the repo on GitHub if this helps your project!

## Support

- **Issues:** https://github.com/yourusername/toolscore/issues
- **Discussions:** https://github.com/yourusername/toolscore/discussions

Happy evaluating!
