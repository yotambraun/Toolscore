"""OpenAI trace format adapter."""

import json
from typing import Any

from toolscore.adapters.base import BaseAdapter, ToolCall


class OpenAIAdapter(BaseAdapter):
    """Adapter for OpenAI function call traces.

    Parses OpenAI Chat Completion API conversation logs that include
    function/tool calls in the message history, and Responses API responses or
    item lists (``function_call``, ``mcp_call`` and ``custom_tool_call`` items,
    with outputs paired by ``call_id``).

    In a Chat Completions history, each ``role: "tool"`` message is attached to
    the call with its ``tool_call_id`` as the call's ``result`` (and a legacy
    ``role: "function"`` message to the latest call of that name), so checks
    that read tool output, such as the honesty checks, see what the tool said.
    """

    def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
        """Parse OpenAI trace into normalized tool calls.

        Args:
            trace_data: OpenAI message history or response containing function calls.
                Can be a list of messages or a dict with 'messages' key.

        Returns:
            List of ToolCall objects extracted from the trace.

        Raises:
            ValueError: If trace format is invalid.
        """
        self._validate_trace_data(trace_data)

        from toolscore.integrations import _is_responses_payload, from_openai_responses

        if _is_responses_payload(trace_data):
            return [_responses_call(c) for c in from_openai_responses(trace_data)]

        # Extract messages list
        if isinstance(trace_data, dict):
            messages = trace_data.get("messages", trace_data.get("choices", []))
            if isinstance(messages, list) and messages and "message" in messages[0]:
                # Handle response format with choices
                messages = [choice["message"] for choice in messages]
        else:
            messages = trace_data

        if not isinstance(messages, list):
            raise ValueError("Expected list of messages in OpenAI trace")

        tool_calls: list[ToolCall] = []

        for msg in messages:
            if not isinstance(msg, dict):
                continue

            if msg.get("role") in ("tool", "function"):
                _attach_output(tool_calls, msg)
                continue

            # Check for function_call (older format)
            if "function_call" in msg:
                func_call = msg["function_call"]
                tool_name = func_call.get("name", "")
                args_str = func_call.get("arguments", "{}")

                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {"raw": args_str}

                tool_calls.append(
                    ToolCall(
                        tool=tool_name,
                        args=args,
                        metadata={"format": "function_call"},
                    )
                )

            # Check for tool_calls (newer format)
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    if tc.get("type") == "function":
                        func = tc.get("function", {})
                        tool_name = func.get("name", "")
                        args_str = func.get("arguments", "{}")

                        try:
                            args = json.loads(args_str) if isinstance(args_str, str) else args_str
                        except json.JSONDecodeError:
                            args = {"raw": args_str}

                        tool_calls.append(
                            ToolCall(
                                tool=tool_name,
                                args=args,
                                metadata={
                                    "format": "tool_calls",
                                    "id": tc.get("id"),
                                },
                            )
                        )

        return tool_calls


def message_text(content: Any) -> str:
    """The text of a chat message ``content``: a string, or the text of its parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        return "\n".join(p for p in parts if p)
    return ""


def _attach_output(calls: list[ToolCall], message: dict[str, Any]) -> None:
    """Attach a ``role: tool``/``function`` message to the call it answers."""
    text = message_text(message.get("content"))
    if message.get("role") == "tool":
        call_id = message.get("tool_call_id")
        for call in reversed(calls):
            if call_id is not None and call.metadata.get("id") == call_id:
                call.result = text
                return
        return
    name = message.get("name")
    for call in reversed(calls):
        if call.tool == name and call.result is None:
            call.result = text
            return


def _responses_call(item: dict[str, Any]) -> ToolCall:
    """Turn one :func:`toolscore.integrations.from_openai_responses` dict into a ToolCall."""
    metadata: dict[str, Any] = {"format": "responses"}
    if item.get("id"):
        metadata["id"] = item["id"]
    if item.get("error"):
        metadata["error"] = item["error"]
        metadata["is_error"] = True
    return ToolCall(
        tool=item["tool"], args=item.get("args") or {}, result=item.get("result"), metadata=metadata
    )
