"""Scenario generation, execution, and tool linting for MCP servers.

This module powers the "MCP Scorecard" harness. It turns a server's advertised
tool schemas into concrete test :class:`Scenario` objects (happy paths plus edge
cases), executes them against a live :class:`~toolscore.mcp.client.MCPStdioClient`
without ever aborting the whole run on a single failure, and statically lints the
tool schemas for common quality problems.

The pieces here are deliberately decoupled from rendering: scoring and report
formatting live in :mod:`toolscore.mcp.scorecard`, while the
:class:`~toolscore.mcp.client.MCPStdioClient` handles transport.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from toolscore.generators.synthetic import generate_value_from_schema
from toolscore.mcp.client import MCPError, MCPTimeoutError

if TYPE_CHECKING:
    from toolscore.mcp.client import MCPStdioClient, MCPToolDef

#: Minimum acceptable length for a tool description before a lint warning fires.
_MIN_DESCRIPTION_LENGTH = 10

#: Regular expression matching a ``snake_case`` (or lowercase) tool name.
_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: Maximum number of characters surfaced from an error payload in a result detail.
_DETAIL_MAX_CHARS = 200

#: Rough characters-per-token ratio used to estimate token cost without a
#: tokenizer dependency. Real tokenizers vary, but ~4 chars/token is a stable
#: approximation for the JSON tool definitions an MCP client feeds the model.
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate the token cost of a string, tokenizer-free.

    Uses a ~4-characters-per-token heuristic. This is an approximation intended
    for relative comparison and context budgeting, not exact billing.

    Args:
        text: The text to estimate.

    Returns:
        ``0`` for empty text, otherwise an estimated token count ``>= 1``.
    """
    if not text:
        return 0
    return max(1, round(len(text) / _CHARS_PER_TOKEN))


def tool_definition_tokens(tool: MCPToolDef) -> int:
    """Estimate the context-window tokens a tool's definition consumes.

    An MCP client sends each tool's name, description, and input schema to the
    model on *every* request, so verbose definitions are a real, recurring
    context cost (a documented MCP pain point). This serializes those three
    parts the way a client would and estimates the tokens via
    :func:`estimate_tokens`.

    Args:
        tool: The tool definition to measure.

    Returns:
        An estimated token count for the tool's advertised definition.
    """
    schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
    payload = json.dumps(
        {"name": tool.name, "description": tool.description or "", "inputSchema": schema},
        ensure_ascii=False,
        sort_keys=True,
    )
    return estimate_tokens(payload)


@dataclass
class Scenario:
    """A single planned tool invocation.

    Attributes:
        tool: The name of the tool to call.
        arguments: The arguments to pass to the tool.
        kind: Either ``"happy"`` (well-formed, expected to succeed) or
            ``"edge"`` (intentionally malformed/boundary input where an error
            response from the server is acceptable).
        description: Human-readable summary of what the scenario exercises.
    """

    tool: str
    arguments: dict[str, Any]
    kind: str
    description: str


@dataclass
class ScenarioResult:
    """The outcome of executing a single :class:`Scenario`.

    Attributes:
        scenario: The scenario that produced this result.
        ok: Whether the scenario is considered a pass. For ``"happy"``
            scenarios this means the call completed without ``is_error``. For
            ``"edge"`` scenarios this means the server *responded* (with or
            without an error payload) rather than crashing or timing out --
            error responses to bad input are acceptable and expected.
        is_error: Whether the tool result reported an error.
        duration: Wall-clock seconds the call took.
        detail: A short outcome string (e.g. an error message excerpt).
    """

    scenario: Scenario
    ok: bool
    is_error: bool
    duration: float
    detail: str


@dataclass
class LintIssue:
    """A single problem found while statically linting a tool schema.

    Attributes:
        tool: The name of the offending tool.
        severity: Either ``"error"`` (a real schema defect) or ``"warning"``
            (a quality nit that hurts agent ergonomics).
        message: A human-readable description of the issue.
        fix: A short, concrete suggestion for how to resolve the issue. May be
            empty for issues raised without a specific remedy.
    """

    tool: str
    severity: str
    message: str
    fix: str = ""


