"""Production trace capture for building test datasets from real agent executions."""

import json
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from toolscore.adapters.base import ToolCall


class TraceCapture:
    """Capture and save agent traces for building test datasets.

    This class enables capturing production agent executions and saving them
    as test cases, creating a feedback loop from production to testing.

    Example:
        >>> capture = TraceCapture(dataset_dir="tests/traces/production")
        >>>
        >>> @capture.trace(name="weather_query")
        >>> def my_agent(query: str) -> dict:
        ...     # Your agent logic here
        ...     tools_called = [...]
        ...     return {"tools": tools_called, "result": ...}
    """

    def __init__(
        self,
        dataset_dir: str | Path = "traces",
        auto_save: bool = True,
    ) -> None:
        """Initialize trace capture.

        Args:
            dataset_dir: Directory to save captured traces.
            auto_save: If True, automatically save traces after capture.
        """
        self.dataset_dir = Path(dataset_dir)
        self.auto_save = auto_save
        self.captured_traces: list[dict[str, Any]] = []

        # Create dataset directory if it doesn't exist
        if self.auto_save:
            self.dataset_dir.mkdir(parents=True, exist_ok=True)

    def trace(
        self,
        name: str | None = None,
        save_on_error: bool = True,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to capture agent execution traces.

        Args:
            name: Optional name for this trace (defaults to function name).
            save_on_error: If True, save traces even when the function raises an error.

        Returns:
            Decorated function that captures traces.

        Example:
            >>> @capture.trace(name="search_agent")
            >>> def search_and_summarize(query: str):
            ...     tools = [
            ...         {"tool": "web_search", "args": {"query": query}},
            ...         {"tool": "summarize", "args": {"text": "..."}},
            ...     ]
            ...     return {"tools": tools, "result": "summary"}
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                trace_name = name or func.__name__
                trace_id = self._generate_trace_id(trace_name)

                error_occurred = False
                result = None

                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    error_occurred = True
                    raise e
                finally:
                    # Save trace if requested or if no error
                    if not error_occurred or save_on_error:
                        self._save_trace(
                            trace_id=trace_id,
                            name=trace_name,
                            args=args,
                            kwargs=kwargs,
                            result=result,
                            error=error_occurred,
                        )

            return wrapper

        return decorator

    def capture_tools(
        self,
        tools: list[ToolCall] | list[dict[str, Any]],
        name: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Manually capture a list of tool calls.

        Useful for capturing traces from existing agent executions.

        Args:
            tools: List of ToolCall objects or dicts with 'tool' and 'args'.
            name: Name for this trace.
            description: Optional description of what this trace represents.
            metadata: Optional metadata to include.

        Returns:
            Path to the saved trace file.

        Example:
            >>> tools = [
            ...     {"tool": "search", "args": {"query": "Python"}},
            ...     {"tool": "summarize", "args": {"text": "..."}},
            ... ]
            >>> capture.capture_tools(tools, name="search_example")
        """
        trace_id = self._generate_trace_id(name)

        # Convert ToolCall objects to dicts
        tool_dicts = []
        for tool in tools:
            if isinstance(tool, ToolCall):
                tool_dicts.append(
                    {
                        "tool": tool.tool,
                        "args": tool.args or {},
                        **({"result": tool.result} if tool.result is not None else {}),
                    }
                )
            else:
                tool_dicts.append(tool)

        trace_data = {
            "id": trace_id,
            "name": name,
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "tools": tool_dicts,
            "metadata": metadata or {},
        }

        return self._save_trace_data(trace_data)

    def _generate_trace_id(self, name: str) -> str:
        """Generate unique trace ID.

        Args:
            name: Base name for the trace.

        Returns:
            Unique trace ID with timestamp.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{name}_{timestamp}"

    def _save_trace(
        self,
        trace_id: str,
        name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        result: Any,
        error: bool,
    ) -> None:
        """Save captured trace to file.

        Args:
            trace_id: Unique trace identifier.
            name: Trace name.
            args: Function positional arguments.
            kwargs: Function keyword arguments.
            result: Function return value.
            error: Whether an error occurred.
        """
        # Extract tools from result if it's a dict with 'tools' key
        tools = []
        if isinstance(result, dict) and "tools" in result:
            tools = result["tools"]
        elif isinstance(result, list):
            tools = result

        trace_data = {
            "id": trace_id,
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "tools": tools,
            "metadata": {
                "args": str(args) if args else None,
                "kwargs": kwargs,
                "error": error,
            },
        }

        if self.auto_save:
            self._save_trace_data(trace_data)
        else:
            self.captured_traces.append(trace_data)

    def _save_trace_data(self, trace_data: dict[str, Any]) -> Path:
        """Save trace data to JSON file.

        Args:
            trace_data: Trace data to save.

        Returns:
            Path to saved file.
        """
        filename = f"{trace_data['id']}.json"
        file_path = self.dataset_dir / filename

        with file_path.open("w") as f:
            json.dump(trace_data, f, indent=2)

        return file_path

    def save_all(self) -> list[Path]:
        """Save all captured traces (when auto_save=False).

        Returns:
            List of paths to saved trace files.
        """
        saved_paths = []
        for trace_data in self.captured_traces:
            path = self._save_trace_data(trace_data)
            saved_paths.append(path)

        self.captured_traces.clear()
        return saved_paths

    def to_gold_standard(
        self,
        trace_file: str | Path,
        output_file: str | Path,
        description: str = "",
    ) -> Path:
        """Convert a captured trace to gold standard format.

        Takes a production trace and converts it to the gold standard format
        used for evaluation, allowing you to turn successful executions into tests.

        Args:
            trace_file: Path to captured trace JSON file.
            output_file: Path to save gold standard file.
            description: Optional description for the gold standard.

        Returns:
            Path to the created gold standard file.

        Example:
            >>> capture.to_gold_standard(
            ...     trace_file="traces/search_agent_20251028_143022.json",
            ...     output_file="tests/gold/search_agent.json",
            ...     description="Successful web search and summarization"
            ... )
        """
        # Load trace
        with Path(trace_file).open() as f:
            trace_data = json.load(f)

        # Convert to gold standard format
        gold_calls = []
        for tool in trace_data.get("tools", []):
            gold_call = {
                "tool": tool["tool"],
                "args": tool.get("args", {}),
            }

            # Add description if provided
            if description:
                gold_call["description"] = description
            elif "description" in trace_data:
                gold_call["description"] = trace_data["description"]

            # Preserve result if available (for side-effect validation)
            if "result" in tool:
                gold_call["side_effects"] = {"result": tool["result"]}

            gold_calls.append(gold_call)

        # Save gold standard
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w") as f:
            json.dump(gold_calls, f, indent=2)

        return output_path


# Global default capture instance
_default_capture = TraceCapture()


def capture_trace(name: str | None = None, save_on_error: bool = True) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Convenience decorator using default capture instance.

    Args:
        name: Optional name for this trace.
        save_on_error: If True, save traces even on errors.

    Returns:
        Decorated function that captures traces.

    Example:
        >>> from toolscore import capture_trace
        >>>
        >>> @capture_trace(name="my_agent")
        >>> def run_agent(query: str):
        ...     return {"tools": [...]}
    """
    return _default_capture.trace(name=name, save_on_error=save_on_error)
