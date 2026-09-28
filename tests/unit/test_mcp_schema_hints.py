"""The scorecard reads the hints real MCP schemas already carry.

Shapes taken from the official reference servers (servers@f46d957): optional
pydantic fields (git), defaults and ``format: uri`` (everything), and examples
in descriptions (time).
"""

from __future__ import annotations

from toolscore.generators.synthetic import generate_value_from_schema
from toolscore.mcp import lint_tools
from toolscore.mcp.client import MCPToolDef


def _lint(properties):
    schema = {"type": "object", "properties": properties}
    return [i.message for i in lint_tools([MCPToolDef("t", "A tool.", schema)])]


def test_optional_anyof_property_is_typed():
    optional = {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None}
    assert not [m for m in _lint({"base_branch": optional}) if "missing a 'type'" in m]


def test_enum_and_ref_properties_are_typed():
    props = {"mode": {"enum": ["a", "b"]}, "item": {"$ref": "#/$defs/Item"}}
    assert not [m for m in _lint(props) if "missing a 'type'" in m]


def test_anyof_with_untyped_branch_is_still_flagged():
    props = {"x": {"anyOf": [{"type": "string"}, {"description": "anything"}]}}
    assert [m for m in _lint(props) if "missing a 'type'" in m]


def test_untyped_property_is_still_flagged():
    assert [m for m in _lint({"x": {"description": "no type"}}) if "missing a 'type'" in m]


def test_uses_schema_examples():
    schema = {"type": "string", "examples": ["Europe/London"]}
    assert generate_value_from_schema("tz", schema) == "Europe/London"


def test_uses_schema_default():
    schema = {"type": "string", "default": "README.md.gz"}
    assert generate_value_from_schema("name", schema) == "README.md.gz"


def test_uses_example_from_description():
    schema = {
        "type": "string",
        "description": "IANA timezone name (e.g., 'America/New_York', 'Europe/London').",
    }
    assert generate_value_from_schema("timezone", schema) == "America/New_York"


def test_uri_format_gets_a_url():
    value = generate_value_from_schema("data", {"type": "string", "format": "uri"})
    assert value.startswith("https://")


def test_date_time_format_gets_iso_timestamp():
    value = generate_value_from_schema("since", {"type": "string", "format": "date-time"})
    assert value[:4].isdigit() and "T" in value


def test_boundary_variation_ignores_hints():
    schema = {"type": "string", "default": "abc", "minLength": 2}
    assert generate_value_from_schema("s", schema, "boundary") == "xx"