def _schema_is_usable(schema: dict[str, Any]) -> bool:
    """Report whether a schema is structured enough to generate arguments from.

    Args:
        schema: The tool's ``inputSchema``.

    Returns:
        ``True`` if the schema is an object schema we can introspect for
        properties; ``False`` for empty or non-object schemas.
    """
    return (
        bool(schema)
        and schema.get("type") == "object"
        and isinstance(schema.get("properties"), dict)
    )


def _happy_arguments(schema: dict[str, Any]) -> dict[str, Any]:
    """Build a well-formed argument mapping satisfying a tool's schema.

    Required properties are always populated; optional properties are included
    too so the happy path exercises the full surface.

    Args:
        schema: The tool's ``inputSchema`` (assumed usable).

    Returns:
        A mapping of argument name to a generated value.
    """
    properties: dict[str, Any] = schema.get("properties", {})
    return {
        name: generate_value_from_schema(name, prop if isinstance(prop, dict) else {}, "normal")
        for name, prop in properties.items()
    }


def _edge_arguments(schema: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """Build edge-case argument mappings for a tool, if its schema permits.

    Produces, where applicable:

    * a *missing required argument* case (drop one required property),
    * a *wrong-type* case (replace a value with a mismatched type),
    * an *empty/zero* case (empty strings, zero numbers, empty collections).

    Args:
        schema: The tool's ``inputSchema`` (assumed usable).

    Returns:
        A list of ``(arguments, description)`` tuples (possibly empty).
    """
    properties: dict[str, Any] = schema.get("properties", {})
    required: list[str] = [r for r in schema.get("required", []) if isinstance(r, str)]
    base = _happy_arguments(schema)

    cases: list[tuple[dict[str, Any], str]] = []

    # Missing required argument: drop the first required property.
    if required:
        missing = dict(base)
        missing.pop(required[0], None)
        cases.append((missing, f"missing required argument {required[0]!r}"))

    # Wrong-type value: flip the type of the first property we understand.
    if properties:
        first_name = next(iter(properties))
        first_schema = properties[first_name]
        wrong = dict(base)
        wrong[first_name] = _wrong_type_value(
            first_schema if isinstance(first_schema, dict) else {}
        )
        cases.append((wrong, f"wrong-type value for {first_name!r}"))

    # Empty/zero values for every property.
    if properties:
        empties = {
            name: _empty_value(prop if isinstance(prop, dict) else {})
            for name, prop in properties.items()
        }
        cases.append((empties, "empty strings / zero numbers"))

    return cases


def _wrong_type_value(prop_schema: dict[str, Any]) -> Any:
    """Return a value whose type deliberately mismatches ``prop_schema``.

    Args:
        prop_schema: The JSON-schema fragment for a single property.

    Returns:
        A value of an intentionally incorrect type.
    """
    prop_type = prop_schema.get("type", "string")
    if prop_type in ("number", "integer"):
        return "not_a_number"
    if prop_type == "boolean":
        return "not_a_bool"
    if prop_type in ("array", "object"):
        return "not_a_collection"
    # Default (string and unknown types): hand back a number.
    return 12345


def _empty_value(prop_schema: dict[str, Any]) -> Any:
    """Return the empty/zero value appropriate to a property's type.

    Args:
        prop_schema: The JSON-schema fragment for a single property.

    Returns:
        An empty string, zero, ``False``, or an empty collection.
    """
    prop_type = prop_schema.get("type", "string")
    return {
        "string": "",
        "number": 0,
        "integer": 0,
        "boolean": False,
        "array": [],
        "object": {},
    }.get(prop_type, "")


def generate_scenarios(
    tools: list[MCPToolDef],
    cases_per_tool: int = 3,
    include_edge_cases: bool = True,
) -> list[Scenario]:
    """Generate test scenarios for every advertised tool.

    For each tool with a usable object schema this produces up to
    ``cases_per_tool`` happy-path scenarios (well-formed arguments generated via
    :func:`~toolscore.generators.synthetic.generate_value_from_schema`, with all
    required properties present) and, when ``include_edge_cases`` is set and the
    schema permits, a handful of edge cases (missing required argument,
    wrong-type value, empty/zero values).

    Tools whose schema is empty or invalid cannot be introspected, so they each
    receive a single no-arguments scenario whose description flags the problem.

    Args:
        tools: The tool definitions to plan scenarios for.
        cases_per_tool: Number of happy-path scenarios per tool.
        include_edge_cases: Whether to also generate edge-case scenarios.

    Returns:
        The planned scenarios across all tools.
    """
    scenarios: list[Scenario] = []

    for tool in tools:
        schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}

        if not _schema_is_usable(schema):
            scenarios.append(
                Scenario(
                    tool=tool.name,
                    arguments={},
                    kind="happy",
                    description="no-args call (empty or invalid input schema)",
                )
            )
            continue

        for index in range(max(cases_per_tool, 0)):
            scenarios.append(
                Scenario(
                    tool=tool.name,
                    arguments=_happy_arguments(schema),
                    kind="happy",
                    description=f"happy path #{index + 1}",
                )
            )

        if include_edge_cases:
            for arguments, description in _edge_arguments(schema):
                scenarios.append(
                    Scenario(
                        tool=tool.name,
                        arguments=arguments,
                        kind="edge",
                        description=f"edge case: {description}",
                    )
                )

    return scenarios


