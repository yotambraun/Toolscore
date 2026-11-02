"""Record tool calls live from agent SDKs, as Toolscore traces.

* :class:`ClaudeAgentSDKRecorder` plugs into the Claude Agent SDK's hooks
  (``PreToolUse``, ``PostToolUse``, ``PostToolUseFailure``) and records every
  tool call with its input, response, error and duration, including MCP tools
  (``mcp__server__tool``) and subagent calls.
* :class:`OpenAIAgentsRecorder` is an OpenAI Agents SDK tracing processor: it
  records every function tool span (function tools and MCP tools) with its
  input, output and error.

Both keep what they recorded in :attr:`calls` (Toolscore call dicts), take the
run's final answer, and write a trace that every Toolscore command reads
(``toolscore eval``, ``toolscore honesty``). Nothing is sent anywhere; the
SDKs stay optional (imported only when a recorder needs them).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from toolscore.metrics.security import redact_secrets


class _Recorder:
    """What both recorders share: calls, final answer, trace file, evaluate."""

    agent = "unknown"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.final_answer: str | None = None
        self.session_id: str | None = None
        self._lock = threading.Lock()

    def to_trace(self, redact: bool = False) -> dict[str, Any]:
        """The recorded run as a Toolscore trace dict.

        Args:
            redact: Replace credentials the secret scanner recognizes with
                redacted previews (for a trace you will share or commit).

        Returns:
            ``{"format": "toolscore", "source", "calls", "final_answer"}``.
        """
        trace: dict[str, Any] = {
            "format": "toolscore",
            "source": {"agent": self.agent, "session_id": self.session_id},
            "calls": [dict(c) for c in self.calls],
            "final_answer": self.final_answer,
        }
        if redact:
            trace = json.loads(redact_secrets(json.dumps(trace, default=str)))
        return trace

    def save(self, path: str | Path, redact: bool = True) -> Path:
        """Write the trace as JSON (credentials redacted unless ``redact=False``).

        Args:
            path: The file to write.
            redact: Replace credentials with redacted previews.

        Returns:
            The path written.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_trace(redact=redact), indent=2, default=str) + "\n", encoding="utf-8"
        )
        return target

    def evaluate(self, expected: Any, **kwargs: Any) -> Any:
        """Evaluate the recorded calls (``toolscore.evaluate`` with the final answer).

        Args:
            expected: The expected calls (as for :func:`toolscore.evaluate`), or a contract mapping.
            **kwargs: Passed to :func:`toolscore.evaluate`.

        Returns:
            The :class:`toolscore.EvaluationResult`.
        """
        from toolscore.contract import evaluate_contract, is_contract
        from toolscore.core import evaluate

        kwargs.setdefault("final_answer", self.final_answer)
        if is_contract(expected):
            return evaluate_contract(expected, self.calls, **kwargs)
        return evaluate(expected=expected, actual=self.calls, **kwargs)


