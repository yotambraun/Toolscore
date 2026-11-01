"""A small, conservative JSON Schema check for ``structuredContent``.

MCP tools may declare an ``outputSchema``; a server must then return
``structuredContent`` that conforms to it. :func:`validate_instance` checks the
keywords that decide the shape of a value -- ``type``, ``properties``,
``required``, ``additionalProperties: false``, ``items``, ``enum``, ``const``,
``anyOf``/``oneOf``/``allOf`` -- plus the common length and range bounds.

It is deliberately incomplete in one direction only: keywords it does not know
(``$ref``, ``pattern``, ``format``, ``if``/``then``...) are not judged, so it
never reports a mismatch that a full validator would not. Standard library only.
"""

from __future__ import annotations

from typing import Any

#: Nesting depth beyond which validation stops (guards against hostile schemas).
_MAX_DEPTH = 32

#: Most errors reported for one value.
_MAX_ERRORS = 20


def _type_matches(value: Any, expected: str) -> bool | None:
    """Whether ``value`` has JSON type ``expected`` (``None`` for unknown types)."""
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or (
            isinstance(value, float) and value.is_integer()
        )
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return None


def _json_type(value: Any) -> str:
    """The JSON type name of a Python value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def validate_instance(value: Any, schema: Any) -> list[str]:
    """Validate ``value`` against ``schema`` and return readable errors.

    Args:
        value: The instance (for example a result's ``structuredContent``).
        schema: The JSON Schema (for example a tool's ``outputSchema``).

    Returns:
        Error strings with a JSON-pointer-like path (``$.items[0].id: ...``);
        empty when the value conforms (or the schema uses only unknown keywords).
    """
    errors: list[str] = []
    _validate(value, schema, "$", errors, 0)
    return errors[:_MAX_ERRORS]


def _validate(value: Any, schema: Any, path: str, errors: list[str], depth: int) -> None:
    """Append the errors of ``value`` against ``schema`` at ``path``."""
    if depth > _MAX_DEPTH or len(errors) >= _MAX_ERRORS:
        return
    if schema is False:
        errors.append(f"{path}: no value is allowed here")
        return
    if not isinstance(schema, dict):
        return

    expected = schema.get("type")
    types = [expected] if isinstance(expected, str) else expected
    if isinstance(types, list) and types:
        verdicts = [_type_matches(value, t) for t in types if isinstance(t, str)]
        if verdicts and None not in verdicts and not any(verdicts):
            wanted = " or ".join(t for t in types if isinstance(t, str))
            errors.append(f"{path}: expected {wanted}, got {_json_type(value)}")
            return

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected the constant {schema['const']!r}")
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        errors.append(f"{path}: {value!r} is not one of {enum!r}")

    _check_bounds(value, schema, path, errors)

    if isinstance(value, dict):
        _validate_object(value, schema, path, errors, depth)
    elif isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, (dict, bool)):
            for index, item in enumerate(value):
                _validate(item, items, f"{path}[{index}]", errors, depth + 1)

    for key in ("anyOf", "oneOf"):
        branches = schema.get(key)
        if isinstance(branches, list) and branches:
            outcomes = []
            for branch in branches:
                branch_errors: list[str] = []
                _validate(value, branch, path, branch_errors, depth + 1)
                outcomes.append(branch_errors)
            if all(outcomes):
                errors.append(f"{path}: matches none of the {key} alternatives ({outcomes[0][0]})")
    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for branch in all_of:
            _validate(value, branch, path, errors, depth + 1)


def _validate_object(
    value: dict[str, Any], schema: dict[str, Any], path: str, errors: list[str], depth: int
) -> None:
    """Check ``required``, ``properties`` and ``additionalProperties``."""
    required = schema.get("required")
    if isinstance(required, list):
        for name in required:
            if isinstance(name, str) and name not in value:
                errors.append(f"{path}: missing required property {name!r}")
    properties = schema.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    for name, prop_schema in properties.items():
        if name in value:
            _validate(value[name], prop_schema, f"{path}.{name}", errors, depth + 1)
    additional = schema.get("additionalProperties")
    if "patternProperties" in schema:
        return  # extra keys may match a pattern, which is not judged here
    extras = [k for k in value if k not in properties]
    if additional is False and extras:
        errors.append(f"{path}: unexpected property {extras[0]!r}")
    elif isinstance(additional, dict):
        for name in extras:
            _validate(value[name], additional, f"{path}.{name}", errors, depth + 1)


def _check_bounds(value: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    """Check string length, numeric range and array/object size bounds."""

    def bound(key: str) -> float | None:
        raw = schema.get(key)
        return raw if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None

    if isinstance(value, str):
        low, high = bound("minLength"), bound("maxLength")
        if low is not None and len(value) < low:
            errors.append(f"{path}: shorter than minLength {low}")
        if high is not None and len(value) > high:
            errors.append(f"{path}: longer than maxLength {high}")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
            limit = bound(key)
            if limit is None:
                continue
            fails = {
                "minimum": number < limit,
                "maximum": number > limit,
                "exclusiveMinimum": number <= limit,
                "exclusiveMaximum": number >= limit,
            }[key]
            if fails:
                errors.append(f"{path}: {value!r} violates {key} {limit}")
    elif isinstance(value, list):
        low, high = bound("minItems"), bound("maxItems")
        if low is not None and len(value) < low:
            errors.append(f"{path}: fewer than minItems {low}")
        if high is not None and len(value) > high:
            errors.append(f"{path}: more than maxItems {high}")
