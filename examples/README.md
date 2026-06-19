# Toolscore Examples

This directory contains example files and scripts demonstrating the usage of Toolscore.

## Files

### Example Traces (Pre-captured)
- **gold_calls.json** - Gold standard specification defining expected tool calls
- **trace_openai.json** - Example trace in OpenAI format
- **trace_anthropic.json** - Example trace in Anthropic/Claude format
- **trace_custom.json** - Example trace in custom/generic format

### Runnable Scripts (no API keys required)
- **evaluate_in_memory.py** - `evaluate()`, `assert_tools()`, `test_agent()`, integrations, and custom weights on mock data
- **langgraph_quickstart.py** - evaluate a LangGraph-shaped agent result (self-contained; runs without langgraph installed)
- **pydantic_ai_quickstart.py** - evaluate a Pydantic AI-shaped agent result (self-contained; runs without pydantic-ai installed)
- **mcp_scorecard_demo.py** - run the MCP scorecard harness against the bundled fake MCP server and print an A–F scorecard
- **test_example_with_pytest.py** - example pytest suite using the Toolscore plugin and fixtures

Run any of them with:

```bash
uv run python examples/<file>.py     # or: python examples/<file>.py
```

### Capture Scripts (Generate Your Own Traces)
- **capture_openai_trace.py** - Script to capture traces from OpenAI API
- **capture_anthropic_trace.py** - Script to capture traces from Anthropic API
- **requirements.txt** - Dependencies for running capture scripts

## Quick Start

### Try it in 10 seconds

```bash
# Grade a bundled sample MCP server — no install, no API key:
toolscore demo
```

You get an A–F grade, a per-tool token-cost estimate, and a ranked **"Top issues to fix"** list. Point it at your own server with `toolscore mcp test "python my_server.py"`.

### Test your agent's tool-calling

```bash
# Compare a recorded trace against a gold spec — prints a grade + "Top issues to fix":
toolscore eval gold_calls.json trace.json
```

### Regression testing

```bash
# Save a baseline from your best evaluation
toolscore eval gold_calls.json trace.json --save-baseline baseline.json

# Run regression checks in CI
toolscore regression baseline.json new_trace.json --gold-file gold_calls.json
```

### Generate Your Own Tests

Use the synthetic test generator to create gold standards from OpenAI function schemas:

```bash
# Generate 10 test cases from your OpenAI function schema
toolscore generate my_functions.json --count 10 --output gold_calls.json

# Or use interactive setup
toolscore init
```

### Option 1: Use Pre-captured Examples

Evaluate an OpenAI trace:
```bash
tool-scorer eval gold_calls.json trace_openai.json --format openai --html report.html
```

Evaluate an Anthropic trace:
```bash
tool-scorer eval gold_calls.json trace_anthropic.json --format anthropic
```

Evaluate a custom trace (auto-detect format):
```bash
tool-scorer eval gold_calls.json trace_custom.json
```

### Option 2: Capture Your Own Traces

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up API keys** (create `.env` in project root):
   ```bash
   echo "OPENAI_API_KEY=your-key-here" > ../.env
   echo "ANTHROPIC_API_KEY=your-key-here" >> ../.env
   ```

3. **Capture a trace:**
   ```bash
   # For OpenAI
   python capture_openai_trace.py

   # For Anthropic
   python capture_anthropic_trace.py
   ```

4. **Evaluate your trace:**
   ```bash
   tool-scorer eval gold_calls.json my_trace_openai.json --format openai
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

## Next Steps

- Read the [Complete Tutorial](../TUTORIAL.md) for an in-depth guide
- Modify the capture scripts to test your own tasks
- Create custom gold standards for your use cases
