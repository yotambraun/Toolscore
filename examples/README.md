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
- **mcp_scorecard_demo.py** - run the MCP scorecard harness (scenarios, lint, output-schema checks) against the bundled fake MCP server and print an A–F scorecard with the protocol it used
- **test_example_with_pytest.py** - example pytest suite using the Toolscore plugin and fixtures

### Guardrails (behavior and safety checks)
- **guardrails/** - a deploy agent's trace with a destructive shell command, a credential posted to a webhook and a failed deploy retried unchanged, plus `forbidden.json` rules. Run:

```bash
toolscore eval examples/guardrails/gold.json examples/guardrails/trace.json \
    --forbidden examples/guardrails/forbidden.json --fail-on-violations
```

The credential is AWS's documented example key (`AKIAIOSFODNN7EXAMPLE`), not a real secret.

### Truth checks (did the tool really do it, did the agent tell the truth)
- **probes/** - a probe config for the bundled sample server, as YAML and JSON (a declared round trip, a bound and a two-path agreement). Try it against a deliberately buggy server:

```bash
toolscore mcp test "python -m toolscore.mcp.sample_server --bug limit-ignored" \
    --probe-config examples/probes/notes-probes.yaml --allow-writes
```

  The sample server's other bug modes: `--bug silent-skip` (a same-title write reports success and changes nothing) and `--bug lose-on-write` (a new note replaces the stored ones).
- **mcp_memory_probes/** - the effect probes on the official MCP memory server before (`2026.8.31`) and after (`2.0.1`) the #4887 fix, with the exact commands and console output (needs Node.js).
- **mcp_filesystem_probes/** - `--arg` values and the built-in `head`/`tail` bounds on the official filesystem server (`2.1.0`), with outputs and a declared `probes.json`.
- **honesty/** - hand-written traces for the honesty checks: a JavaScript escape hatch after a disabled button (OpenAI format), an ignored warning, and the same run answered honestly (Anthropic format). Run `toolscore honesty examples/honesty/disabled_button.json`.
- **browser_use/** - browser-use agent histories in the 0.13.14 layout: the #6068 disabled-button bypass (a refused click, and the silent click the issue logs) and an honest run. Run `toolscore honesty examples/browser_use/order_click_refused.json`.
- **coding_sessions/** - synthetic Claude Code and Codex CLI sessions in which the agent reports success after a failing test or lint run: `toolscore honesty examples/coding_sessions/codex-rollout.jsonl`, `toolscore sessions list`, and `toolscore sessions export` for a redacted trace.
- **fault_injection/** - `faults.json` and `scripted_agent.py`, which runs a scripted agent behind `toolscore mcp proxy --inject` and checks its report (`python examples/fault_injection/scripted_agent.py`, offline).

Run any of them with:

```bash
uv run python examples/<file>.py     # or: python examples/<file>.py
```

### Rigor: agents, pinning, contracts, receipts and runs
- **agent_harness/** - `toolscore agent run` on an offline spec (scripted provider, a guard that refuses deletes, two arms), then `toolscore compare --runs` with a pre-declared `protocol.yaml`, `toolscore select`, `toolscore export --format aef` and `toolscore doctor`, all with real output; plus `memory-anthropic.yaml`, a real-model spec that **costs money** (not run).
- **pinning/** - `toolscore mcp pin` / `verify-pin` catching a poisoned description and a new shell tool (offline), and the official memory server's `2026.8.31` vs `2.0.1` with `mcp verify-pin` and `mcp diff` (needs Node.js).
- **contracts/** - a contract with an optional call, a forbidden call and alternatives, against the gold file it replaces, and `toolscore regrade` of a receipt (offline).

### GitHub Actions
- **github_actions/** - workflows for evaluation, regression, quality gates, and `mcp-badge.yml`, which keeps an "MCP grade" badge in your README current

### Capture Scripts (Generate Your Own Traces)
- **capture_openai_trace.py** - capture a trace with the OpenAI Responses API (`gpt-6-luna`) and save the response as it is
- **capture_anthropic_trace.py** - capture a trace with the Anthropic Messages API (`claude-haiku-5-5`)
- **requirements.txt** - Dependencies for running capture scripts

## Quick Start

### Try it in 10 seconds

```bash
# Grade a bundled sample MCP server — no install, no API key:
toolscore demo
```

You get an A–F grade, a per-tool token-cost estimate, and a ranked **"Top issues to fix"** list. Point it at your own server with `toolscore mcp test "python my_server.py"`, or at a remote one with `toolscore mcp test https://mcp.example.com/mcp --auth-env MCP_TOKEN` (needs `pip install "tool-scorer[http]"`). Add `--badge mcp-grade.svg` for a README badge with the grade.

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
   tool-scorer eval gold_calls.json my_trace_openai.json   # the Responses API format is auto-detected
   ```

## Python API

You can also use the Python API directly:

```python
from toolscore import evaluate_trace

result = evaluate_trace(
    gold_file="gold_calls.json", trace_file="trace_openai.json", format="openai"
)

print(f"Invocation Accuracy: {result.metrics['invocation_accuracy']:.2%}")
print(f"Selection Accuracy: {result.metrics['selection_accuracy']:.2%}")
```

## Next Steps

- Read the [Complete Tutorial](../TUTORIAL.md) for an in-depth guide
- Modify the capture scripts to test your own tasks
- Create custom gold standards for your use cases
