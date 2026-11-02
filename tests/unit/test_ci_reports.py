"""SARIF 2.1.0 and JUnit XML output (toolscore.reports.ci) for the commands with findings."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from toolscore.cli import main
from toolscore.mcp import LintIssue, MCPScorecard, MCPToolDef, Scenario, ScenarioResult
from toolscore.reports.ci import (
    Outcome,
    default_location,
    outcomes_from_honesty,
    outcomes_from_scorecard,
    to_junit,
    to_sarif,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
EXAMPLES = ROOT / "examples"

# The official schema (OASIS SARIF 2.1.0 errata 01), vendored unchanged from
# https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json
SARIF_SCHEMA = json.loads((FIXTURES / "sarif-schema-2.1.0.json").read_text(encoding="utf-8"))


# -- a JSON Schema draft-04 validator for the keywords the SARIF schema uses ----------------

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


def _is_type(value: Any, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/definitions/"), ref
        schema = SARIF_SCHEMA["definitions"][ref.split("/")[-1]]
    return schema


def _errors(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    schema = _resolve(schema)
    errors: list[str] = []
    kinds = schema.get("type")
    if kinds is not None:
        names = kinds if isinstance(kinds, list) else [kinds]
        if not any(_is_type(value, n) for n in names):
            return [f"{path}: expected {kinds}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    for keyword in ("anyOf", "oneOf"):
        if keyword in schema:
            matches = sum(1 for sub in schema[keyword] if not _errors(value, sub, path))
            if matches == 0 or (keyword == "oneOf" and matches > 1):
                errors.append(f"{path}: {keyword} matched {matches} branches")
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: missing required {name!r}")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                errors += _errors(item, properties[key], f"{path}.{key}")
            elif extra is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(extra, dict):
                errors += _errors(item, extra, f"{path}.{key}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if schema.get("uniqueItems"):
            dumped = [json.dumps(v, sort_keys=True) for v in value]
            if len(set(dumped)) != len(dumped):
                errors.append(f"{path}: items are not unique")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                errors += _errors(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{path}: does not match {schema['pattern']!r}")
    return errors


def assert_valid_sarif(log: dict[str, Any]) -> None:
    errors = _errors(log, SARIF_SCHEMA)
    assert not errors, errors[:10]
    # Rules GitHub code scanning requires beyond the schema.
    for run in log["runs"]:
        rules = run["tool"]["driver"]["rules"]
        assert len({r["id"] for r in rules}) == len(rules)
        for rule in rules:
            assert rule["shortDescription"]["text"] and rule["fullDescription"]["text"]
            assert rule["help"]["text"]
        for result in run["results"]:
            assert rules[result["ruleIndex"]]["id"] == result["ruleId"]
            if result["kind"] != "fail":
                assert result["level"] == "none"  # SARIF 3.27.10


def test_the_validator_rejects_a_broken_log() -> None:
    assert _errors({"version": "2.1.0"}, SARIF_SCHEMA)  # no runs
    bad = to_sarif([Outcome("x", "fail", "m")], "toolscore/test")
    bad["runs"][0]["results"][0]["level"] = "fatal"
    assert _errors(bad, SARIF_SCHEMA)


# -- the formats -----------------------------------------------------------------------


def _card() -> MCPScorecard:
    add = MCPToolDef("add", "Add two numbers.", {"type": "object", "properties": {}})
    ask = MCPToolDef("ask", "Ask the user.", {"type": "object", "properties": {}})

    def result(tool: str, kind: str, ok: bool, **extra: Any) -> ScenarioResult:
        return ScenarioResult(
            scenario=Scenario(tool, {}, kind, f"{kind} path"), ok=ok, is_error=not ok,
            duration=0.0, detail="boom" if not ok else "ok", **extra,
        )  # fmt: skip

    results = [
        result("add", "happy", True),
        result("add", "happy", False),
        result("ask", "happy", False, input_required=True),
    ]
    lint = [LintIssue("ask", "warning", "no annotations", "Add them.", "annotations-missing")]
    return MCPScorecard(server_info={"name": "s"}, tools=[add, ask], results=results, lint=lint)


def test_scorecard_sarif_is_valid_and_reports_only_what_did_not_pass() -> None:
    outcomes = outcomes_from_scorecard(_card(), "server.py")
    log = to_sarif(outcomes, "toolscore/mcp-test")
    assert_valid_sarif(log)
    run = log["runs"][0]
    assert run["tool"]["driver"]["name"] == "Toolscore"
    assert run["automationDetails"]["id"] == "toolscore/mcp-test/"
    by_rule = {r["ruleId"]: r for r in run["results"]}
    assert by_rule["happy-path-failed"]["level"] == "error"
    assert by_rule["annotations-missing"]["level"] == "warning"
    assert (by_rule["happy-path"]["kind"], by_rule["happy-path"]["level"]) == ("open", "none")
    assert "lint-clean" not in by_rule  # passes are not results
    location = by_rule["happy-path-failed"]["locations"][0]
    assert location["physicalLocation"]["artifactLocation"]["uri"] == "server.py"
    assert location["logicalLocations"][0]["name"] == "add"


def test_junit_maps_fail_unknown_warning_and_pass() -> None:
    xml = to_junit(outcomes_from_scorecard(_card(), "server.py"), "mcp test")
    suites = ET.fromstring(xml)
    suite = suites.find("testsuite")
    assert suite is not None
    cases = suite.findall("testcase")
    assert int(suite.get("tests", "0")) == len(cases)
    failed = [c for c in cases if c.find("failure") is not None]
    skipped = [c for c in cases if c.find("skipped") is not None]
    assert (suite.get("failures"), suite.get("skipped")) == (str(len(failed)), str(len(skipped)))
    assert [c.get("name") for c in failed] == ["happy-path-failed add"]
    assert skipped[0].find("skipped").get("message", "").startswith("unknown: ")  # type: ignore[union-attr]
    warned = next(c for c in cases if c.get("name") == "annotations-missing ask")
    assert warned.findtext("system-out", "").startswith("warning: ")
    assert any(c.get("name") == "lint-clean add" and len(c) == 0 for c in cases)


def test_honesty_rules_that_did_not_fire_pass_or_are_unknown() -> None:
    from toolscore.adapters.base import ToolCall
    from toolscore.metrics.honesty import check_honesty

    failed = ToolCall("save", {}, result=None, metadata={"is_error": True, "error": "Error: x"})
    report = check_honesty([failed], "Done, no errors!")
    statuses = {o.check: o.status for o in outcomes_from_honesty(report, "trace.json")}
    assert statuses["claimed-success"] == "fail"
    assert statuses["escape-hatch-after-refusal"] == "pass"
    unknown = check_honesty([failed], None)
    statuses = {o.check: o.status for o in outcomes_from_honesty(unknown, "trace.json")}
    assert statuses["claimed-success"] == "unknown"
    assert_valid_sarif(to_sarif(outcomes_from_honesty(unknown, "trace.json"), "t"))


def test_default_location_prefers_explicit_then_config_then_a_file_in_the_command(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("server.py").write_text("")
    config = Path("mcp.json")
    assert default_location(Path("x.py"), config, ("python server.py",)) == "x.py"
    assert default_location(None, config, ("python server.py",)) == "mcp.json"
    assert default_location(None, None, ("python server.py",)) == "server.py"
    # The interpreter is not the server, and a URL is no file.
    assert default_location(None, None, (f"{sys.executable} -m server",)) is None
    assert default_location(None, None, ("https://mcp.example.com/mcp",)) is None
    assert default_location(None, None, ("uvx some-server",), Path("lock.json")) == "lock.json"


def test_an_unknown_status_is_rejected() -> None:
    with pytest.raises(ValueError):
        Outcome("x", "maybe", "m")


# -- the commands ----------------------------------------------------------------------------


def _run(args: list[str]) -> Any:
    return CliRunner().invoke(main, args, catch_exceptions=False)


def _read(sarif: Path, junit: Path) -> tuple[dict[str, Any], ET.Element]:
    log = json.loads(sarif.read_text(encoding="utf-8"))
    assert_valid_sarif(log)
    return log, ET.fromstring(junit.read_text(encoding="utf-8"))


def test_honesty_command_writes_sarif_and_junit(tmp_path: Path) -> None:
    sarif, junit = tmp_path / "h.sarif", tmp_path / "h.xml"
    trace = EXAMPLES / "honesty" / "disabled_button.json"
    result = _run(["honesty", str(trace), "--sarif", str(sarif), "--junit", str(junit)])
    assert result.exit_code == 0, result.output
    log, suites = _read(sarif, junit)
    rules = {r["ruleId"] for r in log["runs"][0]["results"]}
    assert "escape-hatch-after-refusal" in rules
    uri = log["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]
    assert uri["uri"].endswith("examples/honesty/disabled_button.json")
    assert suites.find("testsuite").get("name") == "toolscore honesty"  # type: ignore[union-attr]
    assert "SARIF:" in result.output and "JUnit:" in result.output


def test_verify_pin_points_at_the_lock(tmp_path: Path) -> None:
    sarif, junit = tmp_path / "p.sarif", tmp_path / "p.xml"
    lock = EXAMPLES / "pinning" / "notes.lock.json"
    rugpull = EXAMPLES / "pinning" / "notes-rugpull.json"
    args = ["mcp", "verify-pin", str(rugpull), "--lock", str(lock)]
    result = _run([*args, "--sarif", str(sarif), "--junit", str(junit)])
    assert result.exit_code == 1
    log, suites = _read(sarif, junit)
    rules = {r["ruleId"] for r in log["runs"][0]["results"]}
    assert {"pin-tool-added", "pin-capability-added", "pin-tool-changed"} <= rules
    assert int(suites.find("testsuite").get("failures", "0")) >= 3  # type: ignore[union-attr]


def test_lint_config_results_carry_file_and_line(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(EXAMPLES / "lint_config")
    sarif, junit = tmp_path / "c.sarif", tmp_path / "c.xml"
    args = ["lint-config", "--snapshot", "notes=notes.snapshot.json"]
    result = _run([*args, "--sarif", str(sarif), "--junit", str(junit)])
    assert result.exit_code == 1
    log, _ = _read(sarif, junit)
    located = [
        r["locations"][0]["physicalLocation"]
        for r in log["runs"][0]["results"]
        if r["ruleId"] == "config-unknown-tool"
    ]
    assert any(
        p["artifactLocation"]["uri"] == ".claude/skills/tidy-notes/SKILL.md"
        and p["region"]["startLine"] == 9
        for p in located
    )


def test_mcp_lint_and_test_point_at_the_server_script(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(ROOT)
    server = f"{sys.executable} tests/fixtures/fake_mcp_server.py"
    for command in ("lint", "test"):
        sarif, junit = tmp_path / f"{command}.sarif", tmp_path / f"{command}.xml"
        _run(["mcp", command, server, "--sarif", str(sarif), "--junit", str(junit)])
        log, suites = _read(sarif, junit)
        results = log["runs"][0]["results"]
        assert results, command
        uris = {
            r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            for r in results
            if "physicalLocation" in r["locations"][0]
        }
        assert uris == {"tests/fixtures/fake_mcp_server.py"}, command
        assert suites.find("testsuite").findall("testcase")  # type: ignore[union-attr]


def test_eval_writes_the_evidence_checks(tmp_path: Path) -> None:
    sarif, junit = tmp_path / "e.sarif", tmp_path / "e.xml"
    gold = EXAMPLES / "honesty" / "gold.json"
    trace = EXAMPLES / "honesty" / "ignored_warning.json"
    args = ["eval", str(gold), str(trace), "-o", str(tmp_path / "r.json")]
    result = _run([*args, "--sarif", str(sarif), "--junit", str(junit)])
    assert result.exit_code == 0, result.output
    log, suites = _read(sarif, junit)
    names = {c.get("name", "").split()[0] for c in suites.iter("testcase")}
    assert {"required-calls", "disclosure", "credentials"} <= names
    assert "undisclosed-warning" in {r["ruleId"] for r in log["runs"][0]["results"]}


def test_mcp_diff_reports_breaking_changes(tmp_path: Path) -> None:
    sarif, junit = tmp_path / "d.sarif", tmp_path / "d.xml"
    a = EXAMPLES / "pinning" / "notes-snapshot.json"
    b = EXAMPLES / "pinning" / "notes-rugpull.json"
    args = ["mcp", "diff", str(a), str(b), "--fail-on", "breaking"]
    result = _run([*args, "--sarif", str(sarif), "--junit", str(junit)])
    assert result.exit_code == 1
    log, _ = _read(sarif, junit)
    breaking = [r for r in log["runs"][0]["results"] if r["ruleId"] == "diff-breaking"]
    assert breaking and all(r["level"] == "error" for r in breaking)
    assert any("run_command" in r["message"]["text"] for r in breaking)
    uri = breaking[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri.endswith("notes-rugpull.json")
