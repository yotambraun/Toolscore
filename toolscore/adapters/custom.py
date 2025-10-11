"""Custom/generic JSON trace format adapter."""

from typing import Any

from toolscore.adapters.base import BaseAdapter, ToolCall


class CustomAdapter(BaseAdapter):
    """Adapter for custom/generic JSON trace formats.

    Accepts a simplified trace format with a 'calls' array or directly
    as an array of tool call objects.
    """

    def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
        """Parse custom JSON trace into normalized tool calls.

        Args:
            trace_data: Custom trace format. Can be:
                - {"calls": [...]} with array of call objects
                - Direct array of call objects
                Each call object should have at minimum a 'tool' or 'name' field.

        Returns:
            List of ToolCall objects extracted from the trace.

        Raises:
            ValueError: If trace format is invalid.
        """
        self._validate_trace_data(trace_data)

        # Extract calls array
        if isinstance(trace_data, dict):
            calls = trace_data.get("calls", trace_data.get("tool_calls", []))
            if not calls:
                # Maybe the dict itself is a single call
                calls = [trace_data] if "tool" in trace_data or "name" in trace_data else []
        else:
            calls = trace_data

        if not isinstance(calls, list):
            raise ValueError("Expected list of calls in custom trace")

        tool_calls: list[ToolCall] = []

        for call in calls:
            if not isinstance(call, dict):
                continue

            # Extract tool name (try multiple possible keys)
            tool_name = call.get("tool") or call.get("name") or call.get("function")
            if not tool_name:
                continue

            # Extract arguments (try multiple possible keys)
            args = call.get("args") or call.get("arguments") or call.get("input") or {}
            if not isinstance(args, dict):
                args = {"value": args}

            # Extract optional fields
            result = call.get("result") or call.get("output")
            timestamp = call.get("timestamp") or call.get("time")
            duration = call.get("duration") or call.get("elapsed")
            cost = call.get("cost")

            # Collect remaining fields as metadata
            metadata_keys = {
                "tool",
                "name",
                "function",
                "args",
                "arguments",
                "input",
                "result",
                "output",
                "timestamp",
                "time",
                "duration",
                "elapsed",
                "cost",
            }
            metadata = {k: v for k, v in call.items() if k not in metadata_keys}

            tool_calls.append(
                ToolCall(
                    tool=tool_name,
                    args=args,
                    result=result,
                    timestamp=timestamp,
                    duration=duration,
                    cost=cost,
                    metadata=metadata,
                )
            )

        return tool_calls
