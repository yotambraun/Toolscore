"""Unit tests for core evaluation logic."""

import json

import pytest

from toolscore.adapters.base import ToolCall
from toolscore.core import (
    EvaluationResult,
    _detect_format,
    evaluate_trace,
    load_gold_standard,
    load_trace,
)


class TestEvaluationResult:
    """Tests for EvaluationResult class."""

    def test_create_result(self):
        """Test creating evaluation result."""
        result = EvaluationResult()
        assert result.metrics == {}
        assert result.gold_calls == []
        assert result.trace_calls == []

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = EvaluationResult()
        result.metrics = {"accuracy": 0.95}
        result.gold_calls = [ToolCall(tool="tool1")]
        result.trace_calls = [ToolCall(tool="tool1"), ToolCall(tool="tool2")]

        data = result.to_dict()

        assert data["metrics"] == {"accuracy": 0.95}
        assert data["gold_calls_count"] == 1
        assert data["trace_calls_count"] == 2


class TestLoadGoldStandard:
    """Tests for load_gold_standard function."""

    def test_load_valid_gold_standard(self, tmp_path):
        """Test loading valid gold standard file."""
        gold_file = tmp_path / "gold.json"
        gold_data = [
            {
                "tool": "make_file",
                "args": {"filename": "test.txt", "content": "hello"},
                "description": "Create a file",
                "side_effects": {"file_exists": "test.txt"},
            },
            {
                "tool": "read_file",
                "args": {"filename": "test.txt"},
            },
        ]

        with gold_file.open("w") as f:
            json.dump(gold_data, f)

        calls = load_gold_standard(gold_file)

        assert len(calls) == 2
        assert calls[0].tool == "make_file"
        assert calls[0].args == {"filename": "test.txt", "content": "hello"}
        assert calls[0].metadata["description"] == "Create a file"
        assert calls[0].metadata["side_effects"] == {"file_exists": "test.txt"}
        assert calls[1].tool == "read_file"

    def test_load_minimal_gold_standard(self, tmp_path):
        """Test loading minimal gold standard with just tool names."""
        gold_file = tmp_path / "gold.json"
        gold_data = [{"tool": "tool1"}, {"tool": "tool2"}]

        with gold_file.open("w") as f:
            json.dump(gold_data, f)

        calls = load_gold_standard(gold_file)

        assert len(calls) == 2
        assert calls[0].tool == "tool1"
        assert calls[0].args == {}
        assert calls[1].tool == "tool2"

    def test_load_missing_file(self):
        """Test loading nonexistent file."""
        with pytest.raises(FileNotFoundError):
            load_gold_standard("/nonexistent/gold.json")

    def test_load_invalid_format(self, tmp_path):
        """Test loading file with invalid format."""
        gold_file = tmp_path / "gold.json"
        with gold_file.open("w") as f:
            json.dump({"not": "a list"}, f)

        with pytest.raises(ValueError, match="Gold standard must be a JSON array"):
            load_gold_standard(gold_file)

    def test_load_skips_invalid_items(self, tmp_path):
        """Test loading skips items without tool name."""
        gold_file = tmp_path / "gold.json"
        gold_data = [
            {"tool": "valid_tool"},
            {"args": "missing tool name"},
            "invalid item",
            {"tool": "another_valid_tool"},
        ]

        with gold_file.open("w") as f:
            json.dump(gold_data, f)

        calls = load_gold_standard(gold_file)

        assert len(calls) == 2
        assert calls[0].tool == "valid_tool"
        assert calls[1].tool == "another_valid_tool"


class TestLoadTrace:
    """Tests for load_trace function."""

    def test_load_openai_trace(self, tmp_path):
        """Test loading OpenAI format trace."""
        trace_file = tmp_path / "trace.json"
        trace_data = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call_123",
                        "function": {
                            "name": "search",
                            "arguments": '{"query": "test"}',
                        },
                    }
                ],
            }
        ]

        with trace_file.open("w") as f:
            json.dump(trace_data, f)

        calls = load_trace(trace_file, format="openai")

        assert len(calls) == 1
        assert calls[0].tool == "search"
        assert calls[0].args == {"query": "test"}

    def test_load_anthropic_trace(self, tmp_path):
        """Test loading Anthropic format trace."""
        trace_file = tmp_path / "trace.json"
        trace_data = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_123",
                        "name": "web_search",
                        "input": {"query": "python"},
                    }
                ],
            }
        ]

        with trace_file.open("w") as f:
            json.dump(trace_data, f)

        calls = load_trace(trace_file, format="anthropic")

        assert len(calls) == 1
        assert calls[0].tool == "web_search"
        assert calls[0].args == {"query": "python"}

    def test_load_custom_trace(self, tmp_path):
        """Test loading custom format trace."""
        trace_file = tmp_path / "trace.json"
        trace_data = {
            "calls": [
                {"tool": "tool1", "args": {"x": 1}},
                {"tool": "tool2", "args": {"y": 2}},
            ]
        }

        with trace_file.open("w") as f:
            json.dump(trace_data, f)

        calls = load_trace(trace_file, format="custom")

        assert len(calls) == 2
        assert calls[0].tool == "tool1"
        assert calls[1].tool == "tool2"

    def test_load_auto_detect_openai(self, tmp_path):
        """Test auto-detection of OpenAI format."""
        trace_file = tmp_path / "trace.json"
        trace_data = [
            {
                "role": "assistant",
                "function_call": {
                    "name": "get_weather",
                    "arguments": '{"location": "NYC"}',
                },
            }
        ]

        with trace_file.open("w") as f:
            json.dump(trace_data, f)

        calls = load_trace(trace_file, format="auto")

        assert len(calls) == 1
        assert calls[0].tool == "get_weather"

    def test_load_missing_file(self):
        """Test loading nonexistent file."""
        with pytest.raises(FileNotFoundError):
            load_trace("/nonexistent/trace.json")

    def test_load_unsupported_format(self, tmp_path):
        """Test loading with unsupported format."""
        trace_file = tmp_path / "trace.json"
        with trace_file.open("w") as f:
            json.dump([], f)

        with pytest.raises(ValueError, match="Unsupported format"):
            load_trace(trace_file, format="unknown_format")


