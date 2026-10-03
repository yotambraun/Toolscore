"""Detect credentials passed into tool arguments.

An agent that copies an API key, token or private key into a tool call can leak
it to whatever the tool talks to (an HTTP request, a message, a file, a
third-party API). This check scans every string in every call's arguments, at any
depth, for credential formats with distinctive prefixes, so ordinary values are
not reported. Findings carry the argument path and a redacted preview, never the
credential itself.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

    from toolscore.adapters.base import ToolCall

#: (kind, pattern), most specific first; a span claimed by one kind is not reported again.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")),
    ("anthropic_api_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai_api_key", re.compile(r"\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{32,}")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b")),
    ("github_token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}")),
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}")),
    ("stripe_secret_key", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{24,}")),
)


def _strings(value: Any, path: str) -> Iterator[tuple[str, str]]:
    """Yield ``(path, string)`` for every string inside an argument value."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, (list, tuple)):
        for position, item in enumerate(value):
            yield from _strings(item, f"{path}[{position}]")


#: Kinds whose formats are only a prefix plus a charset: also require the mix of
#: digits and both letter cases that random keys have, so slugs and identifiers
#: such as ``sk-some-very-long-kebab-case-identifier-name`` are not reported.
_RANDOM_KINDS = frozenset({"anthropic_api_key", "openai_api_key"})


def _looks_random(secret: str) -> bool:
    return (
        any(c.isdigit() for c in secret)
        and any(c.islower() for c in secret)
        and any(c.isupper() for c in secret)
    )


def _matches(text: str) -> Iterator[tuple[str, re.Match[str]]]:
    """Yield ``(kind, match)`` for each credential in ``text``, without overlaps."""
    claimed: list[tuple[int, int]] = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < c_end and c_start < end for c_start, c_end in claimed):
                continue
            if kind in _RANDOM_KINDS and not _looks_random(match.group(0)):
                continue
            claimed.append((start, end))
            yield kind, match


def redact_secrets(text: str) -> str:
    """Replace every credential in ``text`` with its redacted preview.

    Used for reports that may be published (Markdown job summaries, HTML), so a
    credential found in a trace is not copied into them in full.

    Args:
        text: Any text.

    Returns:
        The text with each credential replaced by ``[REDACTED kind: preview]``.
    """
    spans = sorted(
        ((m.start(), m.end(), kind, m.group(0)) for kind, m in _matches(text)),
        reverse=True,
    )
    for start, end, kind, secret in spans:
        text = f"{text[:start]}[REDACTED {kind}: {_preview(kind, secret)}]{text[end:]}"
    return text


def _preview(kind: str, secret: str) -> str:
    """A redacted preview that identifies the credential without revealing it."""
    if kind == "private_key":
        return "-----BEGIN … PRIVATE KEY-----"
    return f"{secret[:4]}…{secret[-2:]}"


def find_secrets(trace_calls: list[ToolCall]) -> dict[str, Any]:
    """Find credentials in tool arguments.

    Args:
        trace_calls: The actual tool calls, in order.

    Returns:
        ``secret_count`` and ``secrets``: one entry per credential with the call
        ``index``, ``tool``, argument ``path`` (``headers.Authorization``,
        ``files[0].content``), ``kind`` and a redacted ``preview``.
    """
    findings: list[dict[str, Any]] = []
    for index, call in enumerate(trace_calls):
        for path, text in _strings(call.args or {}, ""):
            for kind, match in _matches(text):
                findings.append(
                    {
                        "index": index,
                        "tool": call.tool,
                        "path": path,
                        "kind": kind,
                        "preview": _preview(kind, match.group(0)),
                    }
                )
    return {"secret_count": len(findings), "secrets": findings}
