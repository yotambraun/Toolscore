"""Find and summarize coding-agent sessions on this machine (read-only).

Claude Code and Codex CLI keep every session as a JSON Lines file
(:mod:`toolscore.adapters.sessions` has the formats). This module finds them,
reads them with the session adapters and runs the honesty checks, so
``toolscore sessions list`` can show what a coding agent did yesterday and where
it may have reported success after a failure.

Nothing here writes to a session file or sends anything anywhere.
:func:`export_session` writes a normalized Toolscore trace with credentials
redacted, for sharing or for a regression test.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

#: Agents whose sessions Toolscore can find.
AGENTS = ("claude-code", "codex")


@dataclass
class SessionSummary:
    """One session file and what the checks found in it.

    Attributes:
        path: The session file.
        agent: ``"claude-code"`` or ``"codex"``.
        session_id: The session ID, when the file records one.
        cwd: The working directory the agent ran in, when recorded.
        started: The first timestamp in the file (ISO 8601), when recorded.
        modified: The file's modification time.
        calls: Tool calls on the main thread.
        failed: Calls that failed.
        findings: Honesty findings as ``{rule: count}``.
        flagged: The honesty verdict (``None`` when unknown).
        final_answer: Whether the session holds a final answer.
        error: Why the file could not be read, if it could not.
    """

    path: Path
    agent: str
    modified: datetime
    session_id: str | None = None
    cwd: str | None = None
    started: str | None = None
    calls: int = 0
    failed: int = 0
    findings: dict[str, int] = field(default_factory=dict)
    flagged: bool | None = None
    final_answer: bool = False
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        """A JSON-safe dict of the summary."""
        return {
            "path": str(self.path),
            "agent": self.agent,
            "session_id": self.session_id,
            "cwd": self.cwd,
            "started": self.started,
            "modified": self.modified.isoformat(),
            "calls": self.calls,
            "failed": self.failed,
            "findings": dict(self.findings),
            "flagged": self.flagged,
            "final_answer": self.final_answer,
            "error": self.error,
        }


def default_roots() -> dict[str, Path]:
    """Where each agent keeps its sessions (honoring ``CLAUDE_CONFIG_DIR`` and ``CODEX_HOME``)."""
    home = Path.home()
    claude = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude")
    codex = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    return {"claude-code": claude / "projects", "codex": codex / "sessions"}


_RELATIVE = re.compile(r"^(\d+)\s*([mhdw])$")


def parse_since(value: str, now: datetime | None = None) -> datetime:
    """Parse ``--since``: ``30m``, ``12h``, ``1d``, ``2w``, or a date / ISO 8601 time.

    Args:
        value: The option value.
        now: The current time (for tests).

    Returns:
        The earliest modification time to include (timezone-aware).

    Raises:
        ValueError: If the value cannot be read.
    """
    now = now or datetime.now(timezone.utc)
    match = _RELATIVE.match(value.strip().lower())
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        delta = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount),
                 "d": timedelta(days=amount), "w": timedelta(weeks=amount)}[unit]  # fmt: skip
        return now - delta
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(
            f"cannot read --since {value!r}: use 30m, 12h, 1d, 2w or a date like 2026-11-01"
        ) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def find_session_files(
    agent: str = "all",
    root: Path | None = None,
    since: datetime | None = None,
) -> list[tuple[str, Path]]:
    """Find session files, newest first.

    Args:
        agent: ``"claude-code"``, ``"codex"`` or ``"all"``.
        root: Search this directory instead of the agents' default folders
            (every ``*.jsonl`` under it; the agent is detected from the content).
        since: Only files modified at or after this time.

    Returns:
        ``(agent, path)`` pairs; with ``root``, the agent is ``"auto"``.
    """
    found: list[tuple[str, Path]] = []
    if root is not None:
        found = [("auto", p) for p in root.rglob("*.jsonl")]
    else:
        for name, folder in default_roots().items():
            if agent not in ("all", name) or not folder.is_dir():
                continue
            pattern = "rollout-*.jsonl" if name == "codex" else "*.jsonl"
            found += [(name, p) for p in folder.rglob(pattern)]
    result = []
    for name, path in found:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if since is None or mtime >= since:
            result.append((mtime, name, path))
    result.sort(key=lambda item: item[0], reverse=True)
    return [(name, path) for _, name, path in result]


def summarize_session(path: Path, agent: str = "auto") -> SessionSummary:
    """Read one session file and run the honesty checks on it.

    Args:
        path: The session file.
        agent: The agent, or ``"auto"`` to detect it from the content.

    Returns:
        The summary; ``error`` is set when the file is not a session Toolscore reads.
    """
    from toolscore.adapters.sessions import looks_like_claude_code, looks_like_codex, session_meta
    from toolscore.core import read_trace_data
    from toolscore.metrics.honesty import check_honesty
    from toolscore.transcript import transcript_from_data

    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    summary = SessionSummary(path=path, agent=agent, modified=modified)
    try:
        data = read_trace_data(path)
    except (OSError, ValueError) as exc:
        summary.error = str(exc)
        return summary
    if not (looks_like_codex(data) or looks_like_claude_code(data)):
        summary.error = "not a Claude Code or Codex session"
        return summary
    meta = session_meta(data)
    summary.agent = meta["agent"]
    summary.session_id = meta.get("session_id")
    summary.cwd = meta.get("cwd")
    summary.started = meta.get("started")
    try:
        transcript = transcript_from_data(data)
    except ValueError as exc:
        summary.error = str(exc)
        return summary
    summary.calls = len(transcript.calls)
    summary.failed = sum(1 for c in transcript.calls if c.is_error)
    summary.final_answer = transcript.final_answer is not None
    report = check_honesty(
        transcript.calls, transcript.final_answer, final_source=transcript.final_source
    )
    for finding in report["findings"]:
        summary.findings[finding["rule"]] = summary.findings.get(finding["rule"], 0) + 1
    summary.flagged = report["flagged"]
    return summary


def _redact(value: Any) -> Any:
    from toolscore.metrics.security import redact_secrets

    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def export_session(path: Path, output: Path, max_result_chars: int = 2000) -> dict[str, Any]:
    """Write a session as a normalized Toolscore trace, with credentials redacted.

    The trace is ``{"format": "toolscore", "source": ..., "calls": [...],
    "final_answer": ...}``: every call with its tool, arguments, result (cut to
    ``max_result_chars``), error and ID. Any credential the secret scanner
    recognizes (API keys, tokens, private keys) is replaced by a redacted
    preview, in arguments, results and the final answer. Other private content
    (code, paths) is kept: review the file before you share it.

    Args:
        path: The session file.
        output: The trace file to write.
        max_result_chars: Longest result text kept per call.

    Returns:
        The trace that was written.
    """
    from toolscore.adapters.sessions import session_meta
    from toolscore.core import read_trace_data
    from toolscore.transcript import transcript_from_data

    data = read_trace_data(path)
    transcript = transcript_from_data(data)
    meta = session_meta(data)

    def cut(value: Any) -> Any:
        if isinstance(value, str) and len(value) > max_result_chars:
            return value[:max_result_chars] + f"… [{len(value) - max_result_chars} more chars]"
        return value

    calls = []
    for call in transcript.calls:
        item: dict[str, Any] = {"tool": call.tool, "args": call.args or {}}
        if call.result is not None:
            item["result"] = cut(call.result)
        if call.is_error:
            item["error"] = call.metadata.get("error") or True
        if call.id is not None:
            item["id"] = call.id
        calls.append(item)
    trace = _redact(
        {
            "format": "toolscore",
            "source": {
                "agent": meta["agent"],
                "session_id": meta.get("session_id"),
                "started": meta.get("started"),
            },
            "calls": calls,
            "final_answer": transcript.final_answer,
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(trace, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return trace  # type: ignore[no-any-return]
