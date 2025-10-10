"""Pytest configuration and fixtures."""

import json
from pathlib import Path

import pytest

from toolscore.adapters.base import ToolCall


@pytest.fixture
def sample_gold_calls() -> list[ToolCall]:
    """Fixture providing sample gold standard calls."""
    return [
        ToolCall(
            tool="read_file",
            args={"path": "input.txt"},
        ),
        ToolCall(
            tool="process_data",
            args={"format": "json"},
        ),
        ToolCall(
            tool="write_file",
            args={"path": "output.txt", "content": "result"},
            metadata={"side_effects": {"file_exists": "output.txt"}},
        ),
    ]


@pytest.fixture
def sample_trace_calls() -> list[ToolCall]:
    """Fixture providing sample trace calls."""
    return [
        ToolCall(
            tool="read_file",
            args={"path": "input.txt"},
            result="file contents",
        ),
        ToolCall(
            tool="process_data",
            args={"format": "json"},
            result={"status": "success"},
        ),
        ToolCall(
            tool="write_file",
            args={"path": "output.txt", "content": "result"},
            result=True,
        ),
    ]


@pytest.fixture
def temp_gold_file(tmp_path: Path, sample_gold_calls: list[ToolCall]) -> Path:
    """Create a temporary gold standard file."""
    gold_file = tmp_path / "gold_calls.json"
    gold_data = [
        {
            "tool": call.tool,
            "args": call.args,
            "side_effects": call.metadata.get("side_effects", {}),
        }
        for call in sample_gold_calls
    ]

    with gold_file.open("w") as f:
        json.dump(gold_data, f)

    return gold_file


@pytest.fixture
def temp_trace_file(tmp_path: Path, sample_trace_calls: list[ToolCall]) -> Path:
    """Create a temporary trace file."""
    trace_file = tmp_path / "trace.json"
    trace_data = {
        "calls": [
            {
                "tool": call.tool,
                "args": call.args,
                "result": call.result,
            }
            for call in sample_trace_calls
        ]
    }

    with trace_file.open("w") as f:
        json.dump(trace_data, f)

    return trace_file
