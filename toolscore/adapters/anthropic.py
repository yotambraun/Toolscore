"""Anthropic Claude trace format adapter."""

from typing import Any

from toolscore.adapters.base import BaseAdapter, ToolCall


class AnthropicAdapter(BaseAdapter):
    """Adapter for Anthropic Claude tool-use traces.

    Parses Anthropic/Claude API conversation logs that include tool_use
    content blocks in assistant messages.
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

        for msg in messages:
            if not isinstance(msg, dict):
                continue

            # Only process assistant messages
            if msg.get("role") != "assistant":
                continue

            content = msg.get("content", [])
            if not isinstance(content, list):
                continue

            # Extract tool_use blocks
            for block in content:
                if not isinstance(block, dict):
                    continue

                if block.get("type") == "tool_use":
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    tool_id = block.get("id")

                    tool_calls.append(
                        ToolCall(
                            tool=tool_name,
                            args=tool_input if isinstance(tool_input, dict) else {},
                            metadata={
                                "format": "anthropic",
                                "id": tool_id,
                                "stop_reason": msg.get("stop_reason"),
                            },
                        )
                    )

        return tool_calls
