"""Adapter for LangChain agent traces.

This adapter handles traces from LangChain agents, supporting both
the legacy and modern agent formats.
"""

from __future__ import annotations

import json
from typing import Any

from toolscore.adapters.base import BaseAdapter, ToolCall


class LangChainAdapter(BaseAdapter):
    """Adapter for LangChain agent traces.

    Supports parsing of:
    - AgentAction objects (legacy format)
    - ToolCall objects (modern format)
    - Raw dictionaries with tool/action information

    Example LangChain trace formats:

    Legacy format (AgentAction):
    ```python
    [
        {
            "tool": "search",
            "tool_input": {"query": "Python"},
            "log": "Invoking search..."
        }
    ]
    ```

    Modern format (ToolCall):
    ```python
    [
        {
            "name": "search",
            "args": {"query": "Python"},
            "id": "call_123"
        }
    ]
    ```
    """

    def parse(self, data: Any) -> list[ToolCall]:
        """Parse LangChain trace data.

        Args:
            data: LangChain trace data (list of actions/calls)

        Returns:
            List of ToolCall objects

        Raises:
            ValueError: If data format is invalid
        """
        if not isinstance(data, list):
            raise ValueError("LangChain trace must be a list")

        tool_calls = []

        for item in data:
            if not isinstance(item, dict):
                continue

            # Try different LangChain formats
            tool_call = self._parse_agent_action(item) or self._parse_tool_call(item)

            if tool_call:
                tool_calls.append(tool_call)

        return tool_calls

    def _parse_agent_action(self, item: dict[str, Any]) -> ToolCall | None:
        """Parse legacy AgentAction format.

        Args:
            item: Dictionary with 'tool' and 'tool_input' keys

        Returns:
            ToolCall if valid, None otherwise
        """
        if "tool" not in item:
            return None

        tool_name = item["tool"]
        tool_input = item.get("tool_input", {})

        # Handle string input (sometimes tool_input is a string)
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except (json.JSONDecodeError, ValueError):
                # If not JSON, treat as single argument
                tool_input = {"input": tool_input}

        # Extract metadata
        metadata: dict[str, Any] = {"format": "langchain_legacy"}
        if "log" in item:
            metadata["log"] = item["log"]
        if "tool_call_id" in item:
            metadata["id"] = item["tool_call_id"]

        return ToolCall(
            tool=tool_name,
            args=tool_input if isinstance(tool_input, dict) else {},
            metadata=metadata,
        )

    def _parse_tool_call(self, item: dict[str, Any]) -> ToolCall | None:
        """Parse modern ToolCall format.

        Args:
            item: Dictionary with 'name' and 'args' keys

        Returns:
            ToolCall if valid, None otherwise
        """
        # Modern format: name + args
        if "name" in item:
            tool_name = item["name"]
            args = item.get("args", {})

            metadata: dict[str, Any] = {"format": "langchain_modern"}
            if "id" in item:
                metadata["id"] = item["id"]
            if "type" in item:
                metadata["type"] = item["type"]

            return ToolCall(tool=tool_name, args=args, metadata=metadata)

        # Alternative: action + action_input (some LangChain versions)
        if "action" in item:
            tool_name = item["action"]
            action_input = item.get("action_input", {})

            if isinstance(action_input, str):
                try:
                    action_input = json.loads(action_input)
                except (json.JSONDecodeError, ValueError):
                    action_input = {"input": action_input}

            metadata = {"format": "langchain_action"}

            return ToolCall(
                tool=tool_name,
                args=action_input if isinstance(action_input, dict) else {},
                metadata=metadata,
            )

        return None
