"""Scenario generation handles JSON-Schema union types and is reproducible."""

from __future__ import annotations

from toolscore.generators.synthetic import generate_value_from_schema
from toolscore.mcp import generate_scenarios
from toolscore.mcp.client import MCPToolDef

# Shape published by @modelcontextprotocol/server-sequential-thinking 2026.8.31.
UNION_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "nextThoughtNeeded": {"type": ["boolean", "string"]},
        "revisesThought": {"type": "integer", "minimum": 1},
    },
    "required": ["thought", "nextThoughtNeeded"],
}

_JSON_TYPES = {
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
    "array": list,
    "object": dict,
}


def _matches(value, types):
    for t in types:
        if t == "null" and value is None:
            return True
        py = _JSON_TYPES.get(t)
        if py is None:
            continue
        if isinstance(value, bool) and t in ("integer", "number"):
            continue
        if isinstance(value, py):
            return True
    return False


def _scenarios(**kwargs):
    tool = MCPToolDef(name="think", description="d", input_schema=UNION_SCHEMA)
    return generate_scenarios([tool], **kwargs)


def test_union_type_does_not_crash_edge_generation():
    assert _scenarios(include_edge_cases=True)


def test_union_type_generates_a_value_of_a_listed_type():
    value = generate_value_from_schema("flag", {"type": ["boolean", "string"]})
    assert _matches(value, ["boolean", "string"])


def test_nullable_type_generates_the_non_null_type():
    assert isinstance(generate_value_from_schema("n", {"type": ["null", "integer"]}), int)


def test_wrong_type_edge_value_matches_none_of_the_union():
    edge = [s for s in _scenarios(include_edge_cases=True) if "wrong-type" in s.description]
    assert edge
    for s in edge:
        name = s.description.split("'")[1]
        assert not _matches(
            s.arguments[name],
            UNION_SCHEMA["properties"][name]["type"]
            if isinstance(UNION_SCHEMA["properties"][name]["type"], list)
            else [UNION_SCHEMA["properties"][name]["type"]],
        )


def test_scenarios_are_reproducible_between_runs():
    first = [(s.description, s.arguments) for s in _scenarios(cases_per_tool=5)]
    second = [(s.description, s.arguments) for s in _scenarios(cases_per_tool=5)]
    assert first == second
