"""Coding-agent session adapters: Claude Code transcripts and Codex CLI rollouts.

Both agents keep each session as a JSON Lines file on the user's machine.
Toolscore reads them in place (read-only), so the honesty checks and
``toolscore eval`` can look at what a coding agent really did.

**Claude Code** writes ``~/.claude/projects/<project>/<session-id>.jsonl``
(``$CLAUDE_CONFIG_DIR/projects`` when that is set). Each line is one event::

    {"type": "assistant", "uuid": "...", "parentUuid": "...", "sessionId": "...",
     "cwd": "/home/me/app", "timestamp": "2026-11-01T09:12:03.120Z", "isSidechain": false,
     "message": {"role": "assistant", "content": [
         {"type": "tool_use", "id": "toolu_01", "name": "Bash", "input": {"command": "pytest"}}]}}
    {"type": "user", ..., "message": {"role": "user", "content": [
         {"type": "tool_result", "tool_use_id": "toolu_01", "content": "...", "is_error": true}]}}

``message`` is an Anthropic Messages API message, so the calls are its
``tool_use`` blocks, paired with the ``tool_result`` blocks by ID (an
``is_error: true`` result makes the call failed). Lines of other types
(``summary``, ``system``, file snapshots) and ``isMeta`` lines are skipped.
Sidechain lines (``isSidechain: true``, the work of subagents) are skipped too:
the session's final answer is the main agent's, so the honesty checks judge
the main thread's calls against it.

**Codex CLI** writes ``~/.codex/sessions/YYYY/MM/DD/rollout-<time>-<id>.jsonl``
(``$CODEX_HOME/sessions`` when that is set). Each line is
``{"timestamp": ..., "type": ..., "payload": ...}``; ``session_meta`` lines hold
the session ID and ``cwd``, and ``response_item`` lines hold OpenAI Responses
API items: ``message``, ``function_call`` (``name``, JSON ``arguments``,
``call_id``), ``function_call_output`` (``call_id``, ``output``),
``custom_tool_call`` / ``custom_tool_call_output`` and ``local_shell_call``.
Verified against ``codex-rs`` (``history/src/rollout_payload.rs``,
``protocol/src/models.rs``) at openai/codex commit a098129 (2026-11-02).
Compressed ``.jsonl.zst`` rollouts are not read.

A Codex tool output carries no error flag in the file, so a shell call counts
as failed only when its output says the command exited non-zero
(``Exit code: 1``, ``Process exited with code 1``, or a JSON output whose
``metadata.exit_code`` is not 0).
"""

from __future__ import annotations

import json
import re
from typing import Any

from toolscore.adapters.anthropic import AnthropicAdapter
from toolscore.adapters.base import BaseAdapter, ToolCall

#: Claude Code line types that carry a conversation message.
_CLAUDE_MESSAGE_TYPES = frozenset({"user", "assistant"})
#: Codex rollout line types.
_CODEX_LINE_TYPES = frozenset(
    {"session_meta", "response_item", "event_msg", "turn_context", "compacted"}
)

_EXIT_TEXT = re.compile(
    r"^(?:Exit code:|Process exited with code)\s*(-?\d+)", re.IGNORECASE | re.MULTILINE
)


def _records(data: Any) -> list[dict[str, Any]] | None:
    if not isinstance(data, list) or not data:
        return None
    records = [r for r in data if isinstance(r, dict)]
    return records or None


def looks_like_claude_code(data: Any) -> bool:
    """Whether ``data`` (the parsed lines of a JSONL file) is a Claude Code session."""
    records = _records(data)
    if records is None:
        return False
    return any(
        r.get("type") in _CLAUDE_MESSAGE_TYPES
        and isinstance(r.get("message"), dict)
        and ("sessionId" in r or "uuid" in r)
        for r in records
    )


def looks_like_codex(data: Any) -> bool:
    """Whether ``data`` (the parsed lines of a JSONL file) is a Codex CLI rollout."""
    records = _records(data)
    if records is None:
        return False
    return any(
        r.get("type") in _CODEX_LINE_TYPES and isinstance(r.get("payload"), dict) for r in records
    ) and any(r.get("type") == "response_item" for r in records)


def claude_code_messages(data: Any, sidechains: bool = False) -> list[dict[str, Any]]:
    """The Anthropic-style messages of a Claude Code session, in order.

    Args:
        data: The parsed lines of the session file.
        sidechains: Also keep subagent (``isSidechain``) lines.

    Returns:
        The ``message`` dicts of the user and assistant lines.
    """
    messages: list[dict[str, Any]] = []
    for record in _records(data) or []:
        if record.get("type") not in _CLAUDE_MESSAGE_TYPES or record.get("isMeta"):
            continue
        if record.get("isSidechain") and not sidechains:
            continue
        message = record.get("message")
        if isinstance(message, dict):
            messages.append(message)
    return messages