class TestDetectFormat:
    """Tests for _detect_format function."""

    def test_detect_openai_dict_format(self):
        """Test detecting OpenAI dict format."""
        data = {"messages": []}
        adapter = _detect_format(data)
        assert adapter.__class__.__name__ == "OpenAIAdapter"

    def test_detect_openai_list_format(self):
        """Test detecting OpenAI list format."""
        data = [{"role": "assistant", "function_call": {"name": "test"}}]
        adapter = _detect_format(data)
        assert adapter.__class__.__name__ == "OpenAIAdapter"

    def test_detect_anthropic_format(self):
        """Test detecting Anthropic format."""
        data = [{"role": "assistant", "content": [{"type": "tool_use"}]}]
        adapter = _detect_format(data)
        assert adapter.__class__.__name__ == "AnthropicAdapter"

    def test_detect_custom_format(self):
        """Test detecting custom format."""
        data = [{"tool": "test", "args": {}}]
        adapter = _detect_format(data)
        assert adapter.__class__.__name__ == "CustomAdapter"


class TestEvaluateTrace:
    """Tests for evaluate_trace function."""

    def test_evaluate_perfect_match(self, tmp_path):
        """Test evaluation with perfect match."""
        gold_file = tmp_path / "gold.json"
        trace_file = tmp_path / "trace.json"

        gold_data = [
            {"tool": "make_file", "args": {"filename": "test.txt"}},
        ]

        trace_data = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "make_file",
                            "arguments": '{"filename": "test.txt"}',
                        },
                    }
                ],
            }
        ]

        with gold_file.open("w") as f:
            json.dump(gold_data, f)
        with trace_file.open("w") as f:
            json.dump(trace_data, f)

        result = evaluate_trace(gold_file, trace_file, format="openai")

        assert result.metrics["invocation_accuracy"] == 1.0
        assert result.metrics["selection_accuracy"] == 1.0
        assert result.metrics["sequence_metrics"]["sequence_accuracy"] == 1.0
        assert len(result.gold_calls) == 1
        assert len(result.trace_calls) == 1

    def test_evaluate_with_side_effects(self, tmp_path):
        """Test evaluation with side effects validation."""
        gold_file = tmp_path / "gold.json"
        trace_file = tmp_path / "trace.json"

        gold_data = [
            {
                "tool": "create_resource",
                "args": {"name": "test"},
                "side_effects": {"file_exists": "test.txt"},
            }
        ]

        trace_data = [
            {
                "tool": "create_resource",
                "args": {"name": "test"},
            }
        ]

        with gold_file.open("w") as f:
            json.dump(gold_data, f)
        with trace_file.open("w") as f:
            json.dump(trace_data, f)

        result = evaluate_trace(gold_file, trace_file, validate_side_effects=True)

        assert "side_effect_metrics" in result.metrics
        assert "success_rate" in result.metrics["side_effect_metrics"]

    def test_evaluate_without_side_effects(self, tmp_path):
        """Test evaluation without side effects validation."""
        gold_file = tmp_path / "gold.json"
        trace_file = tmp_path / "trace.json"

        gold_data = [{"tool": "test_tool"}]
        trace_data = [{"tool": "test_tool"}]

        with gold_file.open("w") as f:
            json.dump(gold_data, f)
        with trace_file.open("w") as f:
            json.dump(trace_data, f)

        result = evaluate_trace(gold_file, trace_file, validate_side_effects=False)

        assert "side_effect_metrics" not in result.metrics

    def test_evaluate_mismatch(self, tmp_path):
        """Test evaluation with mismatched calls."""
        gold_file = tmp_path / "gold.json"
        trace_file = tmp_path / "trace.json"

        gold_data = [
            {"tool": "tool_a", "args": {"x": 1}},
            {"tool": "tool_b", "args": {"y": 2}},
        ]

        trace_data = [
            {
                "tool": "tool_c",
                "args": {"z": 3},
            }
        ]

        with gold_file.open("w") as f:
            json.dump(gold_data, f)
        with trace_file.open("w") as f:
            json.dump(trace_data, f)

        result = evaluate_trace(gold_file, trace_file)

        assert result.metrics["selection_accuracy"] < 1.0
        assert result.metrics["invocation_accuracy"] < 1.0

    def test_evaluate_empty_traces(self, tmp_path):
        """Test evaluation with empty traces."""
        gold_file = tmp_path / "gold.json"
        trace_file = tmp_path / "trace.json"

        with gold_file.open("w") as f:
            json.dump([], f)
        with trace_file.open("w") as f:
            json.dump([], f)

        result = evaluate_trace(gold_file, trace_file)

        assert result.metrics["invocation_accuracy"] == 1.0
        assert len(result.gold_calls) == 0
        assert len(result.trace_calls) == 0
