"""Synthetic test case generation from function schemas."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


def _generate_value_from_schema(
    param_name: str, param_schema: dict[str, Any], variation: str = "normal"
) -> Any:
    """Generate a value based on parameter schema and variation type.

    Args:
        param_name: Name of the parameter
        param_schema: JSON schema for the parameter
        variation: Type of variation ("normal", "edge", "boundary", "invalid")

    Returns:
        Generated value matching the schema
    """
    param_type = param_schema.get("type", "string")

    # Handle enum values
    if "enum" in param_schema:
        enum_values = param_schema["enum"]
        if variation == "normal":
            return random.choice(enum_values)
        elif variation == "edge":
            return enum_values[0]  # First value
        elif variation == "boundary":
            return enum_values[-1]  # Last value
        else:
            return random.choice(enum_values)

    # String type
    if param_type == "string":
        examples = {
            "query": ["wireless headphones", "laptop", "coffee maker"],
            "search": ["best restaurants", "weather today", "news"],
            "text": ["Hello world", "Test message", "Sample text"],
            "message": ["Important update", "Hello!", "Test notification"],
            "email": ["user@example.com", "test@test.com", "admin@domain.org"],
            "url": ["https://example.com", "https://api.test.com/data", "https://docs.site.io"],
            "path": ["/home/user/file.txt", "/tmp/data.json", "/var/log/app.log"],
            "filename": ["output.txt", "data.json", "report.pdf"],
            "name": ["John Doe", "Alice Smith", "Bob Johnson"],
            "city": ["San Francisco", "New York", "London"],
            "country": ["US", "UK", "CA"],
        }

        # Try to match parameter name to examples
        for key, values in examples.items():
            if key in param_name.lower():
                if variation == "edge":
                    return values[0]
                elif variation == "boundary":
                    min_len = param_schema.get("minLength", 1)
                    return "a" * min_len if min_len else "x"
                else:
                    return random.choice(values)

        # Default string values
        if variation == "boundary":
            min_len = param_schema.get("minLength", 1)
            return "x" * min_len
        elif variation == "edge":
            max_len = param_schema.get("maxLength", 100)
            return "a" * min(max_len, 10)
        else:
            return f"sample_{param_name}"

    # Integer type
    elif param_type == "integer":
        minimum = param_schema.get("minimum", 1)
        maximum = param_schema.get("maximum", 100)

        if variation == "boundary":
            return minimum
        elif variation == "edge":
            return maximum
        else:
            return random.randint(minimum, min(maximum, minimum + 20))

    # Number type
    elif param_type == "number":
        minimum = param_schema.get("minimum", 0.0)
        maximum = param_schema.get("maximum", 100.0)

        if variation == "boundary":
            return minimum
        elif variation == "edge":
            return maximum
        else:
            return round(random.uniform(minimum, min(maximum, minimum + 50.0)), 2)

    # Boolean type
    elif param_type == "boolean":
        if variation == "edge":
            return True
        else:
            return random.choice([True, False])

    # Array type
    elif param_type == "array":
        items_schema = param_schema.get("items", {})
        min_items = param_schema.get("minItems", 1)
        max_items = param_schema.get("maxItems", 5)

        if variation == "boundary":
            count = min_items
        elif variation == "edge":
            count = min(max_items, 3)
        else:
            count = random.randint(min_items, min(max_items, 3))

        return [
            _generate_value_from_schema(f"{param_name}_item", items_schema, "normal")
            for _ in range(count)
        ]

    # Object type
    elif param_type == "object":
        properties = param_schema.get("properties", {})
        return {
            key: _generate_value_from_schema(key, value, variation)
            for key, value in properties.items()
        }

    return None


def _create_test_case(
    function_def: dict[str, Any], variation: str = "normal"
) -> dict[str, Any]:
    """Create a single test case from function definition.

    Args:
        function_def: OpenAI function definition
        variation: Type of test case to generate

    Returns:
        Toolscore gold call format
    """
    function_name = function_def.get("name", "unknown")
    parameters = function_def.get("parameters", {})
    properties = parameters.get("properties", {})
    required = parameters.get("required", [])

    # Generate arguments
    args = {}
    for param_name, param_schema in properties.items():
        # For normal variation, skip some optional params randomly
        if variation == "normal" and param_name not in required and random.random() > 0.5:
            continue

        args[param_name] = _generate_value_from_schema(param_name, param_schema, variation)

    # Build metadata with schema
    metadata: dict[str, Any] = {
        "description": function_def.get("description", f"Call {function_name}"),
        "schema": {},
    }

    # Add schema validation rules
    for param_name, param_schema in properties.items():
        schema_rules: dict[str, Any] = {"type": param_schema.get("type", "string")}

        # Add constraints
        if "minimum" in param_schema:
            schema_rules["minimum"] = param_schema["minimum"]
        if "maximum" in param_schema:
            schema_rules["maximum"] = param_schema["maximum"]
        if "minLength" in param_schema:
            schema_rules["minLength"] = param_schema["minLength"]
        if "maxLength" in param_schema:
            schema_rules["maxLength"] = param_schema["maxLength"]
        if "pattern" in param_schema:
            schema_rules["pattern"] = param_schema["pattern"]
        if "enum" in param_schema:
            schema_rules["enum"] = param_schema["enum"]
        if "items" in param_schema:
            schema_rules["items"] = param_schema["items"]
        if "properties" in param_schema:
            schema_rules["properties"] = param_schema["properties"]

        # Mark as required or optional
        schema_rules["required"] = param_name in required

        metadata["schema"][param_name] = schema_rules

    return {
        "tool": function_name,
        "args": args,
        "result": None,
        "timestamp": None,
        "duration": None,
        "cost": None,
        "metadata": metadata,
    }


def generate_from_openai_schema(
    schema_file: str | Path,
    count: int = 10,
    include_edge_cases: bool = True,
) -> list[dict[str, Any]]:
    """Generate synthetic test cases from OpenAI function schema.

    Args:
        schema_file: Path to OpenAI function definitions JSON file
        count: Number of test cases to generate per function
        include_edge_cases: Whether to include boundary and edge case variations

    Returns:
        List of gold standard test cases in Toolscore format

    Example OpenAI schema format:
        [
            {
                "name": "get_weather",
                "description": "Get weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                    },
                    "required": ["location"]
                }
            }
        ]
    """
    schema_path = Path(schema_file)
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    # Load function definitions
    with schema_path.open() as f:
        functions = json.load(f)

    # Handle single function or list
    if isinstance(functions, dict):
        functions = [functions]

    gold_calls = []

    for function_def in functions:
        # Determine number of variations
        if include_edge_cases:
            # Generate: normal (60%), boundary (20%), edge (20%)
            normal_count = int(count * 0.6)
            boundary_count = int(count * 0.2)
            edge_count = count - normal_count - boundary_count

            # Generate normal cases
            for _ in range(normal_count):
                gold_calls.append(_create_test_case(function_def, "normal"))

            # Generate boundary cases
            for _ in range(boundary_count):
                gold_calls.append(_create_test_case(function_def, "boundary"))

            # Generate edge cases
            for _ in range(edge_count):
                gold_calls.append(_create_test_case(function_def, "edge"))
        else:
            # Generate only normal cases
            for _ in range(count):
                gold_calls.append(_create_test_case(function_def, "normal"))

    return gold_calls


def save_gold_standard(gold_calls: list[dict[str, Any]], output_file: str | Path) -> Path:
    """Save generated gold standard to file.

    Args:
        gold_calls: List of gold standard test cases
        output_file: Output file path

    Returns:
        Path to saved file
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        json.dump(gold_calls, f, indent=2)

    return output_path
