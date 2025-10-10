"""OpenAI trace format adapter."""

import json
from typing import Any

from toolscore.adapters.base import BaseAdapter, ToolCall


class OpenAIAdapter(BaseAdapter):
    """Adapter for OpenAI function call traces.

    Parses OpenAI Chat Completion API conversation logs that include
    function/tool calls in the message history.
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
