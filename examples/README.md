# Toolscore Examples

This directory contains example files demonstrating the usage of Toolscore.

## Files

- **gold_calls.json** - Gold standard specification defining expected tool calls
- **trace_openai.json** - Example trace in OpenAI format
- **trace_anthropic.json** - Example trace in Anthropic/Claude format
- **trace_custom.json** - Example trace in custom/generic format

## Usage

Evaluate an OpenAI trace:
```bash
toolscore eval gold_calls.json trace_openai.json --format openai --html report.html
```

Evaluate an Anthropic trace:
```bash
toolscore eval gold_calls.json trace_anthropic.json --format anthropic
```

Evaluate a custom trace (auto-detect format):
```bash
toolscore eval gold_calls.json trace_custom.json
```

## Python API

You can also use the Python API directly:

```python
from toolscore import evaluate_trace

result = evaluate_trace(
    gold_file="gold_calls.json",
    trace_file="trace_openai.json",
    format="openai"
)

print(f"Invocation Accuracy: {result.metrics['invocation_accuracy']:.2%}")
print(f"Selection Accuracy: {result.metrics['selection_accuracy']:.2%}")
```
