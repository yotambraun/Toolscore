"""Split a command line the way the user's platform does."""

from __future__ import annotations

import shlex
import subprocess
import sys

__all__ = ["join_command", "split_command"]


def split_command(command: str) -> list[str]:
    """Tokens of ``command``: POSIX shell rules, or Windows rules on Windows.

    ``shlex.split`` treats a backslash as an escape, which turns a Windows path
    such as ``C:\\Python\\python.exe`` into ``C:Pythonpython.exe``. On Windows the
    line is split as ``CommandLineToArgvW`` does, the inverse of
    ``subprocess.list2cmdline``.
    """
    if sys.platform != "win32":
        return shlex.split(command)
    return _split_windows(command)


def join_command(argv: list[str]) -> str:
    """One command line for ``argv`` that :func:`split_command` splits back into ``argv``."""
    return subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)


def _split_windows(command: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    in_token = in_quotes = False
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if ch == "\\":
            j = i
            while j < n and command[j] == "\\":
                j += 1
            count = j - i
            if j < n and command[j] == '"':
                # 2k backslashes + quote: k backslashes, the quote toggles; 2k+1: k and a literal quote
                current.append("\\" * (count // 2))
                if count % 2:
                    current.append('"')
                    j += 1
                i = j
            else:
                current.append("\\" * count)
                i = j
            in_token = True
            continue
        if ch == '"':
            if in_quotes and i + 1 < n and command[i + 1] == '"':
                current.append('"')  # "" inside quotes is a literal quote
                i += 2
                continue
            in_quotes = not in_quotes
            in_token = True
            i += 1
            continue
        if ch in " \t" and not in_quotes:
            if in_token:
                tokens.append("".join(current))
                current, in_token = [], False
            i += 1
            continue
        current.append(ch)
        in_token = True
        i += 1
    if in_token:
        tokens.append("".join(current))
    return tokens
