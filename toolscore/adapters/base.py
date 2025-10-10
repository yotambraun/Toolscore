"""Base adapter interface for trace format conversion."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """Represents a single tool call in a trace.

    Attributes:
        tool: Name of the tool/function called.
        args: Arguments provided to the tool (dict or None).
        result: Result returned by the tool (optional).
        timestamp: Unix timestamp of when the call was made (optional).
        duration: Duration of the call in seconds (optional).
        cost: Cost associated with this call in USD (optional).
        metadata: Additional metadata about the call.
    """

    tool: str
    args: dict[str, Any] | None = None
    result: Any = None
    timestamp: float | None = None
    duration: float | None = None
    cost: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate tool call data after initialization."""
        if not self.tool:
            raise ValueError("Tool name cannot be empty")
        if self.args is None:
            self.args = {}


class BaseAdapter(ABC):
    """Abstract base class for trace format adapters.

    All trace format adapters must inherit from this class and implement
    the parse method to convert provider-specific formats into a normalized
    list of ToolCall objects.
    """

    @abstractmethod
    def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
        """Parse trace data into a normalized list of tool calls.

        Args:
            trace_data: The raw trace data from the LLM provider.

        Returns:
            A list of ToolCall objects in chronological order.

        Raises:
            ValueError: If the trace data is invalid or cannot be parsed.
        """
        pass

    def _validate_trace_data(self, trace_data: Any) -> None:
        """Validate that trace data is in expected format.

        Args:
            trace_data: The raw trace data to validate.

        Raises:
            ValueError: If trace data is None or not dict/list.
        """
        if trace_data is None:
            raise ValueError("Trace data cannot be None")
        if not isinstance(trace_data, (dict, list)):
            raise ValueError(
                f"Trace data must be dict or list, got {type(trace_data).__name__}"
            )