def _excerpt(text: str) -> str:
    """Trim a string to a bounded length for use in result detail fields.

    Args:
        text: The text to trim.

    Returns:
        The text truncated to :data:`_DETAIL_MAX_CHARS` characters.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) <= _DETAIL_MAX_CHARS:
        return collapsed
    return collapsed[: _DETAIL_MAX_CHARS - 1] + "…"


def _content_excerpt(content: Any) -> str:
    """Extract a short human-readable excerpt from an MCP result ``content``.

    Args:
        content: The ``content`` field of an :class:`MCPToolResult`.

    Returns:
        A short text summary of the content.
    """
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return _excerpt(" ".join(parts))
    if isinstance(content, dict):
        message = content.get("message")
        if message is not None:
            return _excerpt(str(message))
    return _excerpt(str(content))


def run_scenarios(client: MCPStdioClient, scenarios: list[Scenario]) -> list[ScenarioResult]:
    """Execute every scenario against the server, never aborting on failure.

    Each scenario is called in turn. Transport problems
    (:class:`~toolscore.mcp.client.MCPError`) and timeouts
    (:class:`~toolscore.mcp.client.MCPTimeoutError`) are caught per scenario and
    recorded as a failed result rather than propagated, so one misbehaving tool
    cannot sink the whole run.

    The ``ok`` determination depends on the scenario kind:

    * ``"happy"`` scenarios are ``ok`` only if the call completed without an
      error result.
    * ``"edge"`` scenarios are ``ok`` whenever the server *responded at all*
      (an error payload is an acceptable, expected reaction to bad input); they
      fail only on a timeout or transport crash.

    Args:
        client: A started MCP client connected to the server under test.
        scenarios: The scenarios to execute.

    Returns:
        One :class:`ScenarioResult` per input scenario, in order.
    """
    results: list[ScenarioResult] = []

    for scenario in scenarios:
        try:
            result = client.call_tool(scenario.tool, scenario.arguments)
        except MCPTimeoutError as exc:
            results.append(
                ScenarioResult(
                    scenario=scenario,
                    ok=False,
                    is_error=True,
                    duration=client.timeout,
                    detail=_excerpt(f"timeout: {exc}"),
                )
            )
            continue
        except MCPError as exc:
            results.append(
                ScenarioResult(
                    scenario=scenario,
                    ok=False,
                    is_error=True,
                    duration=0.0,
                    detail=_excerpt(f"transport error: {exc}"),
                )
            )
            continue

        # For an edge case, the server merely responding (with or without an
        # error payload) counts as success; for a happy path the call must not
        # have returned an error result.
        ok = True if scenario.kind == "edge" else not result.is_error

        detail = _content_excerpt(result.content) if result.is_error else "ok"
        results.append(
            ScenarioResult(
                scenario=scenario,
                ok=ok,
                is_error=result.is_error,
                duration=result.duration,
                detail=detail,
            )
        )

    return results


# Concrete remediation hints surfaced alongside lint issues so the verdict is
# actionable ("here's what's wrong AND how to fix it"), not just diagnostic.
_FIX_DESCRIPTION = (
    "Describe what the tool does and when to use it — models choose tools by their description."
)
_FIX_SNAKE_CASE = "Rename the tool to snake_case for predictable, consistent tool selection."
_FIX_INPUT_SCHEMA = (
    "Define an object inputSchema with typed properties so clients know how to call the tool."
)
_FIX_SCHEMA_TYPE = 'Add \'"type": "object"\' to the inputSchema.'
_FIX_PROP_TYPE = (
    "Give the property a JSON-schema type (and an enum where the values are fixed) "
    "so the model does not have to guess."
)
_FIX_REQUIRED_MISSING = "List only properties that actually exist in the 'required' array."
_FIX_NO_REQUIRED = "Declare a 'required' list so callers know which parameters are mandatory."


def lint_tools(tools: list[MCPToolDef]) -> list[LintIssue]:
    """Statically lint tool schemas for common quality problems.

    Errors (real defects):

    * missing or empty ``inputSchema``,
    * schema missing a ``type``,
    * a declared property that lacks a ``type``,
    * a name in ``required`` that is absent from ``properties``.

    Warnings (ergonomic nits):

    * missing or very short (< 10 chars) description,
    * a tool name that is not ``snake_case``,
    * properties present but no ``required`` list declared.

    Each issue carries a concrete ``fix`` hint.

    Args:
        tools: The tool definitions to lint.

    Returns:
        Every issue found, across all tools.
    """
    issues: list[LintIssue] = []

    for tool in tools:
        name = tool.name
        schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}

        # -- description warnings ----------------------------------------
        description = tool.description or ""
        if not description.strip():
            issues.append(
                LintIssue(
                    tool=name,
                    severity="warning",
                    message="missing description",
                    fix=_FIX_DESCRIPTION,
                )
            )
        elif len(description.strip()) < _MIN_DESCRIPTION_LENGTH:
            issues.append(
                LintIssue(
                    tool=name,
                    severity="warning",
                    message=f"description is very short (< {_MIN_DESCRIPTION_LENGTH} chars)",
                    fix=_FIX_DESCRIPTION,
                )
            )

        # -- name warning ------------------------------------------------
        if not _SNAKE_CASE_RE.match(name):
            issues.append(
                LintIssue(
                    tool=name,
                    severity="warning",
                    message=f"tool name {name!r} is not snake_case",
                    fix=_FIX_SNAKE_CASE,
                )
            )

        # -- schema errors -----------------------------------------------
        if not schema:
            issues.append(
                LintIssue(
                    tool=name,
                    severity="error",
                    message="missing or empty inputSchema",
                    fix=_FIX_INPUT_SCHEMA,
                )
            )
            continue

        if "type" not in schema:
            issues.append(
                LintIssue(
                    tool=name,
                    severity="error",
                    message="inputSchema is missing 'type'",
                    fix=_FIX_SCHEMA_TYPE,
                )
            )

        properties = schema.get("properties")
        if isinstance(properties, dict):
            for prop_name, prop_schema in properties.items():
                if not isinstance(prop_schema, dict) or "type" not in prop_schema:
                    issues.append(
                        LintIssue(
                            tool=name,
                            severity="error",
                            message=f"property {prop_name!r} is missing a 'type'",
                            fix=_FIX_PROP_TYPE,
                        )
                    )

            required = schema.get("required")
            if isinstance(required, list):
                for req_name in required:
                    if req_name not in properties:
                        issues.append(
                            LintIssue(
                                tool=name,
                                severity="error",
                                message=(f"required property {req_name!r} is not in 'properties'"),
                                fix=_FIX_REQUIRED_MISSING,
                            )
                        )
            elif properties:
                issues.append(
                    LintIssue(
                        tool=name,
                        severity="warning",
                        message="properties defined but no 'required' list declared",
                        fix=_FIX_NO_REQUIRED,
                    )
                )

    return issues
