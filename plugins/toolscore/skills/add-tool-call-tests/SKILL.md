---
name: add-tool-call-tests
description: Add deterministic tool-call regression tests for an LLM agent with Toolscore - capture what the agent really calls (an MCP session recording, a provider response, a framework run result or a trace file), write a contract of required, optional and forbidden calls, and add a pytest test that fails when the agent's tool calls drift. Use when someone wants to test their agent's tool calling, add evals to CI, lock in agent behavior, or catch an agent calling the wrong tool, with wrong arguments, or a dangerous one.
when_to_use: Trigger phrases include "test my agent's tool calls", "add agent tests", "regression test for my agent", "assert the agent calls", "evals in CI for tool use", "snapshot my agent".
argument-hint: "[agent entry point or trace file]"
---

# Add tool-call tests

Toolscore is deterministic and free per run: the tests compare tool calls, they
do not call a model. Only capturing a new trace runs the agent (and may cost the
user money); ask before running an agent that uses a paid API.

## 0. Toolscore

`pip install tool-scorer` into the project's test dependencies (or check it is
there: `toolscore --version`, 1.11 or later). Snapshot tests need nothing else;
`toolscore init` detects LangGraph, Pydantic AI, OpenAI Agents SDK, CrewAI,
Claude Agent SDK, OpenAI and Anthropic projects and scaffolds a passing suite.

## 1. Get a real trace

Pick the source that matches the project:

- **The agent uses MCP servers**: put `toolscore mcp record -o session.json --`
  in front of the server command in the client's MCP config, run the task once,
  and use `session.json`.
- **Python agent code**: the raw response or run result is the trace. Toolscore
  auto-detects OpenAI Chat Completions and Responses, Anthropic, Gemini,
  LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK and CrewAI
  objects, so the test can pass them to `evaluate()` directly.
- **An existing trace file** (OpenTelemetry GenAI spans, a JSON chat history):
  check it reads with `toolscore validate trace.json`.

Show the user the calls the trace holds before writing expectations from them.

## 2. Write the contract

Ask what the task must do, may do and must never do, then write
`tests/contracts/<task>.json`:

```json
{
  "contract_version": 2,
  "description": "Book a flight to Lisbon. Checking the weather is fine; cancelling is not.",
  "required": [
    {"tool": "search_flights", "args": {"destination": "LIS"}},
    {"tool": "book_flight", "args": {"flight_id": {"$regex": "^FL-\\d+$"}}}
  ],
  "optional": [{"tool": "get_weather"}],
  "forbidden": [{"tool": "cancel_booking", "reason": "never cancel an existing booking"}],
  "min_score": 0.9
}
```

Use matchers (`$regex`, `$contains`, `$one_of`, `$any`, `$type`, `$approx`)
for arguments that legitimately vary, instead of copying values from one run.
Alternatives (`"alternatives": [[...], [...]]`) cover tasks with more than one
correct path. Check it against the trace:

```bash
toolscore eval tests/contracts/book.json session.json
```

## 3. Add the pytest test

```python
from toolscore import evaluate_trace


def test_books_a_flight() -> None:
    result = evaluate_trace("tests/contracts/book.json", "tests/traces/book.json")
    assert result.score >= 0.9, result.score
    assert not result.policy_violations
```

For a live agent, pass its response to `evaluate()` or use the fluent API:

```python
from toolscore import Regex, expect

expect(agent).on("book me a flight to Lisbon") \
    .calls("search_flights", destination="LIS") \
    .then_calls("book_flight", flight_id=Regex(r"FL-\d+")) \
    .does_not_call("cancel_booking") \
    .run()
```

Or record the behavior once and replay it with the bundled snapshot fixture:
`def test_x(toolscore_snapshot): toolscore_snapshot(agent(prompt))`, then
`toolscore approve --all` after reviewing `toolscore snapshots show NAME`.

## 4. Run and wire into CI

Run `pytest` and show the result. For CI, the tests run as part of the existing
pytest job; for a trace file checked in to the repository the GitHub Action
also works:

```yaml
- uses: yotambraun/toolscore@v1
  with:
    gold-file: tests/contracts/book.json
    trace-file: tests/traces/book.json
    threshold: '0.90'
    fail-on-honesty: 'true'
```

Guides: https://yotambraun.github.io/Toolscore/docs/contracts.html and
https://yotambraun.github.io/Toolscore/docs/snapshot_testing.html

$ARGUMENTS
