"""Forbidden-call policies and secret detection in tool arguments (1.10)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner
from rich.console import Console

from toolscore import Contains, OneOf, Regex, ToolScoreAssertionError, evaluate, expect
from toolscore.cli import main
from toolscore.core import evaluate_trace
from toolscore.metrics.policy import rules_from_json
from toolscore.reports import generate_markdown_report, print_evaluation_summary
from toolscore.reports.findings import behavior_findings

if TYPE_CHECKING:
    from pathlib import Path

# Fake credentials are assembled at runtime so no token-shaped literal is stored in the repo.
GITHUB_TOKEN = "ghp_" + "A1b2C3d4" * 4 + "Zz9Y"
OPENAI_KEY = "sk-" + "proj-" + "x" * 20 + "Y7" * 12
AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"
PRIVATE_KEY = (
    "-----BEGIN " + "OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXkt\n-----END OPENSSH PRIVATE KEY-----"
)

SHELL_TRACE = [
    {"tool": "run_shell", "args": {"command": "ls -la"}},
    {"tool": "run_shell", "args": {"command": "rm -rf /tmp/build"}},
    {"tool": "read_file", "args": {"path": "/home/me/.ssh/id_rsa"}},
]


# -- forbidden-call policies ----------------------------------------------------


def test_forbidden_rule_with_argument_matcher_reports_the_violating_call() -> None:
    result = evaluate(
        expected=[{"tool": "run_shell"}],
        actual=SHELL_TRACE,
        forbidden=[
            {
                "tool": "run_shell",
                "args": {"command": Regex(r".*\brm\s+-rf\b.*")},
                "reason": "destructive",
            },
            {"tool": "read_file", "args": {"path": Contains(".ssh")}},
        ],
    )

    policy = result.metrics["policy_metrics"]
    assert policy["violation_count"] == 2
    assert [(v["index"], v["tool"], v["rule"]) for v in policy["violations"]] == [
        (1, "run_shell", 0),
        (2, "read_file", 1),
    ]
    assert policy["violations"][0]["reason"] == "destructive"
    assert result.policy_violations == policy["violations"]


def test_rule_without_args_forbids_every_call_to_the_tool() -> None:
    result = evaluate(expected=[], actual=SHELL_TRACE, forbidden=[{"tool": "run_shell"}])

    assert result.metrics["policy_metrics"]["violation_count"] == 2


def test_without_rules_no_policy_was_checked() -> None:
    result = evaluate(expected=[{"tool": "run_shell"}], actual=SHELL_TRACE)

    assert "policy_metrics" not in result.metrics
    assert result.policy_violations == []


def test_policies_do_not_change_the_score() -> None:
    plain = evaluate(expected=[{"tool": "run_shell"}], actual=SHELL_TRACE)
    checked = evaluate(
        expected=[{"tool": "run_shell"}], actual=SHELL_TRACE, forbidden=[{"tool": "run_shell"}]
    )

    assert checked.score == plain.score


def test_file_based_evaluation_accepts_forbidden_rules(tmp_path: Path) -> None:
    gold, trace = tmp_path / "gold.json", tmp_path / "trace.json"
    gold.write_text(json.dumps([{"tool": "run_shell"}]))
    trace.write_text(json.dumps(SHELL_TRACE))

    result = evaluate_trace(gold, trace, format="custom", forbidden=[{"tool": "read_file"}])

    assert result.metrics["policy_metrics"]["violation_count"] == 1


def test_expect_does_not_call_with_argument_matchers() -> None:
    with pytest.raises(ToolScoreAssertionError, match="rm -rf"):
        expect(SHELL_TRACE).does_not_call("run_shell", command=Regex(r".*\brm\s+-rf\b.*")).run()

    # Only the safe command is called: the matcher-based rule passes.
    safe = [{"tool": "run_shell", "args": {"command": "ls -la"}}]
    expect(safe).does_not_call("run_shell", command=Regex(r".*\brm\s+-rf\b.*")).run()


# -- secrets in tool arguments --------------------------------------------------


def test_secrets_in_arguments_are_found_with_path_and_redacted_preview() -> None:
    actual = [
        {
            "tool": "http_request",
            "args": {
                "url": "https://api.example.com",
                "headers": {"Authorization": f"token {GITHUB_TOKEN}"},
            },
        },
        {"tool": "send_message", "args": {"text": f"here is the key: {OPENAI_KEY}"}},
        {
            "tool": "write_file",
            "args": {"files": [{"path": "deploy.env", "content": f"AWS_ACCESS_KEY_ID={AWS_KEY}"}]},
        },
        {"tool": "upload", "args": {"data": PRIVATE_KEY}},
    ]

    security = evaluate(expected=[], actual=actual).metrics["security_metrics"]

    assert security["secret_count"] == 4
    found = {(f["index"], f["kind"], f["path"]) for f in security["secrets"]}
    assert found == {
        (0, "github_token", "headers.Authorization"),
        (1, "openai_api_key", "text"),
        (2, "aws_access_key_id", "files[0].content"),
        (3, "private_key", "data"),
    }
    # Findings never repeat the secret itself (the trace's own arguments are kept as recorded).
    for secret in (GITHUB_TOKEN, OPENAI_KEY, AWS_KEY, PRIVATE_KEY):
        assert secret not in json.dumps(security)
        assert secret[4:16] not in json.dumps(security)


def test_ordinary_values_are_not_reported_as_secrets() -> None:
    actual = [
        {
            "tool": "search",
            "args": {
                "q": "task-123 ask-for-help sk-learn tutorial",
                "id": "9f86d081884c7d659a2feaa0c55ad015",
            },
        },
        {
            "tool": "lookup",
            "args": {"code": "AKIA", "uuid": "123e4567-e89b-12d3-a456-426614174000"},
        },
    ]

    security = evaluate(expected=[], actual=actual).metrics["security_metrics"]

    assert security == {"secret_count": 0, "secrets": []}


# -- JSON rules, reports and the CLI ---------------------------------------------


def test_json_rules_turn_dollar_operators_into_matchers() -> None:
    rules = rules_from_json(
        [
            {"tool": "run_shell", "args": {"command": {"$regex": r".*\brm\s+-rf\b.*"}}},
            {"tool": "read_file", "args": {"path": {"$contains": ".ssh"}}},
            {"tool": "deploy", "args": {"env": {"$one_of": ["prod", "production"]}}},
            {"tool": "set", "args": {"value": {"a": 1}}},
        ]
    )

    assert isinstance(rules[0]["args"]["command"], Regex)
    assert rules[0]["args"]["command"].matches("sudo rm -rf /")
    assert not rules[0]["args"]["command"].matches("rmdir build")
    assert isinstance(rules[1]["args"]["path"], Contains)
    assert isinstance(rules[2]["args"]["env"], OneOf)
    # A dict that is not a one-key $ operator stays an exact value.
    assert rules[3]["args"]["value"] == {"a": 1}

    trace = [*SHELL_TRACE, {"tool": "deploy", "args": {"env": "prod"}}]
    found = evaluate(expected=[], actual=trace, forbidden=rules).policy_violations
    assert [v["index"] for v in found] == [1, 2, 3]


@pytest.mark.parametrize(
    "rules",
    [
        {"tool": "x"},
        [{"args": {}}],
        [{"tool": "x", "args": {"a": {"$regex": 3}}}],
        [{"tool": "x", "args": {"a": {"$one_of": "prod"}}}],
    ],
)
def test_malformed_json_rules_are_rejected(rules: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        rules_from_json(rules)


def test_reports_list_behavior_and_safety_findings(tmp_path: Path) -> None:
    trace = [
        {"tool": "run_shell", "args": {"command": "rm -rf /"}},
        {"tool": "fetch", "args": {"url": "x"}, "is_error": True, "error": "timeout"},
        {"tool": "fetch", "args": {"url": "x"}, "is_error": True, "error": "timeout"},
        {"tool": "http_request", "args": {"headers": {"Authorization": GITHUB_TOKEN}}},
    ]
    result = evaluate(
        expected=[{"tool": "fetch"}],
        actual=trace,
        forbidden=[{"tool": "run_shell", "reason": "no shell access"}],
    )

    findings = behavior_findings(result)

    assert findings == [
        ("error", "call 1 run_shell matches forbidden rule 1: no shell access"),
        (
            "error",
            "call 4 http_request passes a github_token in 'headers.Authorization' "
            f"({GITHUB_TOKEN[:4]}…{GITHUB_TOKEN[-2:]})",
        ),
        ("warning", "2 of 4 tool calls failed (fetch x2)"),
        ("warning", "1 call(s) retried a failed call with the same arguments"),
    ]

    report = generate_markdown_report(result, tmp_path / "report.md").read_text(encoding="utf-8")
    assert "## 🛡️ Behavior and Safety" in report
    assert "matches forbidden rule 1: no shell access" in report
    assert "| Failed Calls | 2 |" in report

    console = Console(record=True, width=200)
    print_evaluation_summary(result, console=console)
    text = console.export_text()
    assert "Behavior and safety" in text
    assert "2 of 4 tool calls failed (fetch x2)" in text
    assert GITHUB_TOKEN not in text


def test_clean_trace_has_no_findings() -> None:
    result = evaluate(expected=[{"tool": "run_shell"}], actual=SHELL_TRACE[:1])

    assert behavior_findings(result) == []


def test_cli_forbidden_file_and_fail_on_violations(tmp_path: Path) -> None:
    gold, trace, rules = tmp_path / "gold.json", tmp_path / "trace.json", tmp_path / "rules.json"
    gold.write_text(json.dumps([{"tool": "run_shell"}]))
    trace.write_text(json.dumps(SHELL_TRACE))
    rules.write_text(json.dumps([{"tool": "read_file", "args": {"path": {"$contains": ".ssh"}}}]))
    out = tmp_path / "report.json"
    base = ["eval", str(gold), str(trace), "-o", str(out), "--forbidden", str(rules)]

    reported = CliRunner().invoke(main, base)
    assert reported.exit_code == 0, reported.output
    assert "call 3 read_file matches forbidden rule 1" in reported.output
    assert json.loads(out.read_text())["metrics"]["policy_metrics"]["violation_count"] == 1

    failed = CliRunner().invoke(main, [*base, "--fail-on-violations"])
    assert failed.exit_code == 1
    assert "--fail-on-violations" in failed.output

    clean = tmp_path / "clean.json"
    clean.write_text(json.dumps(SHELL_TRACE[:1]))
    passed = CliRunner().invoke(
        main,
        [
            "eval",
            str(gold),
            str(clean),
            "-o",
            str(out),
            "--forbidden",
            str(rules),
            "--fail-on-violations",
        ],
    )
    assert passed.exit_code == 0, passed.output
