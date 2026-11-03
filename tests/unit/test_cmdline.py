"""split_command: POSIX rules, Windows rules on Windows."""

from __future__ import annotations

import subprocess
import sys

import pytest

from toolscore._cmdline import _split_windows, join_command, split_command

CASES = [
    ["C:\\Python312\\python.exe", "-m", "toolscore.mcp.sample_server"],
    ["C:\\Program Files\\node\\node.exe", "server.js", "--root", "C:\\data dir\\"],
    ["python", "server.py", "--instructions", "Always use 'missing_tool' first."],
    ["tool", 'say "hi"', "a\\\\b", "trailing\\", ""],
]


@pytest.mark.parametrize("argv", CASES)
def test_windows_split_inverts_list2cmdline(argv: list[str]) -> None:
    assert _split_windows(subprocess.list2cmdline(argv)) == argv


def test_unquoted_windows_paths_keep_their_backslashes() -> None:
    assert _split_windows("C:\\Python312\\python.exe -m pkg") == [
        "C:\\Python312\\python.exe",
        "-m",
        "pkg",
    ]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX rules")
def test_posix_rules_elsewhere() -> None:
    assert split_command("npx -y '@scope/server' --dir \"a b\"") == [
        "npx",
        "-y",
        "@scope/server",
        "--dir",
        "a b",
    ]


@pytest.mark.parametrize("argv", CASES)
def test_join_and_split_round_trip_on_this_platform(argv: list[str]) -> None:
    assert split_command(join_command(argv)) == argv
