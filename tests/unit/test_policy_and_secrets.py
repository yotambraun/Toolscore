"""Forbidden-call policies and secret detection in tool arguments (1.10)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from toolscore import Contains, Regex, ToolScoreAssertionError, evaluate, expect
from toolscore.core import evaluate_trace

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
