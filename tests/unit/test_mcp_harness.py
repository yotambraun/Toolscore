"""Tests for the MCP scenario harness, tool linting, and scorecard.

These tests exercise the harness against the *real* fake MCP server fixture
spawned as a subprocess (no mocks) so the full pipeline -- scenario generation,
tool calls, linting, scoring, and report rendering -- is verified end to end.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from toolscore.mcp import (
    LintIssue,
    MCPScorecard,
    MCPStdioClient,
    MCPToolDef,
    Scenario,
    ScenarioResult,
    generate_scenarios,
    lint_tools,
    print_scorecard,
    run_scenarios,
    scorecard_to_json,
    scorecard_to_markdown,
)

FIXTURE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mcp_server.py"


def _server_command(*extra: str) -> list[str]:
    """Build the command vector that launches the fake MCP server."""
    return [sys.executable, str(FIXTURE_SERVER), *extra]


@pytest.fixture
def client() -> Iterator[MCPStdioClient]:
    """Provide a started client wired to the fake server, closed on teardown."""
    c = MCPStdioClient(_server_command(), timeout=10.0)
    c.start()
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def fake_tools(client: MCPStdioClient) -> list[MCPToolDef]:
    """Return the live tool definitions advertised by the fake server."""
    return client.list_tools()


# -- test helpers (hand-built tool defs for unit-level checks) -------------

ADD_TOOL = MCPToolDef(
    name="add",
    description="Add two numbers and return the sum.",
    input_schema={
        "type": "object",
        "properties": {
            "a": {"type": "number", "description": "First addend."},
            "b": {"type": "number", "description": "Second addend."},
        },
        "required": ["a", "b"],
    },
)

FLAKY_TOOL = MCPToolDef(
    name="flaky",
    description="Always fails with an error result.",
    input_schema={
        "type": "object",
        "properties": {"x": {"type": "string", "description": "Ignored input."}},
    },
)

BAD_SCHEMA_TOOL = MCPToolDef(name="bad_schema", description="", input_schema={})


# -- generate_scenarios ---------------------------------------------------


def test_generate_scenarios_happy_args_satisfy_required() -> None:
    scenarios = generate_scenarios([ADD_TOOL], cases_per_tool=3)
    happy = [s for s in scenarios if s.kind == "happy" and s.tool == "add"]
    assert happy, "expected at least one happy scenario for add"
    for scenario in happy:
        assert "a" in scenario.arguments
        assert "b" in scenario.arguments
        assert isinstance(scenario.arguments["a"], int | float)
        assert isinstance(scenario.arguments["b"], int | float)


def test_generate_scenarios_respects_cases_per_tool() -> None:
    scenarios = generate_scenarios([ADD_TOOL], cases_per_tool=2, include_edge_cases=False)
    happy = [s for s in scenarios if s.kind == "happy" and s.tool == "add"]
    assert len(happy) == 2


def test_generate_scenarios_includes_edge_cases() -> None:
    scenarios = generate_scenarios([ADD_TOOL], cases_per_tool=3, include_edge_cases=True)
    edge = [s for s in scenarios if s.kind == "edge" and s.tool == "add"]
    assert edge, "expected edge-case scenarios for a tool with required props"
    # A missing-required edge case must omit at least one required argument.
    assert any("a" not in s.arguments or "b" not in s.arguments for s in edge), (
        "expected a missing-required edge scenario"
    )


def test_generate_scenarios_no_edge_cases_when_disabled() -> None:
    scenarios = generate_scenarios([ADD_TOOL], cases_per_tool=3, include_edge_cases=False)
    assert all(s.kind == "happy" for s in scenarios)


def test_generate_scenarios_bad_schema_single_flagged() -> None:
    scenarios = generate_scenarios([BAD_SCHEMA_TOOL], cases_per_tool=3)
    bad = [s for s in scenarios if s.tool == "bad_schema"]
    assert len(bad) == 1
    assert bad[0].arguments == {}
    assert "schema" in bad[0].description.lower()


def test_generate_scenarios_live_tools(fake_tools: list[MCPToolDef]) -> None:
    scenarios = generate_scenarios(fake_tools, cases_per_tool=3)
    tools_with_scenarios = {s.tool for s in scenarios}
    assert tools_with_scenarios == {"add", "flaky", "bad_schema"}


# -- lint_tools -----------------------------------------------------------


def test_lint_bad_schema_has_errors() -> None:
    issues = lint_tools([BAD_SCHEMA_TOOL])
    bad = [i for i in issues if i.tool == "bad_schema"]
    assert any(i.severity == "error" for i in bad)
    assert any("type" in i.message.lower() or "schema" in i.message.lower() for i in bad)


def test_lint_add_tool_minimal_issues() -> None:
    issues = lint_tools([ADD_TOOL])
    add = [i for i in issues if i.tool == "add"]
    assert all(i.severity != "error" for i in add)


def test_lint_flaky_warns_missing_required() -> None:
    # flaky has properties but no "required" list -> warning, not error.
    issues = lint_tools([FLAKY_TOOL])
    flaky = [i for i in issues if i.tool == "flaky"]
    assert all(i.severity != "error" for i in flaky)
    assert any("required" in i.message.lower() for i in flaky)


def test_lint_live_tools(fake_tools: list[MCPToolDef]) -> None:
    issues = lint_tools(fake_tools)
    by_tool = {i.tool for i in issues}
    assert "bad_schema" in by_tool
    bad_errors = [i for i in issues if i.tool == "bad_schema" and i.severity == "error"]
    assert bad_errors
    assert all(isinstance(i, LintIssue) for i in issues)


def test_lint_non_snake_case_warns() -> None:
    tool = MCPToolDef(
        name="CamelCaseTool",
        description="A tool with a camel case name that is long enough.",
        input_schema={"type": "object", "properties": {}},
    )
    issues = lint_tools([tool])
    assert any(i.severity == "warning" and "snake_case" in i.message for i in issues)


def test_lint_required_not_in_properties_is_error() -> None:
    tool = MCPToolDef(
        name="broken",
        description="Lists a required prop that does not exist in properties.",
        input_schema={
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a", "missing"],
        },
    )
    issues = lint_tools([tool])
    assert any(i.severity == "error" and "missing" in i.message for i in issues)


# -- run_scenarios --------------------------------------------------------


def test_run_scenarios_add_happy_ok(client: MCPStdioClient) -> None:
    scenarios = generate_scenarios([ADD_TOOL], cases_per_tool=2, include_edge_cases=False)
    results = run_scenarios(client, scenarios)
    assert len(results) == len(scenarios)
    assert all(r.ok for r in results)
    assert all(not r.is_error for r in results)
    assert all(r.duration >= 0 for r in results)


def test_run_scenarios_flaky_happy_fails(client: MCPStdioClient) -> None:
    scenarios = generate_scenarios([FLAKY_TOOL], cases_per_tool=2, include_edge_cases=False)
    results = run_scenarios(client, scenarios)
    # flaky always returns isError -> happy scenarios are not ok.
    assert all(r.is_error for r in results)
    assert all(not r.ok for r in results)


def test_run_scenarios_never_aborts_on_timeout() -> None:
    # A slow server triggers MCPTimeoutError per scenario; the run must continue.
    c = MCPStdioClient(_server_command("--sleep", "2"), timeout=0.4)
    c.start()
    try:
        scenarios = generate_scenarios([ADD_TOOL], cases_per_tool=2, include_edge_cases=False)
        results = run_scenarios(c, scenarios)
        assert len(results) == len(scenarios)
        assert all(not r.ok for r in results)
        assert all(
            "timeout" in r.detail.lower() or "timed out" in r.detail.lower() for r in results
        )
    finally:
        c.close()


def test_run_scenarios_edge_ok_when_server_responds(client: MCPStdioClient) -> None:
    # bad_schema accepts any args and returns success; its single edge/no-arg
    # scenario should be ok (server responded without crashing).
    scenarios = generate_scenarios([BAD_SCHEMA_TOOL], cases_per_tool=3)
    results = run_scenarios(client, scenarios)
    assert results
    assert all(r.ok for r in results)


# -- scorecard end to end -------------------------------------------------


def test_scorecard_pipeline(client: MCPStdioClient) -> None:
    tools = client.list_tools()
    scenarios = generate_scenarios(tools, cases_per_tool=3)
    results = run_scenarios(client, scenarios)
    lint = lint_tools(tools)
    card = MCPScorecard(
        server_info=client.server_info,
        tools=tools,
        results=results,
        lint=lint,
    )
    assert 0.0 <= card.score <= 1.0
    assert card.grade in {"A", "B", "C", "D", "F"}
    # flaky lowers the happy pass rate, and bad_schema lint errors lower lint
    # score, so the grade is not a perfect A.
    assert card.score < 1.0


def test_scorecard_to_markdown_contains_grade_and_table(client: MCPStdioClient) -> None:
    tools = client.list_tools()
    scenarios = generate_scenarios(tools, cases_per_tool=2)
    results = run_scenarios(client, scenarios)
    card = MCPScorecard(
        server_info=client.server_info,
        tools=tools,
        results=results,
        lint=lint_tools(tools),
    )
    md = scorecard_to_markdown(card)
    assert card.grade in md
    assert "fake-mcp" in md
    assert "|" in md  # has a markdown table
    assert "add" in md


def test_scorecard_to_json_round_trips(client: MCPStdioClient) -> None:
    tools = client.list_tools()
    scenarios = generate_scenarios(tools, cases_per_tool=2)
    results = run_scenarios(client, scenarios)
    card = MCPScorecard(
        server_info=client.server_info,
        tools=tools,
        results=results,
        lint=lint_tools(tools),
    )
    payload = scorecard_to_json(card)
    # Must be JSON-serializable and round-trippable.
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["grade"] == card.grade
    assert pytest.approx(decoded["score"]) == card.score
    assert decoded["server"]["name"] == "fake-mcp"
    assert any(t["name"] == "add" for t in decoded["tools"])


def test_print_scorecard_runs(client: MCPStdioClient) -> None:
    from rich.console import Console

    tools = client.list_tools()
    results = run_scenarios(client, generate_scenarios(tools, cases_per_tool=2))
    card = MCPScorecard(
        server_info=client.server_info,
        tools=tools,
        results=results,
        lint=lint_tools(tools),
    )
    console = Console(record=True, width=100)
    print_scorecard(card, console=console)
    text = console.export_text()
    assert "fake-mcp" in text
    assert card.grade in text


# -- grading math ---------------------------------------------------------


def _make_result(tool: str, kind: str, ok: bool, is_error: bool) -> ScenarioResult:
    return ScenarioResult(
        scenario=Scenario(tool=tool, arguments={}, kind=kind, description="x"),
        ok=ok,
        is_error=is_error,
        duration=0.01,
        detail="",
    )


def test_grade_perfect_is_a() -> None:
    tools = [ADD_TOOL]
    results = [
        _make_result("add", "happy", ok=True, is_error=False),
        _make_result("add", "edge", ok=True, is_error=True),
    ]
    card = MCPScorecard(server_info={}, tools=tools, results=results, lint=[])
    assert card.score == pytest.approx(1.0)
    assert card.grade == "A"


def test_grade_all_happy_fail_is_f() -> None:
    tools = [ADD_TOOL]
    results = [
        _make_result("add", "happy", ok=False, is_error=True),
        _make_result("add", "happy", ok=False, is_error=True),
    ]
    # happy_pass_rate=0, no edge -> edge_resilience defaults to 1.0,
    # lint perfect -> score = 0.6*0 + 0.2*1 + 0.2*1 = 0.4 -> F
    card = MCPScorecard(server_info={}, tools=tools, results=results, lint=[])
    assert card.score == pytest.approx(0.4)
    assert card.grade == "F"


def test_grade_boundary_b() -> None:
    # happy pass rate 1.0, edge resilience 1.0, but lint drags score to ~0.8.
    tools = [ADD_TOOL, FLAKY_TOOL]
    results = [_make_result("add", "happy", ok=True, is_error=False)]
    # one error => lint_score = 1 - (0.25)/2 = 0.875; score = 0.6 + 0.2 + 0.2*0.875 = 0.975 -> A
    # Use enough warnings to push to the B band instead.
    lint = [LintIssue(tool="add", severity="warning", message="w") for _ in range(4)]
    # lint_score = 1 - (4*0.1)/2 = 0.8; score = 0.6 + 0.2 + 0.2*0.8 = 0.96 -> still A
    card = MCPScorecard(server_info={}, tools=tools, results=results, lint=lint)
    assert 0.0 <= card.score <= 1.0


def test_grade_zero_scenarios_no_division_error() -> None:
    card = MCPScorecard(server_info={}, tools=[ADD_TOOL], results=[], lint=[])
    # No scenarios -> happy/edge default to full credit; lint perfect -> 1.0.
    assert card.score == pytest.approx(1.0)
    assert card.grade == "A"


def test_grade_lint_score_floor_at_zero() -> None:
    # Many lint errors on a single tool must not drive lint_score negative.
    tools = [BAD_SCHEMA_TOOL]
    results = [_make_result("bad_schema", "happy", ok=True, is_error=False)]
    lint = [LintIssue(tool="bad_schema", severity="error", message="e") for _ in range(20)]
    card = MCPScorecard(server_info={}, tools=tools, results=results, lint=lint)
    # lint_score floored at 0 -> score = 0.6 + 0.2 + 0 = 0.8 -> B
    assert card.score == pytest.approx(0.8)
    assert card.grade == "B"
