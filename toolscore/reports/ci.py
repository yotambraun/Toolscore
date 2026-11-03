"""SARIF 2.1.0 and JUnit XML for the commands that produce findings.

One model, two formats. Each command turns what it found into a list of
:class:`Outcome` objects (one per check: a scenario, a lint issue, a probe, a
pin difference, an honesty rule...) with a tri-state status, and
:func:`write_ci_reports` writes them as:

* **SARIF 2.1.0** (``--sarif PATH``), for GitHub code scanning and other SARIF
  viewers. A failed check is a result with ``kind: "fail"`` and the level of
  its severity (``error``, ``warning`` or ``note``); a check that could not be
  decided is ``kind: "open"`` with ``level: "none"`` (SARIF's "not enough
  information"), never a pass; passing checks are left out.
* **JUnit XML** (``--junit PATH``), for GitLab, Jenkins, Azure DevOps and any
  test-report viewer. Every check is a test case: a failed error-severity
  check is a ``<failure>``, an unknown one is ``<skipped>``, and a passing one
  is a plain test case. JUnit has no warning state, so a warning or note is a
  passing test case whose ``<system-out>`` says ``warning: ...``.

Code scanning shows a SARIF result only when it has a location. Results point
at the file the check is about (a config or instruction file with its line,
the lock file, the trace) or, for a server, at the file passed with
``--report-location``, the ``--config`` file, or the server script in the
command; see :func:`default_location`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, TypeVar
from xml.sax.saxutils import escape, quoteattr

from toolscore._cmdline import split_command

if TYPE_CHECKING:
    from collections.abc import Callable

    from toolscore.config_lint import ConfigLintReport
    from toolscore.core import EvaluationResult
    from toolscore.mcp.harness import LintIssue
    from toolscore.mcp.pin import PinReport
    from toolscore.mcp.scorecard import MCPScorecard
    from toolscore.mcp.server_diff import ServerDiff

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"

#: Outcome statuses, worst first.
STATUSES = ("fail", "warn", "note", "unknown", "pass")

_LEVELS = {"fail": "error", "warn": "warning", "note": "note"}

_DOCS = "https://yotambraun.github.io/Toolscore/docs/"


@dataclass(frozen=True)
class Outcome:
    """One check and what came of it.

    Attributes:
        check: A stable name for the check (the rule ID for a finding).
        status: ``"fail"`` (error severity), ``"warn"``, ``"note"``,
            ``"unknown"`` (could not be decided) or ``"pass"``.
        message: What was found, or what passed.
        subject: What the check is about (a tool, a call), for grouping.
        location: A file path the check is about, or ``None``.
        line: A 1-based line in that file, or ``None``.
        fix: How to fix a failure (the SARIF rule help).
    """

    check: str
    status: str
    message: str
    subject: str = ""
    location: str | None = None
    line: int | None = None
    fix: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown outcome status {self.status!r}")


def rule_description(rule: str) -> str:
    """The one-line meaning of a Toolscore rule ID, from the rule tables."""
    from toolscore.mcp.pin import PIN_RULES
    from toolscore.mcp.probes import PROBE_RULES
    from toolscore.mcp.scorecard import SCENARIO_RULES
    from toolscore.metrics.honesty import HONESTY_RULES

    for table in (HONESTY_RULES, PIN_RULES, PROBE_RULES, SCENARIO_RULES, _OTHER_RULES):
        if rule in table:
            return table[rule]
    return f"Toolscore check {rule}"


_OTHER_RULES: dict[str, str] = {
    "config-server-invalid": "an MCP host config entry is invalid or uses a removed transport",
    "config-unknown-server": "an instruction names an MCP server no config defines",
    "config-unknown-tool": "an instruction names a tool no configured server exposes",
    "config-annotation-contradiction": "an instruction contradicts a tool's annotations",
    "diff-breaking": "a change between two servers that can break an agent",
    "diff-change": "a difference between two servers",
    "lint-clean": "the tool definition has no lint issues",
    "pin-match": "the server matches its lock file",
    "config-clean": "no issues in the instruction files and host configs",
    "required-calls": "every required call was made and did not fail",
    "call-errors": "no tool call failed",
    "forbidden-calls": "no forbidden call was made",
    "credentials": "no credential in tool arguments",
    "disclosure": "every warning, unrecovered error and injected fault was disclosed",
    "escape-hatch": "no code-execution tool was used to get around a refusal",
    "side-effects": "every declared side effect was found",
    "prompt-injection": "no call followed a planted instruction and no canary leaked",
}


_HONESTY_PAGE_RULES = frozenset(
    {
        "claimed-success",
        "done-after-error",
        "undisclosed-warning",
        "escape-hatch-after-refusal",
        "injected-fault-undisclosed",
    }
)
_INJECTION_RULES = frozenset({"prompt-injection-followed", "canary-leaked", "prompt-injection"})
_EVIDENCE_CHECKS = frozenset(
    {
        "required-calls",
        "call-errors",
        "forbidden-calls",
        "credentials",
        "disclosure",
        "escape-hatch",
        "side-effects",
    }
)


def _help_uri(rule: str) -> str:
    """The documentation page for a rule."""
    if rule.startswith(("pin-", "diff-")):
        page = "pinning_diff"
    elif rule.startswith("probe-"):
        page = "effect_probes"
    elif rule.startswith("config-"):
        page = "config_lint"
    elif rule in _INJECTION_RULES:
        page = "fault_injection"
    elif rule in _HONESTY_PAGE_RULES:
        page = "honesty_checks"
    elif rule in _EVIDENCE_CHECKS:
        page = "receipts"
    else:
        page = "mcp_testing"
    return f"{_DOCS}{page}.html"


def _uri(path: str) -> str:
    """A relative POSIX URI for a path under the working directory, else the path as is."""
    candidate = Path(path)
    try:
        candidate = candidate.resolve().relative_to(Path.cwd().resolve())
    except (OSError, ValueError):
        return candidate.as_posix()
    return PurePosixPath(candidate.as_posix()).as_posix()


def default_location(
    explicit: Path | None,
    config: Path | None = None,
    command: tuple[str, ...] = (),
    pin: Path | None = None,
) -> str | None:
    """The file SARIF results about a server point to.

    The first that applies: ``--report-location``, the ``--config`` file, a
    file under the working directory named in the server command
    (``python server.py`` gives ``server.py``), the lock file. ``None`` when there is none (a remote URL
    with no config file): code scanning then does not display the results.
    """
    if explicit is not None:
        return str(explicit)
    if config is not None:
        return str(config)
    tokens: list[str] = []
    for part in command:
        try:
            tokens += split_command(part)
        except ValueError:
            tokens += part.split()
    # A file in this repository named as an argument (the script, not the
    # interpreter), else the program itself when it is such a file.
    for token in [*tokens[1:], *tokens[:1]]:
        if "://" not in token and _in_cwd(token):
            return token
    return str(pin) if pin is not None else None


def _in_cwd(token: str) -> bool:
    """Whether ``token`` names a file under the working directory."""
    path = Path(token)
    try:
        return path.is_file() and path.resolve().is_relative_to(Path.cwd().resolve())
    except (OSError, ValueError):
        return False


# -- the formats ---------------------------------------------------------------------


def to_sarif(outcomes: list[Outcome], category: str) -> dict[str, Any]:
    """A SARIF 2.1.0 log with one run.

    Args:
        outcomes: The checks; passing ones are not written.
        category: The analysis category (``runAutomationDetails.id`` prefix),
            such as ``"toolscore/mcp-test"``; GitHub uses it to keep analyses
            of different commands apart.
    """
    from toolscore import __version__

    reported = [o for o in outcomes if o.status != "pass"]
    rules: dict[str, int] = {}
    descriptors: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for outcome in reported:
        if outcome.check not in rules:
            rules[outcome.check] = len(descriptors)
            description = rule_description(outcome.check)
            level = _LEVELS.get(outcome.status, "note")
            descriptors.append(
                {
                    "id": outcome.check,
                    "name": outcome.check,
                    "shortDescription": {"text": description[:1024]},
                    "fullDescription": {"text": description[:1024]},
                    "help": {
                        "text": (outcome.fix or description)[:4096],
                        "markdown": (
                            f"{outcome.fix or description}\n\n"
                            f"[Rule documentation]({_help_uri(outcome.check)})"
                        ),
                    },
                    "helpUri": _help_uri(outcome.check),
                    "defaultConfiguration": {"level": level},
                    "properties": {"tags": ["toolscore"]},
                }
            )
        result: dict[str, Any] = {
            "ruleId": outcome.check,
            "ruleIndex": rules[outcome.check],
            "kind": "open" if outcome.status == "unknown" else "fail",
            "level": "none" if outcome.status == "unknown" else _LEVELS[outcome.status],
            "message": {"text": outcome.message or rule_description(outcome.check)},
            "partialFingerprints": {
                "toolscoreFingerprint/v1": hashlib.sha256(
                    f"{outcome.check}\x00{outcome.subject}\x00{outcome.message}".encode()
                ).hexdigest()[:32]
            },
        }
        if outcome.location:
            physical: dict[str, Any] = {"artifactLocation": {"uri": _uri(outcome.location)}}
            if outcome.line is not None and outcome.line >= 1:
                physical["region"] = {"startLine": outcome.line}
            location: dict[str, Any] = {"physicalLocation": physical}
            if outcome.subject:
                location["logicalLocations"] = [{"name": outcome.subject, "kind": "function"}]
            result["locations"] = [location]
        elif outcome.subject:
            result["locations"] = [
                {"logicalLocations": [{"name": outcome.subject, "kind": "function"}]}
            ]
        results.append(result)
    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Toolscore",
                        "version": __version__,
                        "semanticVersion": __version__,
                        "informationUri": "https://yotambraun.github.io/Toolscore/",
                        "rules": descriptors,
                    }
                },
                "automationDetails": {"id": f"{category}/"},
                "invocations": [{"executionSuccessful": True}],
                "results": results,
            }
        ],
    }


def to_junit(outcomes: list[Outcome], suite: str) -> str:
    """A JUnit XML document with one test suite and one test case per check."""
    failures = sum(1 for o in outcomes if o.status == "fail")
    skipped = sum(1 for o in outcomes if o.status == "unknown")
    cases: list[str] = []
    for outcome in outcomes:
        name = f"{outcome.check} {outcome.subject}".strip()
        classname = f"toolscore.{suite.replace(' ', '.')}"
        body = ""
        text = outcome.message or rule_description(outcome.check)
        if outcome.status == "fail":
            detail = f"{text}\n{outcome.fix}".strip()
            body = (
                f"<failure message={quoteattr(text)} type={quoteattr(outcome.check)}>"
                f"{escape(detail)}</failure>"
            )
        elif outcome.status == "unknown":
            body = f"<skipped message={quoteattr('unknown: ' + text)}/>"
        elif outcome.status in ("warn", "note"):
            level = "warning" if outcome.status == "warn" else "note"
            body = f"<system-out>{escape(f'{level}: {text}')}</system-out>"
        where = ""
        if outcome.location:
            where = f" file={quoteattr(_uri(outcome.location))}"
            if outcome.line is not None:
                where += f" line={quoteattr(str(outcome.line))}"
        cases.append(
            f'    <testcase classname={quoteattr(classname)} name={quoteattr(name)}{where} time="0">'
            + (f"\n      {body}\n    </testcase>" if body else "</testcase>")
        )
    head = f'tests="{len(outcomes)}" failures="{failures}" errors="0" skipped="{skipped}" time="0"'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<testsuites name={quoteattr('toolscore')} {head}>\n"
        f"  <testsuite name={quoteattr('toolscore ' + suite)} {head}>\n"
        + "\n".join(cases)
        + ("\n" if cases else "")
        + "  </testsuite>\n</testsuites>\n"
    )


def write_ci_reports(
    outcomes: list[Outcome],
    command: str,
    sarif: Path | None = None,
    junit: Path | None = None,
) -> list[tuple[str, Path]]:
    """Write the SARIF and/or JUnit files a command was asked for.

    Args:
        outcomes: The command's checks.
        command: The command name (``"mcp test"``), used for the SARIF
            category and the JUnit suite name.
        sarif: Where to write SARIF, or ``None``.
        junit: Where to write JUnit XML, or ``None``.

    Returns:
        ``(format, path)`` for each file written (``"SARIF"``, ``"JUnit"``).
    """
    written: list[tuple[str, Path]] = []
    if sarif is not None:
        sarif.parent.mkdir(parents=True, exist_ok=True)
        log = to_sarif(outcomes, f"toolscore/{command.replace(' ', '-')}")
        sarif.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
        written.append(("SARIF", sarif))
    if junit is not None:
        junit.parent.mkdir(parents=True, exist_ok=True)
        junit.write_text(to_junit(outcomes, command), encoding="utf-8")
        written.append(("JUnit", junit))
    return written


# -- from each command's results --------------------------------------------------------


def _lint_status(severity: str) -> str:
    return {"error": "fail", "warning": "warn"}.get(severity, "note")


def outcomes_from_lint(
    issues: list[LintIssue], tools: list[str], location: str | None
) -> list[Outcome]:
    """Lint issues, plus one passing check per tool without any."""
    outcomes = [
        Outcome(
            check=issue.rule or "lint",
            status=_lint_status(issue.severity),
            message=f"{issue.tool}: {issue.message}" if issue.tool else issue.message,
            subject=issue.tool,
            location=location,
            fix=issue.fix,
        )
        for issue in issues
    ]
    flagged = {issue.tool for issue in issues}
    outcomes.extend(
        Outcome("lint-clean", "pass", f"{tool}: no lint issues", tool, location)
        for tool in tools
        if tool not in flagged
    )
    return outcomes


def outcomes_from_scorecard(card: MCPScorecard, location: str | None) -> list[Outcome]:
    """Scenarios, lint issues, scenario findings and effect probes of a scorecard."""
    from toolscore.mcp.scorecard import scenario_findings

    outcomes: list[Outcome] = []
    for result in card.results:
        scenario = result.scenario
        happy = scenario.kind == "happy"
        check = "happy-path" if happy else "edge-case"
        name = f"{scenario.tool}: {scenario.description}"
        if result.status == "input_required":
            outcomes.append(
                Outcome(check, "unknown", f"{name}: {result.detail}", scenario.tool, location)
            )
        elif result.ok:
            outcomes.append(Outcome(check, "pass", name, scenario.tool, location))
        else:
            what = "fails on valid input" if happy else "crashes on bad input"
            outcomes.append(
                Outcome(
                    "happy-path-failed" if happy else "edge-case-crashed",
                    "fail",
                    f"{name}: {what} ({result.detail})",
                    scenario.tool,
                    location,
                    fix=(
                        "Check the handler and that the input schema matches what the tool accepts."
                        if happy
                        else "Validate arguments and return a clean error result instead of "
                        "crashing or timing out."
                    ),
                )
            )
    for finding in scenario_findings(card):
        outcomes.append(
            Outcome(
                finding["rule"],
                {"warning": "warn", "note": "note"}.get(finding["severity"], "warn"),
                f"{finding['tool']}: {finding['message']}",
                finding["tool"],
                location,
                fix=finding["fix"],
            )
        )
    outcomes.extend(outcomes_from_lint(card.lint, [t.name for t in card.tools], location))
    for probe in card.probes or []:
        name = probe.rule or f"probe-{probe.probe}"
        text = f"{probe.tool}: {probe.message}"
        if probe.status == "fail":
            status = "fail" if probe.severity == "error" else "warn"
        elif probe.status == "pass":
            status = "pass"
        else:  # inconclusive or skipped: never a pass
            status = "unknown"
            text = f"{text} ({probe.status})"
        outcomes.append(Outcome(name, status, text, probe.tool, location, fix=probe.fix))
    return outcomes


def outcomes_from_pin(report: PinReport, location: str | None) -> list[Outcome]:
    """Pin differences: the ones that fail under ``--fail-on`` are errors, the rest notes."""
    failing = {id(f) for f in report.failing}
    outcomes = [
        Outcome(
            finding.rule,
            "fail" if id(finding) in failing else "note",
            f"{finding.tool}: {finding.message}" if finding.tool else finding.message,
            finding.tool,
            location,
            fix="Review the change; if it is intended, re-pin with `toolscore mcp pin`.",
        )
        for finding in report.findings
    ]
    if not outcomes:
        outcomes.append(Outcome("pin-match", "pass", "the server matches its lock", "", location))
    return outcomes


def outcomes_from_diff(diff: ServerDiff, fail_on: str, location: str | None) -> list[Outcome]:
    """Breaking changes, other differences and new lint issues between two servers."""
    breaking = diff.breaking
    outcomes = [
        Outcome(
            "diff-breaking",
            "fail" if fail_on in ("any", "breaking") else "note",
            reason,
            "",
            location,
        )
        for reason in breaking
    ]
    others: list[str] = [f"tool {name!r} added" for name in diff.added]
    others += [f"{c.tool}: {', '.join(c.fields)} changed" for c in diff.changed if not c.breaking]
    others += list(diff.server_changes)
    outcomes += [
        Outcome("diff-change", "fail" if fail_on == "any" else "note", text, "", location)
        for text in others
    ]
    outcomes += [
        o
        for o in outcomes_from_lint(diff.lint_new, [], location)
        if not (o.status == "fail" and any(o.check in r for r in breaking))
    ]
    if not outcomes:
        outcomes.append(
            Outcome("diff-change", "pass", f"{diff.a} and {diff.b} match", "", location)
        )
    return outcomes


def outcomes_from_config_lint(report: ConfigLintReport) -> list[Outcome]:
    """Config-lint issues with their file and line; skipped rules are unknown."""
    outcomes = [
        Outcome(
            issue.rule,
            _lint_status(issue.severity),
            issue.message,
            "",
            issue.path,
            issue.line,
            issue.fix,
        )
        for issue in report.issues
    ]
    outcomes += [
        Outcome(rule, "unknown", f"not checked: {reason}")
        for rule, reason in report.skipped_rules.items()
    ]
    if not report.issues:
        outcomes.append(Outcome("config-clean", "pass", "no issues found"))
    return outcomes


#: The ``false_success`` count that tells whether an honesty rule could be checked.
_HONESTY_COUNTS = {
    "claimed-success": "claimed_success",
    "done-after-error": "done_after_error",
    "undisclosed-warning": "undisclosed_warning",
    "escape-hatch-after-refusal": "escape_hatch",
    "injected-fault-undisclosed": "injected_undisclosed",
}


def outcomes_from_honesty(report: dict[str, Any], location: str | None) -> list[Outcome]:
    """Honesty findings, and for each rule that did not fire: pass, or unknown without evidence."""
    outcomes: list[Outcome] = []
    for finding in report.get("findings", []):
        rule = str(finding.get("rule", ""))
        if finding.get("confidence") == "unknown":
            status = "unknown"
        else:
            status = "fail" if finding.get("severity") == "error" else "warn"
        call = finding.get("call")
        outcomes.append(
            Outcome(
                rule,
                status,
                str(finding.get("message", "")),
                f"call {call} {finding.get('tool')}" if call else "",
                location,
            )
        )
    counts = report.get("false_success") or {}
    for rule, key in _HONESTY_COUNTS.items():
        if any(o.check == rule for o in outcomes):
            continue
        value = counts.get(key)
        if value is None:
            why = (
                "the final answer is not in English"
                if report.get("answer_language") == "other"
                else "no tool results in the trace"
                if report.get("results") == "missing"
                else "no final answer in the trace"
            )
            outcomes.append(Outcome(rule, "unknown", f"not checked: {why}", "", location))
        else:
            outcomes.append(Outcome(rule, "pass", rule_description(rule), "", location))
    planted = report.get("prompt_injection") or {}
    if planted.get("planted"):
        for rule, value in (
            ("prompt-injection-followed", planted.get("followed")),
            ("canary-leaked", planted.get("canary_leaked")),
        ):
            if any(o.check == rule for o in outcomes):
                continue
            if value is None:
                text = "not checked: no final answer to look for the canary in"
                outcomes.append(Outcome(rule, "unknown", text, "", location))
            else:
                outcomes.append(Outcome(rule, "pass", rule_description(rule), "", location))
    return outcomes


def outcomes_from_evaluation(result: EvaluationResult, location: str | None) -> list[Outcome]:
    """The tri-state evidence checks of an evaluation (``toolscore eval``)."""
    from toolscore.evidence import evaluation_evidence

    status = {"pass": "pass", "fail": "fail", "unknown": "unknown"}
    return [
        Outcome(
            str(check["check"]),
            status.get(str(check["status"]), "unknown"),
            str(check["detail"]),
            "",
            location,
        )
        for check in evaluation_evidence(result)["checks"]
    ]


# -- the shared command-line options -------------------------------------------------


_Command = TypeVar("_Command", bound="Callable[..., Any]")


def ci_report_options(location: bool = False) -> Callable[[_Command], _Command]:
    """Add ``--sarif PATH`` and ``--junit PATH`` (and ``--report-location FILE``) to a command."""
    import click

    options = [
        click.option(
            "--sarif",
            "sarif_path",
            type=click.Path(path_type=Path),  # type: ignore[type-var]
            default=None,
            help="Also write the findings as SARIF 2.1.0 (GitHub code scanning).",
        ),
        click.option(
            "--junit",
            "junit_path",
            type=click.Path(path_type=Path),  # type: ignore[type-var]
            default=None,
            help="Also write every check as JUnit XML (GitLab, Jenkins, other CI test reports).",
        ),
    ]
    if location:
        options.append(
            click.option(
                "--report-location",
                type=click.Path(path_type=Path),  # type: ignore[type-var]
                default=None,
                help=(
                    "File the SARIF and JUnit results point to (default: the --config file, or "
                    "a file in the server command such as server.py, or the lock file)."
                ),
            )
        )

    def decorate(func: _Command) -> _Command:
        for option in reversed(options):
            func = option(func)
        return func

    return decorate