def codex_items(data: Any) -> list[dict[str, Any]]:
    """The Responses API items (``response_item`` payloads) of a Codex rollout, in order."""
    return [
        r["payload"]
        for r in _records(data) or []
        if r.get("type") == "response_item" and isinstance(r.get("payload"), dict)
    ]


def session_meta(data: Any) -> dict[str, Any]:
    """Session ID, working directory, start time and agent of a session's lines."""
    records = _records(data) or []
    if looks_like_codex(data):
        for record in records:
            if record.get("type") == "session_meta" and isinstance(record.get("payload"), dict):
                payload = record["payload"]
                return {
                    "agent": "codex",
                    "session_id": payload.get("id") or payload.get("session_id"),
                    "cwd": payload.get("cwd"),
                    "started": payload.get("timestamp") or record.get("timestamp"),
                }
        return {"agent": "codex", "session_id": None, "cwd": None, "started": None}
    first = next((r for r in records if r.get("sessionId")), {})
    started = next((r.get("timestamp") for r in records if r.get("timestamp")), None)
    return {
        "agent": "claude-code",
        "session_id": first.get("sessionId"),
        "cwd": first.get("cwd"),
        "started": started,
    }


def _output_text(output: Any) -> str | None:
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        texts = [b.get("text") for b in output if isinstance(b, dict)]
        return "\n".join(t for t in texts if isinstance(t, str)) or None
    return None


def shell_exit_error(output: Any) -> str | None:
    """The failure a Codex tool output reports (a non-zero exit code), or ``None``."""
    text = _output_text(output)
    if text is None:
        return None
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            metadata = parsed.get("metadata")
            code = metadata.get("exit_code") if isinstance(metadata, dict) else None
            if isinstance(code, int) and not isinstance(code, bool) and code != 0:
                body = parsed.get("output")
                tail = f": {str(body).strip()[-200:]}" if body else ""
                return f"exit code {code}{tail}"
            return None
    match = _EXIT_TEXT.search(text)
    if match and int(match.group(1)) != 0:
        return f"exit code {match.group(1)}: {stripped[-200:]}"
    return None


class ClaudeCodeSessionAdapter(BaseAdapter):
    """Reads a Claude Code session transcript (the parsed lines of its JSONL file)."""

    def __init__(self, sidechains: bool = False) -> None:
        self.sidechains = sidechains

    def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
        """Parse the session's tool calls, with their results and errors.

        Args:
            trace_data: The parsed lines of the session file.

        Returns:
            The calls of the main thread (and the sidechains, if asked), in order.
        """
        messages = claude_code_messages(trace_data, sidechains=self.sidechains)
        if not messages:
            return []
        calls = AnthropicAdapter().parse(messages)
        for call in calls:
            call.metadata.setdefault("format", "claude-code")
        return calls


class CodexSessionAdapter(BaseAdapter):
    """Reads a Codex CLI rollout (the parsed lines of its JSONL file)."""

    def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
        """Parse the rollout's tool calls, with their outputs and shell failures.

        Args:
            trace_data: The parsed lines of the rollout file.

        Returns:
            The calls, in order.
        """
        from toolscore.adapters.openai import _responses_call
        from toolscore.integrations import from_openai_responses

        items = codex_items(trace_data)
        responses = [i for i in items if i.get("type") != "local_shell_call"]
        calls_by_order: list[tuple[int, ToolCall]] = []
        call_positions = {
            i.get("call_id"): n
            for n, i in enumerate(items)
            if i.get("type") in ("function_call", "custom_tool_call", "local_shell_call")
        }
        outputs = {
            i.get("call_id"): i.get("output")
            for i in items
            if i.get("type") in ("function_call_output", "custom_tool_call_output")
        }
        for entry in from_openai_responses(responses) if responses else []:
            call = _responses_call(entry)
            call.metadata["format"] = "codex"
            position = call_positions.get(call.id, len(items))
            calls_by_order.append((position, call))
        for n, item in enumerate(items):
            if item.get("type") != "local_shell_call":
                continue
            raw_action = item.get("action")
            action: dict[str, Any] = raw_action if isinstance(raw_action, dict) else {}
            call_id = item.get("call_id")
            call = ToolCall(
                tool="local_shell",
                args=dict(action),
                result=outputs.get(call_id),
                metadata={"format": "codex", "id": call_id} if call_id else {"format": "codex"},
            )
            calls_by_order.append((n, call))
        calls_by_order.sort(key=lambda pair: pair[0])
        calls = [call for _, call in calls_by_order]
        for call in calls:
            if call.is_error:
                continue
            error = shell_exit_error(call.result)
            if error is not None:
                call.metadata["is_error"] = True
                call.metadata["error"] = error
        return calls
