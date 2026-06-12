"""Snapshot testing for AI agents — "Jest snapshots for tool calls".

Record an agent's tool calls once, review and approve them, then replay the
approved baseline as a regression test.  This is the storage + state-machine
core; the pytest fixture and ``toolscore`` CLI are built on top of this API.

A snapshot is a single JSON file on disk that captures the list of tool calls
an agent made for a given test.  The workflow is:

1. **Record** — the first run captures the calls into an *unapproved* snapshot.
2. **Approve** — a human reviews the snapshot and marks it approved.
3. **Replay** — subsequent runs evaluate the agent's calls against the approved
   baseline and fail the test when they drift.

Example::

    from toolscore.snapshots import snapshot_check

    result = snapshot_check("test_booking", my_agent("book a flight to NYC"))
    # First run: writes an unapproved snapshot, warns, returns None.
    # After `toolscore approve test_booking`: evaluates and returns a result.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import builtins

    from toolscore.core import EvaluationResult

DEFAULT_ROOT = ".toolscore/snapshots"
SCHEMA_VERSION = 1

# Characters that are unsafe in file names across platforms (plus whitespace).
# The "::" pytest node separator is collapsed first so it becomes a single
# "__" rather than two.
_UNSAFE_CHARS = re.compile(r'[/\\:\[\]<>|*?"]|\s')


def _utcnow() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _toolscore_version() -> str:
    """Return the installed toolscore version (empty string if unavailable)."""
    try:
        from toolscore import __version__

        return __version__
    except Exception:  # pragma: no cover - defensive only
        return ""


def _sanitize_name(name: str) -> str:
    """Sanitize a snapshot name into a filesystem-safe stem fragment.

    Replaces path separators, drive separators, glob/redirection metacharacters
    and whitespace with ``__``.  The pytest ``::`` node separator is handled by
    the same substitution.  This is *not* required to be reversible — a sha1 of
    the full name is appended by :meth:`SnapshotStore.path_for` to guarantee
    uniqueness and prevent collisions / path traversal.
    """
    # Collapse the pytest node separator first so "::" -> "__" (not "____").
    collapsed = name.replace("::", "__")
    sanitized = _UNSAFE_CHARS.sub("__", collapsed)
    # Strip leading/trailing dots so names like "../../evil" cannot escape root.
    sanitized = sanitized.strip(".")
    return sanitized or "snapshot"


@dataclass
class Snapshot:
    """A recorded set of tool calls for a single test.

    Attributes:
        name: Logical identifier (typically a pytest node id).
        calls: List of tool-call dicts (``{"tool": ..., "args": {...}}``).
        approved: Whether a human has approved this baseline.
        source: How the snapshot was produced — ``"pytest"``, ``"record"`` or
            ``"trace"``.
        created_at: ISO-8601 UTC timestamp; filled on creation if empty.
        updated_at: ISO-8601 UTC timestamp; filled on creation if empty.
        schema_version: On-disk schema version.
        toolscore_version: Version of toolscore that wrote the snapshot; filled
            from the package version if empty.
    """

    name: str
    calls: list[dict[str, Any]] = field(default_factory=list)
    approved: bool = False
    source: str = "pytest"
    created_at: str = ""
    updated_at: str = ""
    schema_version: int = SCHEMA_VERSION
    toolscore_version: str = ""

    def __post_init__(self) -> None:
        """Fill in timestamps and version defaults when not supplied."""
        now = _utcnow()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.toolscore_version:
            self.toolscore_version = _toolscore_version()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the snapshot to a JSON-friendly dict."""
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "toolscore_version": self.toolscore_version,
            "approved": self.approved,
            "source": self.source,
            "calls": self.calls,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        """Construct a :class:`Snapshot` from a dict produced by :meth:`to_dict`."""
        return cls(
            name=data["name"],
            calls=list(data.get("calls", [])),
            approved=bool(data.get("approved", False)),
            source=data.get("source", "pytest"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            toolscore_version=data.get("toolscore_version", ""),
        )


class SnapshotStore:
    """File-backed store for snapshots — one JSON file per snapshot.

    The root directory is created lazily on the first :meth:`save`, so merely
    constructing a store (or listing an empty/absent root) never touches the
    filesystem in a way that creates directories.
    """

    def __init__(self, root: str | Path = DEFAULT_ROOT) -> None:
        """Initialize the store rooted at *root* (no directory is created)."""
        self.root = Path(root)

    def path_for(self, name: str) -> Path:
        """Return the on-disk path for a snapshot named *name*.

        The filename is ``<sanitized-name>-<sha1(name)[:8]>.json``.  The sha1 of
        the *full* name guarantees uniqueness even when sanitization collapses
        distinct names, and keeps every snapshot inside ``root`` regardless of
        path-traversal sequences in the name.
        """
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
        # Truncate the sanitized stem so very long names (e.g. pytest nodeids
        # built from long ``@toolscore.cases`` prompts) cannot exceed the
        # filesystem's per-component name limit.  The sha1 suffix below already
        # guarantees uniqueness, so truncation never collides distinct names.
        sanitized = _sanitize_name(name)[:100]
        stem = f"{sanitized}-{digest}"
        return self.root / f"{stem}.json"

    def exists(self, name: str) -> bool:
        """Return True if a snapshot named *name* is stored on disk."""
        return self.path_for(name).exists()

    def load(self, name: str) -> Snapshot | None:
        """Load the snapshot named *name*, or None if it does not exist.

        Raises:
            ValueError: If the file exists but cannot be parsed as a valid
                snapshot (the path is included in the message).
        """
        path = self.path_for(name)
        if not path.exists():
            return None
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise ValueError(f"Corrupt snapshot file at {path}: {e}") from e
        if not isinstance(data, dict) or "name" not in data or "calls" not in data:
            raise ValueError(
                f"Corrupt snapshot file at {path}: "
                "expected a JSON object with 'name' and 'calls' keys"
            )
        return Snapshot.from_dict(data)

    def save(self, snapshot: Snapshot) -> Path:
        """Persist *snapshot* to disk, creating the root directory if needed.

        The snapshot's ``updated_at`` timestamp is refreshed before writing.

        Returns:
            The path the snapshot was written to.
        """
        snapshot.updated_at = _utcnow()
        path = self.path_for(snapshot.name)
        # Serialize fully *before* touching the destination so a non-serializable
        # value never leaves a truncated file behind (which would make every later
        # run fail with "Corrupt snapshot file").
        try:
            payload = json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False) + "\n"
        except TypeError as e:
            raise ValueError(
                f"Cannot save snapshot {snapshot.name!r}: tool-call arguments must "
                f"be JSON-serializable (got {e}). Convert non-serializable values "
                "(e.g. datetime, Decimal, numpy scalars) to plain JSON types — "
                "strings, numbers, booleans, lists, or dicts — before recording."
            ) from e
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically: a temp file in the same directory + os.replace so a
        # crash mid-write can never corrupt an existing (possibly approved) baseline.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            tmp_path.replace(path)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp_path.unlink()
            raise
        return path

    def approve(self, name: str) -> Snapshot:
        """Mark the snapshot named *name* as approved and persist the change.

        Raises:
            KeyError: If no snapshot named *name* exists.
        """
        snapshot = self.load(name)
        if snapshot is None:
            raise KeyError(f"No snapshot named {name!r} to approve")
        snapshot.approved = True
        self.save(snapshot)
        return snapshot

    def delete(self, name: str) -> None:
        """Delete the snapshot named *name* if it exists (no error if absent)."""
        path = self.path_for(name)
        if path.exists():
            path.unlink()

    def list(self) -> builtins.list[Snapshot]:
        """Return all snapshots in the store, sorted by name.

        Unparseable ``*.json`` files in the root are skipped rather than raising,
        so a single corrupt file does not break listing the rest.
        """
        snapshots: list[Snapshot] = []
        if not self.root.exists():
            return snapshots
        for path in self.root.glob("*.json"):
            try:
                with path.open(encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, dict) and "name" in data and "calls" in data:
                snapshots.append(Snapshot.from_dict(data))
        snapshots.sort(key=lambda s: s.name)
        return snapshots

    def pending(self) -> builtins.list[Snapshot]:
        """Return all unapproved snapshots, sorted by name."""
        return [s for s in self.list() if not s.approved]