class ClaudeAgentSDKRecorder(_Recorder):
    """Record a Claude Agent SDK run through its tool hooks.

    Example::

        from claude_agent_sdk import ClaudeAgentOptions, query
        from toolscore.recorders import ClaudeAgentSDKRecorder

        recorder = ClaudeAgentSDKRecorder()
        options = ClaudeAgentOptions(hooks=recorder.hooks(), allowed_tools=["Read", "Bash"])
        async for message in query(prompt="Run the tests", options=options):
            recorder.observe(message)       # keeps the final ResultMessage text
        recorder.save("trace.json")         # then: toolscore honesty trace.json

    The hooks return ``{}``: they never block or change a tool call. Merge them
    with your own hooks with ``recorder.hooks(existing)``.
    """

    agent = "claude-agent-sdk"

    def __init__(self) -> None:
        super().__init__()
        self._pending: dict[str, dict[str, Any]] = {}

    def _call(self, data: dict[str, Any], tool_use_id: str | None) -> dict[str, Any]:
        key = str(data.get("tool_use_id") or tool_use_id or len(self.calls))
        with self._lock:
            call = self._pending.get(key)
            if call is None:
                call = {"tool": str(data.get("tool_name") or "unknown"), "args": {}, "id": key}
                tool_input = data.get("tool_input")
                if isinstance(tool_input, dict):
                    call["args"] = dict(tool_input)
                metadata: dict[str, Any] = {}
                for field in ("agent_id", "agent_type"):
                    if data.get(field):
                        metadata[field] = data[field]
                if metadata:
                    call["metadata"] = metadata
                call["timestamp"] = time.time()
                self._pending[key] = call
                self.calls.append(call)
            if data.get("session_id") and self.session_id is None:
                self.session_id = str(data["session_id"])
        return call

    async def pre_tool_use(
        self, input_data: Any, tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """``PreToolUse`` hook: records the call and its input."""
        if isinstance(input_data, dict):
            self._call(input_data, tool_use_id)
        return {}

    async def post_tool_use(
        self, input_data: Any, tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """``PostToolUse`` hook: records the tool's response and duration."""
        if isinstance(input_data, dict):
            call = self._call(input_data, tool_use_id)
            call["result"] = input_data.get("tool_response")
            if isinstance(input_data.get("duration_ms"), (int, float)):
                call["duration"] = input_data["duration_ms"] / 1000
        return {}

    async def post_tool_use_failure(
        self, input_data: Any, tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """``PostToolUseFailure`` hook: records the error."""
        if isinstance(input_data, dict):
            call = self._call(input_data, tool_use_id)
            call["error"] = str(input_data.get("error") or "tool failed")
            if input_data.get("is_interrupt"):
                call.setdefault("metadata", {})["interrupted"] = True
            if isinstance(input_data.get("duration_ms"), (int, float)):
                call["duration"] = input_data["duration_ms"] / 1000
        return {}

    def hooks(self, existing: dict[str, list[Any]] | None = None) -> dict[str, list[Any]]:
        """The hooks to pass as ``ClaudeAgentOptions(hooks=...)``.

        Args:
            existing: Your own hooks mapping; the recorder's matchers are added to it.

        Returns:
            A hooks mapping with a ``HookMatcher`` for every tool on
            ``PreToolUse``, ``PostToolUse`` and ``PostToolUseFailure``.
        """
        from claude_agent_sdk import HookMatcher

        merged: dict[str, list[Any]] = {k: list(v) for k, v in (existing or {}).items()}
        callbacks: tuple[tuple[str, Any], ...] = (
            ("PreToolUse", self.pre_tool_use),
            ("PostToolUse", self.post_tool_use),
            ("PostToolUseFailure", self.post_tool_use_failure),
        )
        for event, callback in callbacks:
            merged.setdefault(event, []).append(HookMatcher(matcher=None, hooks=[callback]))
        return merged

    def observe(self, message: Any) -> None:
        """Pass each message ``query()`` yields; keeps the final answer and session ID."""
        if type(message).__name__ == "ResultMessage":
            text = getattr(message, "result", None)
            if isinstance(text, str) and text.strip():
                self.final_answer = text
            session = getattr(message, "session_id", None)
            if session:
                self.session_id = str(session)


class OpenAIAgentsRecorder(_Recorder):
    """An OpenAI Agents SDK tracing processor that records tool calls.

    Example::

        from agents import Runner, add_trace_processor
        from toolscore.recorders import OpenAIAgentsRecorder

        recorder = OpenAIAgentsRecorder()
        add_trace_processor(recorder)          # alongside the default exporter
        result = await Runner.run(agent, "Book a table for two")
        recorder.final_answer = str(result.final_output)
        recorder.save("trace.json")

    Every ``function`` span (function tools, and MCP tools, which the SDK also
    traces as function spans with ``mcp_data``) becomes a call with its input
    (parsed JSON arguments), output and error. ``trace_id`` restricts
    recording to one trace; :meth:`for_trace` reads the calls of one trace.
    """

    agent = "openai-agents"

    def __init__(self, trace_id: str | None = None) -> None:
        super().__init__()
        self.trace_id = trace_id
        self._by_span: dict[str, dict[str, Any]] = {}

    def _span_kind(self, span: Any) -> str | None:
        data = getattr(span, "span_data", None)
        kind = getattr(data, "type", None)
        return kind if isinstance(kind, str) else None

    def on_trace_start(self, trace: Any) -> None:
        """Tracing processor hook (unused)."""

    def on_trace_end(self, trace: Any) -> None:
        """Tracing processor hook (unused)."""

    def on_span_start(self, span: Any) -> None:
        """Records a tool span's start (tool name, arguments, time)."""
        if self._span_kind(span) != "function":
            return
        if self.trace_id is not None and getattr(span, "trace_id", None) != self.trace_id:
            return
        data = span.span_data
        call: dict[str, Any] = {
            "tool": str(getattr(data, "name", None) or "unknown"),
            "args": _parse_arguments(getattr(data, "input", None)),
            "id": str(getattr(span, "span_id", "")) or None,
            "timestamp": time.time(),
        }
        trace_id = getattr(span, "trace_id", None)
        call["metadata"] = {"trace_id": trace_id} if trace_id else {}
        mcp = getattr(data, "mcp_data", None)
        if mcp:
            call["metadata"]["mcp"] = mcp
        with self._lock:
            self._by_span[str(getattr(span, "span_id", id(span)))] = call
            self.calls.append(call)

    def on_span_end(self, span: Any) -> None:
        """Records a tool span's output, error and duration."""
        if self._span_kind(span) != "function":
            return
        key = str(getattr(span, "span_id", id(span)))
        with self._lock:
            call = self._by_span.get(key)
        if call is None:
            return
        data = span.span_data
        call["args"] = _parse_arguments(getattr(data, "input", None)) or call["args"]
        output = getattr(data, "output", None)
        if output is not None:
            call["result"] = output
        error = getattr(span, "error", None)
        if error:
            message = error.get("message") if isinstance(error, dict) else str(error)
            data_detail = error.get("data") if isinstance(error, dict) else None
            call["error"] = str(message or "tool failed") + (
                f": {data_detail}" if data_detail else ""
            )
        if isinstance(call.get("timestamp"), float):
            call["duration"] = max(0.0, time.time() - call["timestamp"])

    def shutdown(self) -> None:
        """Tracing processor hook (unused)."""

    def force_flush(self) -> None:
        """Tracing processor hook (unused)."""

    def for_trace(self, trace_id: str) -> list[dict[str, Any]]:
        """The recorded calls of one trace."""
        return [c for c in self.calls if (c.get("metadata") or {}).get("trace_id") == trace_id]


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"input": raw}
        return parsed if isinstance(parsed, dict) else {"input": parsed}
    return {}
