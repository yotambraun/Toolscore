"""Tests for synthetic test generation."""

import json
from pathlib import Path

import pytest

from toolscore.generators.synthetic import (
    _create_test_case,
    _generate_value_from_schema,
    generate_from_openai_schema,
    save_gold_standard,
)


def test_generate_value_string():
    """Test generating string values."""
    schema = {"type": "string"}
    value = _generate_value_from_schema("test_param", schema, "normal")
    assert isinstance(value, str)


def test_generate_value_integer():
    """Test generating integer values."""
    schema = {"type": "integer", "minimum": 1, "maximum": 10}
    value = _generate_value_from_schema("count", schema, "normal")
    assert isinstance(value, int)
    assert 1 <= value <= 10


def test_generate_value_integer_boundary():
    """Test generating boundary integer values."""
    schema = {"type": "integer", "minimum": 5, "maximum": 20}
    value = _generate_value_from_schema("count", schema, "boundary")
    assert value == 5  # Should be minimum for boundary


def test_generate_value_integer_edge():
    """Test generating edge integer values."""
    schema = {"type": "integer", "minimum": 1, "maximum": 100}
    value = _generate_value_from_schema("count", schema, "edge")
    assert value == 100  # Should be maximum for edge


def test_generate_value_number():
    """Test generating number values."""
    schema = {"type": "number", "minimum": 0.0, "maximum": 1.0}
    value = _generate_value_from_schema("score", schema, "normal")
    assert isinstance(value, float)
    assert 0.0 <= value <= 1.0


def test_generate_value_boolean():
    """Test generating boolean values."""
    schema = {"type": "boolean"}
    value = _generate_value_from_schema("flag", schema, "normal")
    assert isinstance(value, bool)


def test_generate_value_enum():
    """Test generating enum values."""
    schema = {"type": "string", "enum": ["celsius", "fahrenheit"]}
    value = _generate_value_from_schema("unit", schema, "normal")
    assert value in ["celsius", "fahrenheit"]


def test_generate_value_array():
    """Test generating array values."""
    schema = {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 1,
        "maxItems": 3,
    }
    value = _generate_value_from_schema("tags", schema, "normal")
    assert isinstance(value, list)
    assert 1 <= len(value) <= 3
    assert all(isinstance(item, str) for item in value)


def test_generate_value_object():
    """Test generating object values."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 0, "maximum": 120},
        },
    }
    value = _generate_value_from_schema("user", schema, "normal")
    assert isinstance(value, dict)
    assert "name" in value
    assert "age" in value
    assert isinstance(value["name"], str)
    assert isinstance(value["age"], int)


def test_create_test_case():
    """Test creating a single test case."""
    function_def = {
        "name": "get_weather",
        "description": "Get weather for location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "unit": {"type": "string", "enum": ["C", "F"]},
            },
            "required": ["location"],
        },
    }

    test_case = _create_test_case(function_def, "normal")

    assert test_case["tool"] == "get_weather"
    assert "location" in test_case["args"]
    assert isinstance(test_case["args"]["location"], str)
    assert test_case["metadata"]["description"] == "Get weather for location"
    assert "schema" in test_case["metadata"]
    assert "location" in test_case["metadata"]["schema"]
    assert test_case["metadata"]["schema"]["location"]["required"] is True


def test_create_test_case_optional_params():
    """Test that optional parameters are sometimes skipped."""
    function_def = {
        "name": "search",
        "description": "Search for items",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
        },
    }

    # Generate multiple test cases to check randomness
    test_cases = [_create_test_case(function_def, "normal") for _ in range(10)]

    # At least one should have the optional param
    has_optional = any("limit" in tc["args"] for tc in test_cases)
    # At least one should not have the optional param
    missing_optional = any("limit" not in tc["args"] for tc in test_cases)

    assert has_optional  # Sometimes included
    assert missing_optional  # Sometimes excluded


def test_generate_from_openai_schema_single_function(tmp_path):
    """Test generating from a single function schema."""
    schema_file = tmp_path / "schema.json"
    schema = {
        "name": "add_numbers",
        "description": "Add two numbers",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
    }

    schema_file.write_text(json.dumps(schema))

    gold_calls = generate_from_openai_schema(schema_file, count=5, include_edge_cases=False)

    assert len(gold_calls) == 5
    assert all(call["tool"] == "add_numbers" for call in gold_calls)
    assert all("a" in call["args"] for call in gold_calls)
    assert all("b" in call["args"] for call in gold_calls)


def test_generate_from_openai_schema_multiple_functions(tmp_path):
    """Test generating from multiple function schemas."""
    schema_file = tmp_path / "schema.json"
    schema = [
        {
            "name": "function1",
            "description": "First function",
            "parameters": {
                "type": "object",
                "properties": {"arg1": {"type": "string"}},
                "required": ["arg1"],
            },
        },
        {
            "name": "function2",
            "description": "Second function",
            "parameters": {
                "type": "object",
                "properties": {"arg2": {"type": "integer"}},
                "required": ["arg2"],
            },
        },
    ]

    schema_file.write_text(json.dumps(schema))

    gold_calls = generate_from_openai_schema(schema_file, count=3, include_edge_cases=False)

    # Should have 3 calls per function = 6 total
    assert len(gold_calls) == 6

    function1_calls = [c for c in gold_calls if c["tool"] == "function1"]
    function2_calls = [c for c in gold_calls if c["tool"] == "function2"]

    assert len(function1_calls) == 3
    assert len(function2_calls) == 3


def test_generate_with_edge_cases(tmp_path):
    """Test that edge cases are generated when requested."""
    schema_file = tmp_path / "schema.json"
    schema = {
        "name": "test_func",
        "description": "Test function",
        "parameters": {
            "type": "object",
            "properties": {
                "value": {"type": "integer", "minimum": 1, "maximum": 100}
            },
            "required": ["value"],
        },
    }

    schema_file.write_text(json.dumps(schema))

    gold_calls = generate_from_openai_schema(schema_file, count=10, include_edge_cases=True)

    # Should have 10 calls with mix of normal, boundary, edge
    assert len(gold_calls) == 10

    # Check that we have some boundary values (1) and edge values (100)
    values = [call["args"]["value"] for call in gold_calls]
    assert 1 in values  # Boundary
    assert 100 in values  # Edge


def test_generate_file_not_found():
    """Test that FileNotFoundError is raised for non-existent schema."""
    with pytest.raises(FileNotFoundError):
        generate_from_openai_schema("nonexistent.json", count=10)


def test_save_gold_standard(tmp_path):
    """Test saving gold standard to file."""
    gold_calls = [
        {
            "tool": "test_tool",
            "args": {"param": "value"},
            "result": None,
            "timestamp": None,
            "duration": None,
            "cost": None,
            "metadata": {},
        }
    ]

    output_file = tmp_path / "gold.json"
    result_path = save_gold_standard(gold_calls, output_file)

    assert result_path == output_file
    assert output_file.exists()

    # Verify content
    with output_file.open() as f:
        saved_calls = json.load(f)

    assert len(saved_calls) == 1
    assert saved_calls[0]["tool"] == "test_tool"
    assert saved_calls[0]["args"]["param"] == "value"


def test_save_gold_standard_creates_parent_dirs(tmp_path):
    """Test that parent directories are created if they don't exist."""
    output_file = tmp_path / "subdir" / "nested" / "gold.json"
    gold_calls = [{"tool": "test", "args": {}, "metadata": {}}]

    result_path = save_gold_standard(gold_calls, output_file)

    assert result_path.exists()
    assert result_path.parent.exists()
