"""Anthropic Claude trace format adapter."""

from typing import Any

from toolscore.adapters.base import BaseAdapter, ToolCall


class AnthropicAdapter(BaseAdapter):
    """Adapter for Anthropic Claude tool-use traces.

    Parses Anthropic/Claude API conversation logs that include tool_use
    content blocks in assistant messages. A ``tool_result`` block in a later
    user message is attached to the call with its ``tool_use_id``: its text
    becomes the call's ``result``, or, with ``is_error: true``, its ``error``.
    """

    def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
        """Parse Anthropic trace into normalized tool calls.

        Args:
            trace_data: Anthropic message history containing tool_use blocks.
                Can be a list of messages or a dict with 'messages' key.

        Returns:
            List of ToolCall objects extracted from the trace.

        Raises:
            ValueError: If trace format is invalid.
        """
        self._validate_trace_data(trace_data)

        # Extract messages list
        if isinstance(trace_data, dict):
            messages = trace_data.get("messages", trace_data.get("content", []))
        else:
            messages = trace_data

        if not isinstance(messages, list):
            raise ValueError("Expected list of messages in Anthropic trace")

        tool_calls: list[ToolCall] = []
        by_id: dict[Any, ToolCall] = {}

        for msg in messages:
            if not isinstance(msg, dict):
                continue

            content = msg.get("content", [])
            if not isinstance(content, list):
                continue

            if msg.get("role") == "user":
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        call = by_id.get(block.get("tool_use_id"))
                        if call is not None:
                            _attach_result(call, block)
                continue

            # Only process assistant messages
            if msg.get("role") != "assistant":
                continue

            # Extract tool_use blocks
            for block in content:
                if not isinstance(block, dict):
                    continue

                if block.get("type") == "tool_use":
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    tool_id = block.get("id")

                    call = ToolCall(
                        tool=tool_name,
                        args=tool_input if isinstance(tool_input, dict) else {},
                        metadata={
                            "format": "anthropic",
                            "id": tool_id,
                            "stop_reason": msg.get("stop_reason"),
                        },
                    )
                    tool_calls.append(call)
                    if isinstance(tool_id, str):
                        by_id[tool_id] = call

        return tool_calls


def block_text(content: Any) -> str:
    """The text of Anthropic content: a string, or the ``text`` of its blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        return "\n".join(p for p in parts if p)
    return ""


def _attach_result(call: ToolCall, block: dict[str, Any]) -> None:
    """Record a ``tool_result`` block on its call (an error when ``is_error``)."""
    text = block_text(block.get("content"))
    if block.get("is_error") is True:
        call.metadata["is_error"] = True
        call.metadata["error"] = text or "tool_result is_error"
    else:
        call.result = text
