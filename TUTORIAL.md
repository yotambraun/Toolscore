# Toolscore Tutorial: Complete Guide

This tutorial walks you through the complete workflow of using Toolscore to evaluate LLM tool usage.

## Table of Contents
1. [Overview](#overview)
2. [Setup](#setup)
3. [Step 1: Capture Tool Usage Traces](#step-1-capture-tool-usage-traces)
4. [Step 2: Create Gold Standards](#step-2-create-gold-standards)
5. [Step 3: Evaluate and Generate Reports](#step-3-evaluate-and-generate-reports)
6. [Understanding the Metrics](#understanding-the-metrics)
7. [Advanced Usage](#advanced-usage)

## Overview

**What is Toolscore?**

Toolscore is an evaluation framework for LLM agents that use tools (function calling). It compares actual tool usage traces against expected behavior (gold standards) and produces detailed metrics.

**What Toolscore does:**
- ✅ Evaluates existing tool usage traces
- ✅ Compares against gold standard specifications
- ✅ Generates detailed metrics and reports

**What Toolscore does NOT do:**
- ❌ Call LLM APIs directly (you capture traces separately)
- ❌ Execute actual tool calls
- ❌ Train or fine-tune models

## Setup

### 1. Install Toolscore

```bash
# Clone the repository
git clone https://github.com/yourusername/toolscore.git
cd toolscore

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"
```

### 2. Set Up API Keys (Optional)

If you plan to capture traces from OpenAI or Anthropic, create a `.env` file:

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

### Python API Usage

Create `evaluate.py`:

```python
#!/usr/bin/env python3
"""Evaluate LLM tool usage."""
from toolscore import evaluate_trace

# Run evaluation
result = evaluate_trace(
    gold_file="my_gold_standard.json",
    trace_file="my_trace_openai.json",
    format="auto"  # auto-detect format
)

# Print summary
print("\n=== Evaluation Results ===")
print(f"Invocation Accuracy: {result.metrics['invocation_accuracy']:.1%}")
print(f"Selection Accuracy: {result.metrics['selection_accuracy']:.1%}")

# Sequence metrics
seq = result.metrics['sequence_metrics']
print(f"Sequence Accuracy: {seq['sequence_accuracy']:.1%}")
print(f"Edit Distance: {seq['edit_distance']}")

# Argument metrics
args = result.metrics['argument_metrics']
print(f"Argument F1 Score: {args['f1']:.1%}")
print(f"Argument Precision: {args['precision']:.1%}")
print(f"Argument Recall: {args['recall']:.1%}")

# Efficiency metrics
eff = result.metrics['efficiency_metrics']
print(f"Redundant Call Rate: {eff['redundant_rate']:.1%}")
print(f"Redundant Calls: {eff['redundant_count']}/{eff['total_calls']}")
```

Run it:
```bash
python evaluate.py
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

## Advanced Usage

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
