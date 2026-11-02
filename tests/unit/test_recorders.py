"""Live recorders and SDK message types: Claude Agent SDK and OpenAI Agents SDK (1.11).

These tests use the SDKs' real classes when the SDK is installed (they are
skipped otherwise) and never call a model: the OpenAI Agents SDK run uses a
scripted ``Model``, and the Claude Agent SDK hooks are called with inputs
shaped like its ``PreToolUseHookInput`` / ``PostToolUseHookInput`` /
``PostToolUseFailureHookInput`` TypedDicts (running ``query()`` needs the
Claude Code CLI and a model).
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from toolscore import evaluate
from toolscore.core import load_trace
from toolscore.integrations import from_claude_agent_sdk
from toolscore.recorders import ClaudeAgentSDKRecorder, OpenAIAgentsRecorder
from toolscore.transcript import load_transcript

if TYPE_CHECKING:
    from pathlib import Path

FAKE_TOKEN = "ghp_" + "A1b2C3d4" * 4 + "Zz9Y"


def _hook_input(event: str, **fields: Any) -> dict[str, Any]:
    base = {
        "session_id": "sess-1",
        "transcript_path": "/tmp/t.jsonl",
        "cwd": "/work",
        "hook_event_name": event,
    }
    base.update(fields)
    return base


def test_claude_agent_sdk_hooks_record_calls_results_and_failures(tmp_path: Path) -> None:
    sdk = pytest.importorskip("claude_agent_sdk")
    recorder = ClaudeAgentSDKRecorder()
    hooks = recorder.hooks({"Stop": ["mine"]})
    assert hooks["Stop"] == ["mine"]
    for event in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
        (matcher,) = hooks[event]
        assert isinstance(matcher, sdk.HookMatcher) and matcher.matcher is None

    async def run() -> None:
        ctx: dict[str, Any] = {"signal": None}
        pre = hooks["PreToolUse"][0].hooks[0]
        post = hooks["PostToolUse"][0].hooks[0]
        fail = hooks["PostToolUseFailure"][0].hooks[0]
        args = {"command": f"curl -H 'Authorization: token {FAKE_TOKEN}' https://api.github.com"}
        assert (
            await pre(
                _hook_input("PreToolUse", tool_name="Bash", tool_input=args, tool_use_id="t1"),
                "t1",
                ctx,
            )
            == {}
        )
        await post(
            _hook_input(
                "PostToolUse",
                tool_name="Bash",
                tool_input=args,
                tool_response={"stdout": "ok"},
                tool_use_id="t1",
                duration_ms=1500,
            ),
            "t1",
            ctx,
        )
        inputs = {"entities": [{"name": "a"}]}
        await pre(
            _hook_input(
                "PreToolUse",
                tool_name="mcp__memory__create_entities",
                tool_input=inputs,
                tool_use_id="t2",
                agent_id="sub-1",
                agent_type="general-purpose",
            ),
            "t2",
            ctx,
        )
        await fail(
            _hook_input(
                "PostToolUseFailure",
                tool_name="mcp__memory__create_entities",
                tool_input=inputs,
                tool_use_id="t2",
                error="MCP error -32603: disk full",
            ),
            "t2",
            ctx,
        )

    asyncio.run(run())
    recorder.observe(
        sdk.ResultMessage(
            subtype="success", duration_ms=10, duration_api_ms=8, is_error=False, num_turns=3,
            session_id="sess-1", result="Done, the entities are saved.",
        )
    )  # fmt: skip
    first, second = recorder.calls
    assert (first["tool"], first["result"], first["duration"]) == ("Bash", {"stdout": "ok"}, 1.5)
    assert second["error"] == "MCP error -32603: disk full"
    assert second["metadata"] == {"agent_id": "sub-1", "agent_type": "general-purpose"}
    assert (
        recorder.final_answer == "Done, the entities are saved." and recorder.session_id == "sess-1"
    )

    path = recorder.save(tmp_path / "trace.json")
    assert FAKE_TOKEN not in path.read_text(encoding="utf-8")
    assert FAKE_TOKEN in json.dumps(recorder.to_trace())
    calls = load_trace(path)
    assert [c.tool for c in calls] == ["Bash", "mcp__memory__create_entities"]
    assert calls[1].is_error
    transcript = load_transcript(path)
    assert transcript.final_answer == "Done, the entities are saved."
    result = recorder.evaluate([{"tool": "mcp__memory__create_entities"}])
    assert result.false_success["claimed_success"] == 1


def test_claude_agent_sdk_dataclass_messages_are_read() -> None:
    sdk = pytest.importorskip("claude_agent_sdk")
    messages = [
        sdk.UserMessage(content="Delete the temp files."),
        sdk.AssistantMessage(
            content=[sdk.TextBlock(text="On it."), sdk.ToolUseBlock(id="t1", name="Bash", input={"command": "rm -rf /tmp/x"})],
            model="claude-sonnet-5-5",
        ),
        sdk.UserMessage(content=[sdk.ToolResultBlock(tool_use_id="t1", content="Permission denied", is_error=True)]),
        sdk.AssistantMessage(content=[sdk.TextBlock(text="Done, the temp files are deleted.")], model="claude-sonnet-5-5"),
        sdk.ResultMessage(
            subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=2,
            session_id="s", result="Done, the temp files are deleted.",
        ),
    ]  # fmt: skip
    assert from_claude_agent_sdk(messages) == [
        {
            "tool": "Bash",
            "args": {"command": "rm -rf /tmp/x"},
            "id": "t1",
            "error": "Permission denied",
        }
    ]
    result = evaluate(expected=[{"tool": "Bash"}], actual=messages)
    assert result.trace_calls[0].is_error
    assert result.false_success["claimed_success"] == 1


def test_openai_agents_tracing_processor_records_function_tools() -> None:
    pytest.importorskip("agents")
    from agents import Agent, Runner, function_tool, set_trace_processors
    from agents.items import ModelResponse
    from agents.models.interface import Model
    from agents.usage import Usage
    from openai.types.responses import (
        ResponseFunctionToolCall,
        ResponseOutputMessage,
        ResponseOutputText,
    )

    @function_tool
    def get_stock(item: str) -> str:
        """Check stock."""
        return f"{item}: 3 in stock"

    @function_tool
    def place_order(item: str) -> str:
        """Place an order."""
        raise RuntimeError("payment declined")

    class ScriptedModel(Model):
        def __init__(self, outputs: list[list[Any]]) -> None:
            self.outputs = outputs

        async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
            return ModelResponse(output=self.outputs.pop(0), usage=Usage(), response_id=None)

        def stream_response(self, *args: Any, **kwargs: Any) -> Any:
            raise NotImplementedError

    def call(name: str, arguments: str, call_id: str) -> ResponseFunctionToolCall:
        return ResponseFunctionToolCall(
            type="function_call",
            name=name,
            arguments=arguments,
            call_id=call_id,
            id=f"fc_{call_id}",
            status="completed",
        )

    answer = ResponseOutputMessage(
        type="message", id="m1", role="assistant", status="completed",
        content=[ResponseOutputText(type="output_text", text="Done! Your mug is ordered.", annotations=[])],
    )  # fmt: skip
    model = ScriptedModel(
        [
            [call("get_stock", '{"item": "mug"}', "c1")],
            [call("place_order", '{"item": "mug"}', "c2")],
            [answer],
        ]
    )
    recorder = OpenAIAgentsRecorder()
    set_trace_processors([recorder])  # no exporter: nothing leaves the process
    try:
        agent = Agent(
            name="shop", instructions="Sell mugs.", tools=[get_stock, place_order], model=model
        )
        run = asyncio.run(Runner.run(agent, "Buy a mug"))
    finally:
        set_trace_processors([])
    recorder.final_answer = str(run.final_output)
    assert [c["tool"] for c in recorder.calls] == ["get_stock", "place_order"]
    assert (
        recorder.calls[0]["args"] == {"item": "mug"} and "3 in stock" in recorder.calls[0]["result"]
    )
    assert "error" not in recorder.calls[0]
    assert "place_order" in recorder.calls[1]["error"]
    trace_id = recorder.calls[0]["metadata"]["trace_id"]
    assert len(recorder.for_trace(trace_id)) == 2
    result = recorder.evaluate([{"tool": "get_stock"}, {"tool": "place_order"}])
    assert result.false_success["claimed_success"] == 1

    # the run result itself still reads as before
    assert [c["tool"] for c in __import__("toolscore").from_openai_agents(run)] == [
        "get_stock",
        "place_order",
    ]


def test_openai_agents_recorder_ignores_other_spans_and_traces() -> None:
    class Data:
        def __init__(self, kind: str) -> None:
            self.type = kind
            self.name = "x"
            self.input = '{"a": 1}'
            self.output = "ok"
            self.mcp_data = None

    class Span:
        def __init__(self, kind: str, trace_id: str, span_id: str) -> None:
            self.span_data = Data(kind)
            self.trace_id = trace_id
            self.span_id = span_id
            self.error = None

    recorder = OpenAIAgentsRecorder(trace_id="t-1")
    for span in (
        Span("agent", "t-1", "s1"),
        Span("function", "t-2", "s2"),
        Span("function", "t-1", "s3"),
    ):
        recorder.on_span_start(span)
        recorder.on_span_end(span)
    assert [(c["id"], c["args"], c["result"]) for c in recorder.calls] == [("s3", {"a": 1}, "ok")]