def _in_ci() -> bool:
    """Return True when running in CI (the ``CI`` env var is set and non-empty).

    Read at call time so tests can monkeypatch ``os.environ``.
    """
    return bool(os.environ.get("CI"))


def snapshot_check(
    name: str,
    actual: Any,
    *,
    store: SnapshotStore | None = None,
    update: bool = False,
    min_score: float = 1.0,
    weights: dict[str, float] | None = None,
    strict: bool = False,
) -> EvaluationResult | None:
    """Record, approve and replay tool-call snapshots.

    Extracts tool calls from *actual* (via
    :func:`toolscore.integrations.auto_extract`, so raw provider responses are
    accepted) and runs the snapshot state machine:

    1. **Snapshot missing.**  Locally: write an unapproved snapshot, emit a
       :class:`UserWarning` telling the user to review and approve it, and return
       ``None``.  In CI (``CI`` env var set): raise
       :class:`~toolscore.core.ToolScoreAssertionError` *without* writing the
       file — snapshots must be created and reviewed locally, never minted in CI.
    2. **update=True.**  Overwrite the snapshot's calls, mark it approved, emit a
       :class:`UserWarning`, and return ``None``.
    3. **Exists but unapproved.**  Locally: emit a :class:`UserWarning` and return
       ``None`` (an unapproved baseline is never evaluated against).  In CI: raise
       :class:`~toolscore.core.ToolScoreAssertionError`.
    4. **Exists and approved.**  Evaluate *actual* against the approved baseline
       with :func:`toolscore.evaluate`, enforce *min_score*, and return the
       :class:`~toolscore.core.EvaluationResult`.

    Args:
        name: Snapshot identifier (typically the pytest node id).
        actual: A raw provider response or a list of tool-call dicts.  Always run
            through ``auto_extract`` before storage / comparison.
        store: Snapshot store to use; ``None`` uses a default-rooted store.
        update: When True, overwrite and approve the snapshot (state 2).
        min_score: Minimum composite score required when replaying (state 4).
        weights: Optional custom weights for the composite score.
        strict: When True, argument comparison uses pure equality.

    Returns:
        An :class:`~toolscore.core.EvaluationResult` when an approved baseline was
        replayed (state 4); otherwise ``None``.

    Raises:
        ToolScoreAssertionError: In CI when the snapshot is missing or unapproved,
            or when an approved replay scores below *min_score*.
    """
    from toolscore.core import ToolScoreAssertionError, _check_min_score, evaluate
    from toolscore.integrations import auto_extract

    if store is None:
        store = SnapshotStore()

    calls = auto_extract(actual)
    existing = store.load(name)

    # State 2: explicit update — overwrite and approve regardless of prior state.
    if update:
        snapshot = existing or Snapshot(name=name, calls=calls, source="pytest")
        snapshot.calls = calls
        snapshot.approved = True
        store.save(snapshot)
        warnings.warn(
            f"snapshot {name!r} updated (calls overwritten and approved)",
            UserWarning,
            stacklevel=2,
        )
        return None

    # State 1: missing snapshot.
    if existing is None:
        if _in_ci():
            raise ToolScoreAssertionError(
                f"snapshot {name!r} does not exist; snapshots cannot be created in CI. "
                "Run the test locally to record it, review it, then approve with "
                "`toolscore approve`."
            )
        snapshot = Snapshot(name=name, calls=calls, approved=False, source="pytest")
        store.save(snapshot)
        warnings.warn(
            f"snapshot {name!r} created — review it, then approve with `toolscore approve`",
            UserWarning,
            stacklevel=2,
        )
        return None

    # State 3: exists but not approved.
    if not existing.approved:
        if _in_ci():
            raise ToolScoreAssertionError(
                f"snapshot {name!r} is pending approval; an unapproved snapshot "
                "cannot be used as a baseline in CI. Approve it locally with "
                "`toolscore approve`."
            )
        warnings.warn(
            f"snapshot {name!r} pending approval — run `toolscore approve` to use it as a baseline",
            UserWarning,
            stacklevel=2,
        )
        return None

    # State 4: exists and approved — evaluate against the baseline.
    result = evaluate(existing.calls, actual, weights=weights, strict=strict)
    # ``_check_min_score`` already tolerates float noise in the threshold, so an
    # exact replay (~0.9999999999999999 against the default min_score=1.0) passes
    # while genuine drift is still caught.
    _check_min_score(result, min_score)
    return result
