"""JSON report generation."""

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult


def _serialize_tool_call(call: Any) -> dict[str, Any]:
    """Serialize a ToolCall to JSON-compatible dict.

    Args:
        call: ToolCall to serialize.

    Returns:
        Dictionary representation.
    """
    return {
        "tool": call.tool,
        "args": call.args,
        "result": call.result,
        "timestamp": call.timestamp,
        "duration": call.duration,
        "cost": call.cost,
        "metadata": call.metadata,
    }


def generate_json_report(
    result: "EvaluationResult",
    output_path: str | Path = "toolscore.json",
) -> Path:
    """Generate JSON report from evaluation result.

    Args:
        result: Evaluation result to report.
        output_path: Path to save the JSON report.

    Returns:
        Path to the generated report file.
    """
    path = Path(output_path)

    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "gold_calls_count": len(result.gold_calls),
            "trace_calls_count": len(result.trace_calls),
        },
        "metrics": result.metrics,
        "gold_calls": [_serialize_tool_call(call) for call in result.gold_calls],
        "trace_calls": [_serialize_tool_call(call) for call in result.trace_calls],
    }

    with path.open("w") as f:
        json.dump(report, f, indent=2)

    return path
