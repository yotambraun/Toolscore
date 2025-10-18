"""Schema validation for tool call arguments.

This module provides validation of tool arguments against JSON-like schemas
without requiring external dependencies like Pydantic or jsonschema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.adapters.base import ToolCall


class SchemaValidationError(Exception):
    """Raised when schema validation fails."""

    pass


def validate_argument_schema(
    call: ToolCall,
    schema: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Validate tool call arguments against a schema.

    Args:
        call: Tool call to validate
        schema: Schema definition for arguments
            Format: {
                "arg_name": {
                    "type": "string" | "integer" | "number" | "boolean" | "array" | "object",
                    "required": bool (default: True),
                    "minimum": number (for numbers),
                    "maximum": number (for numbers),
                    "minLength": int (for strings),
                    "maxLength": int (for strings),
                    "pattern": str (regex pattern for strings),
                    "enum": list (allowed values),
                }
            }

    Returns:
        Tuple of (is_valid, list_of_errors)

    Example:
        >>> schema = {
        ...     "query": {"type": "string", "minLength": 1},
        ...     "limit": {"type": "integer", "minimum": 1, "maximum": 100, "required": False}
        ... }
        >>> call = ToolCall(tool="search", args={"query": "test", "limit": 10})
        >>> is_valid, errors = validate_argument_schema(call, schema)
        >>> is_valid
        True
    """
    errors = []
    args = call.args or {}

    # Check for missing required arguments
    for arg_name, arg_schema in schema.items():
        is_required = arg_schema.get("required", True)

        if is_required and arg_name not in args:
            errors.append(f"Missing required argument: {arg_name}")
            continue

        if arg_name not in args:
            # Optional argument not provided
            continue

        # Validate the argument value
        value = args[arg_name]
        arg_errors = _validate_value(value, arg_schema, arg_name)
        errors.extend(arg_errors)

    return (len(errors) == 0, errors)


def _validate_value(value: Any, schema: dict[str, Any], arg_name: str) -> list[str]:
    """Validate a single value against schema rules.

    Args:
        value: The value to validate
        schema: Schema rules for this value
        arg_name: Name of the argument (for error messages)

    Returns:
        List of validation errors
    """
    errors = []
    expected_type = schema.get("type")

    # Type validation
    if expected_type and not _check_type(value, expected_type):
        errors.append(
            f"Argument '{arg_name}' has wrong type: expected {expected_type}, "
            f"got {type(value).__name__}"
        )
        return errors  # Don't check other constraints if type is wrong

    # Enum validation
    if "enum" in schema:
        allowed_values = schema["enum"]
        if value not in allowed_values:
            errors.append(
                f"Argument '{arg_name}' has invalid value: {value!r} "
                f"not in {allowed_values}"
            )

    # Numeric constraints
    if expected_type in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(
                f"Argument '{arg_name}' is below minimum: {value} < {schema['minimum']}"
            )
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(
                f"Argument '{arg_name}' exceeds maximum: {value} > {schema['maximum']}"
            )

    # String constraints
    if expected_type == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(
                f"Argument '{arg_name}' is too short: {len(value)} < {schema['minLength']}"
            )
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(
                f"Argument '{arg_name}' is too long: {len(value)} > {schema['maxLength']}"
            )
        if "pattern" in schema:
            import re

            pattern = schema["pattern"]
            if not re.match(pattern, value):
                errors.append(
                    f"Argument '{arg_name}' doesn't match pattern: {pattern}"
                )

    # Array constraints
    if expected_type == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(
                f"Argument '{arg_name}' has too few items: {len(value)} < {schema['minItems']}"
            )
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(
                f"Argument '{arg_name}' has too many items: {len(value)} > {schema['maxItems']}"
            )

    return errors


def _check_type(value: Any, expected_type: str) -> bool:
    """Check if a value matches the expected type.

    Args:
        value: Value to check
        expected_type: Expected type name

    Returns:
        True if type matches
    """
    type_checkers = {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
        "null": lambda v: v is None,
    }

    checker = type_checkers.get(expected_type)
    if checker is None:
        return True  # Unknown type, don't validate

    return checker(value)


def calculate_schema_validation_metrics(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
) -> dict[str, Any]:
    """Calculate schema validation metrics for all calls.

    This requires that gold_calls have a "schema" key in their metadata.

    Args:
        gold_calls: Expected tool calls with schema definitions
        trace_calls: Actual tool calls from agent

    Returns:
        Dictionary containing:
        - schema_compliance_rate: Proportion of calls passing validation
        - total_validated: Number of calls validated
        - total_errors: Total number of validation errors
        - failed_calls: List of calls that failed validation
        - error_details: Detailed error messages per call

    Example:
        >>> gold = [ToolCall(
        ...     tool="search",
        ...     args={"query": "test"},
        ...     metadata={"schema": {"query": {"type": "string", "minLength": 1}}}
        ... )]
        >>> trace = [ToolCall(tool="search", args={"query": ""})]
        >>> metrics = calculate_schema_validation_metrics(gold, trace)
        >>> metrics["schema_compliance_rate"]
        0.0  # Failed because query is too short
    """
    total_validated = 0
    total_errors = 0
    failed_calls = []
    error_details = []

    # Create a mapping of tool names to schemas
    schema_map: dict[str, dict[str, Any]] = {}
    for gold_call in gold_calls:
        schema = gold_call.metadata.get("schema")
        if schema:
            schema_map[gold_call.tool] = schema

    # Validate trace calls
    for trace_call in trace_calls:
        schema = schema_map.get(trace_call.tool)
        if not schema:
            continue  # No schema defined for this tool

        total_validated += 1
        is_valid, errors = validate_argument_schema(trace_call, schema)

        if not is_valid:
            total_errors += len(errors)
            failed_calls.append(
                {
                    "tool": trace_call.tool,
                    "args": trace_call.args,
                    "errors": errors,
                }
            )
            error_details.extend([f"{trace_call.tool}: {err}" for err in errors])

    schema_compliance_rate = (
        (total_validated - len(failed_calls)) / total_validated if total_validated > 0 else 1.0
    )

    return {
        "schema_compliance_rate": schema_compliance_rate,
        "total_validated": total_validated,
        "total_errors": total_errors,
        "failed_count": len(failed_calls),
        "failed_calls": failed_calls,
        "error_details": error_details,
    }
