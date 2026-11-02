"""What an agent said at the end of a run, next to the calls it made.

Tool-call metrics need only the calls. The honesty checks
(:mod:`toolscore.metrics.honesty`) also need the agent's **final answer**, the
text it gave the user, to see whether it claimed success after a failure or
kept a warning to itself. :func:`final_answer_of` finds that text in every
trace format Toolscore reads; :func:`load_transcript` returns it with the calls.

Where the final answer comes from:

* a top-level ``final_answer``, ``final_output`` or ``output_text`` string
  (any trace file, including recorded MCP sessions, which hold no answer of
  their own);
* OpenAI Chat Completions and Anthropic Messages histories: the last assistant
  message, when it calls no tool;
* OpenAI Responses items: the last assistant ``message`` after the last call;
* LangChain/LangGraph message dicts (``type: "ai"``) without tool calls;
* Claude Agent SDK / ``claude -p --output-format json`` results
  (``{"type": "result", "result": ...}``);
* OpenTelemetry spans with ``gen_ai.output.messages``;
* Claude Code and Codex CLI sessions (JSON Lines): the main agent's last
  assistant message after its last tool call;
* browser-use histories: the ``done`` action's text (the last result with
  ``is_done: true``), whose ``success`` flag is kept as
  :attr:`Transcript.success`;
* otherwise a final "done" tool call (``done``, ``finish``, ``final_answer``...)
  with a ``text``/``message``/``answer``/``summary`` argument.

When none of these is present, the final answer is unknown (``None``), and
checks that need it report "unknown" rather than pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from toolscore.adapters.anthropic import block_text
from toolscore.adapters.openai import message_text

if TYPE_CHECKING:
    from toolscore.adapters.base import ToolCall

#: Top-level string fields that hold a run's final answer.
FINAL_ANSWER_KEYS = ("final_answer", "final_output", "output_text")

#: Tool names (normalized) an agent calls to finish a run.
DONE_TOOLS = frozenset(
    {
        "done", "finish", "final_answer", "submit_final_answer", "complete_task",
        "task_complete", "attempt_completion", "respond_to_user",
    }
)  # fmt: skip
#: Arguments of a done tool that hold the answer.
_DONE_TEXT_ARGS = ("text", "message", "answer", "result", "summary", "output", "response")

_CALL_TYPES = frozenset({"function_call", "mcp_call", "custom_tool_call"})


@dataclass
class Transcript:
    """The calls of a run and what the agent said at the end.

    Attributes:
        calls: The tool calls, in order.
        final_answer: The agent's final answer, or ``None`` when the trace has none.
        final_source: Where the final answer was found (for reports), or ``None``.
        injections: Faults injected by ``toolscore mcp proxy --inject`` (from a
            proxy session file); empty otherwise.
        success: The agent's own verdict on the run, when the trace records
            one (browser-use's ``done`` ``success``); ``None`` otherwise.
    """

    calls: list[ToolCall]
    final_answer: str | None = None
    final_source: str | None = None
    injections: list[dict[str, Any]] = field(default_factory=list)
    success: bool | None = None


def normalize_tool_name(name: str) -> str:
    """A tool name without host prefixes: ``mcp__browser__click`` -> ``click``.

    Claude Code names MCP tools ``mcp__<server>__<tool>``, and some hosts write
    ``functions.<tool>`` or ``<server>.<tool>``.
    """
    lowered = name.strip()
    if lowered.startswith("mcp__"):
        lowered = lowered.split("__", 2)[-1]
    if lowered.startswith("functions."):
        lowered = lowered[len("functions.") :]
    return lowered.lower()


def _text_or_none(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _from_fields(data: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in FINAL_ANSWER_KEYS:
        text = _text_or_none(data.get(key))
        if text is not None:
            return text, f"trace field {key!r}"
    if data.get("type") == "result":
        text = _text_or_none(data.get("result"))
        if text is not None:
            return text, "agent result message"
    return None, None


def _from_responses(items: list[Any]) -> tuple[str | None, str | None]:
    last_call = max((i for i, it in enumerate(items) if _type(it) in _CALL_TYPES), default=-1)
    for item in reversed(items[last_call + 1 :]):
        if (
            isinstance(item, dict)
            and item.get("type") == "message"
            and item.get("role")
            in (
                "assistant",
                None,
            )
        ):
            text = _text_or_none(block_text(item.get("content")))
            if text is not None:
                return text, "assistant message"
    return None, None


def _type(item: Any) -> Any:
    return item.get("type") if isinstance(item, dict) else None


def _from_messages(messages: list[Any]) -> tuple[str | None, str | None]:
    """The last assistant message of a chat history, when it calls no tool."""
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        if message.get("type") == "result":
            return _from_fields(message)
        role = message.get("role") or message.get("type")
        if role in ("tool", "function", "user", "human", "system", "ToolMessage"):
            return None, None
        if role not in ("assistant", "ai", "AIMessage", "AIMessageChunk", "model"):
            continue
        if message.get("tool_calls") or message.get("function_call"):
            return None, None
        content = message.get("content")
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_use" for b in content
        ):
            return None, None
        text = _text_or_none(message_text(content) if isinstance(content, list) else content)
        if text is not None:
            return text, "assistant message"
        return None, None
    return None, None


def _from_otel(data: Any) -> tuple[str | None, str | None]:
    from toolscore.adapters.otel import _attributes, _nanos, _spans, is_tool_span

    best: tuple[int, str] | None = None
    for span in _spans(data):
        if is_tool_span(span):
            continue
        raw = _attributes(span).get("gen_ai.output.messages")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                continue
        if not isinstance(raw, list):
            continue
        texts = [
            str(part.get("content", ""))
            for message in raw
            if isinstance(message, dict) and message.get("role") in ("assistant", None)
            for part in message.get("parts", []) or []
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        text = "\n".join(t for t in texts if t).strip()
        if text:
            end = _nanos(span, "endTimeUnixNano", "end_time") or 0
            if best is None or end >= best[0]:
                best = (end, text)
    return (best[1], "OpenTelemetry gen_ai.output.messages") if best else (None, None)


def _from_done_call(calls: list[ToolCall]) -> tuple[str | None, str | None]:
    if not calls or normalize_tool_name(calls[-1].tool) not in DONE_TOOLS:
        return None, None
    args = calls[-1].args or {}
    for key in _DONE_TEXT_ARGS:
        text = _text_or_none(args.get(key))
        if text is not None:
            return text, f"{calls[-1].tool} call"
    return None, None


def final_answer_of(
    data: Any, calls: list[ToolCall] | None = None
) -> tuple[str | None, str | None]:
    """Find the agent's final answer in a trace (see the module docstring).

    Args:
        data: The parsed trace (any supported format).
        calls: The trace's calls, for the "done tool" fallback.

    Returns:
        ``(final answer, where it was found)``, or ``(None, None)`` when the
        trace holds no final answer.
    """
    from toolscore.adapters.browser_use import browser_use_final, looks_like_browser_use
    from toolscore.adapters.sessions import (
        claude_code_messages,
        codex_items,
        looks_like_claude_code,
        looks_like_codex,
    )

    found: tuple[str | None, str | None]
    if looks_like_codex(data):
        found = _from_responses(codex_items(data))
        found = (found[0], "Codex session") if found[0] else found
    elif looks_like_claude_code(data):
        found = _from_messages(claude_code_messages(data))
        found = (found[0], "Claude Code session") if found[0] else found
    elif looks_like_browser_use(data):
        text = browser_use_final(data)[0]
        found = (text, "browser-use done result") if text else (None, None)
    elif isinstance(data, dict):
        found = _from_fields(data)
        if found[0] is None:
            from toolscore.adapters.otel import looks_like_otel

            if looks_like_otel(data):
                found = _from_otel(data)
            elif isinstance(data.get("output"), list):
                found = _from_responses(data["output"])
            elif isinstance(data.get("messages"), list) and data.get("format") != "mcp":
                found = _from_messages(data["messages"])
            elif isinstance(data.get("choices"), list) and data["choices"]:
                choice = data["choices"][0]
                message = choice.get("message") if isinstance(choice, dict) else None
                found = _from_messages([message]) if isinstance(message, dict) else (None, None)
            elif data.get("role") == "assistant":
                found = _from_messages([data])
    elif isinstance(data, list):
        from toolscore.adapters.otel import looks_like_otel

        if looks_like_otel(data):
            found = _from_otel(data)
        elif any(_type(i) in _CALL_TYPES for i in data):
            found = _from_responses(data)
        else:
            found = _from_messages(data)
    else:
        found = (None, None)
    if found[0] is None and calls:
        found = _from_done_call(calls)
    return found


def agent_success_of(data: Any) -> bool | None:
    """The agent's own success flag, when the trace records one (browser-use ``done``)."""
    from toolscore.adapters.browser_use import browser_use_final, looks_like_browser_use

    return browser_use_final(data)[1] if looks_like_browser_use(data) else None


def transcript_from_data(
    data: Any,
    format: str = "auto",
    final_answer: str | None = None,
) -> Transcript:
    """Build a :class:`Transcript` from parsed trace data.

    Args:
        data: The parsed trace.
        format: The trace format, as for :func:`toolscore.core.load_trace`.
        final_answer: The final answer, when you have it from elsewhere (it
            wins over anything found in the trace).

    Returns:
        The transcript.
    """
    from toolscore.core import adapter_for

    calls = adapter_for(data, format).parse(data)
    text: str | None
    source: str | None
    if final_answer is not None and final_answer.strip():
        text, source = final_answer.strip(), "provided"
    else:
        text, source = final_answer_of(data, calls)
    injections = data.get("injections") if isinstance(data, dict) else None
    return Transcript(
        calls=calls,
        final_answer=text,
        final_source=source,
        injections=[i for i in injections if isinstance(i, dict)]
        if isinstance(injections, list)
        else [],
        success=agent_success_of(data),
    )


def load_transcript(
    file_path: str | Path, format: str = "auto", final_answer: str | None = None
) -> Transcript:
    """Load a trace file as a :class:`Transcript` (calls, final answer, injected faults).

    Args:
        file_path: The trace file.
        format: The trace format (``"auto"`` detects it).
        final_answer: The final answer, if the trace does not hold it.

    Returns:
        The transcript.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the format is not supported.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Trace file not found: {file_path}")
    from toolscore.core import read_trace_data

    data = read_trace_data(path)
    return transcript_from_data(data, format=format, final_answer=final_answer)
