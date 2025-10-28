"""Google Gemini trace format adapter."""

import json
from typing import Any

from toolscore.adapters.base import BaseAdapter, ToolCall


class GeminiAdapter(BaseAdapter):
    """Adapter for Google Gemini function call traces.

    Parses Google Gemini API conversation logs that include
    function calls in the candidate responses.
    """

    def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
        """Parse Gemini trace into normalized tool calls.

        Args:
            trace_data: Gemini message history or response containing function calls.
                Can be a list of messages or a dict with 'candidates' key.

        Returns:
            List of ToolCall objects extracted from the trace.

        Raises:
            ValueError: If trace format is invalid.
        """
        self._validate_trace_data(trace_data)

        tool_calls: list[ToolCall] = []

        # Handle different Gemini response formats
        if isinstance(trace_data, dict):
            # Check for 'candidates' key (typical Gemini response format)
            if "candidates" in trace_data:
                candidates = trace_data["candidates"]
                for candidate in candidates:
                    tool_calls.extend(self._parse_candidate(candidate))

            # Check for 'content' key (direct message format)
            elif "content" in trace_data:
                tool_calls.extend(self._parse_content(trace_data["content"]))

            # Check if it's a single message object
            elif "parts" in trace_data:
                tool_calls.extend(self._parse_parts(trace_data["parts"]))

        elif isinstance(trace_data, list):
            # List of messages/candidates
            for item in trace_data:
                if isinstance(item, dict):
                    # Could be candidates or messages
                    if "content" in item:
                        tool_calls.extend(self._parse_content(item["content"]))
                    elif "parts" in item:
                        tool_calls.extend(self._parse_parts(item["parts"]))
                    elif "functionCall" in item or "function_call" in item:
                        tool_calls.append(self._parse_function_call(item))

        return tool_calls

    def _parse_candidate(self, candidate: dict[str, Any]) -> list[ToolCall]:
        """Parse a single candidate from Gemini response."""
        tool_calls: list[ToolCall] = []

        if "content" in candidate:
            tool_calls.extend(self._parse_content(candidate["content"]))

        return tool_calls

    def _parse_content(self, content: dict[str, Any] | list[Any]) -> list[ToolCall]:
        """Parse content object containing parts."""
        tool_calls: list[ToolCall] = []

        if isinstance(content, dict) and "parts" in content:
            tool_calls.extend(self._parse_parts(content["parts"]))
        elif isinstance(content, list):
            # Content is already a list of parts
            tool_calls.extend(self._parse_parts(content))

        return tool_calls

    def _parse_parts(self, parts: list[Any]) -> list[ToolCall]:
        """Parse parts list for function calls."""
        tool_calls: list[ToolCall] = []

        if not isinstance(parts, list):
            return tool_calls

        for part in parts:
            if not isinstance(part, dict):
                continue

            # Check for functionCall (Gemini format)
            if "functionCall" in part:
                tool_calls.append(self._parse_function_call(part["functionCall"]))

            # Check for function_call (alternative format)
            elif "function_call" in part:
                tool_calls.append(self._parse_function_call(part["function_call"]))

        return tool_calls

    def _parse_function_call(self, func_call: dict[str, Any]) -> ToolCall:
        """Parse a single function call object."""
        # Extract tool name
        tool_name = func_call.get("name", "")

        # Extract arguments
        # Gemini can use 'args' or 'arguments'
        args = func_call.get("args", func_call.get("arguments", {}))

        # If args is a string, try to parse as JSON
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"raw": args}
        elif args is None:
            args = {}

        # Create ToolCall with Gemini-specific metadata
        return ToolCall(
            tool=tool_name,
            args=args,
            metadata={
                "format": "gemini",
                "id": func_call.get("id"),
            },
        )
