"""Receipts: content-hashed records of an evaluation, and regrading without re-running.

Record once, re-score forever (an idea from Agent Eval Flow). A **receipt** says
exactly what was evaluated and how: the SHA-256 of every input file (gold or
contract, trace, forbidden rules, honesty config, injected faults), the
settings (format, weights, final answer), the Toolscore version, the result
(score, grade) and the SHA-256 of the full :meth:`~toolscore.core.EvaluationResult.to_dict`
record. The receipt hashes itself (``receipt_sha256``), so a changed receipt is
detectable too.

:func:`regrade` re-scores a saved trace with a new contract, gold file or
weights. Nothing is re-run: no agent, no model, no MCP server. Given a receipt,
it first checks that the trace is still the file the receipt hashed.

Receipt layout (``receipt_version`` "1")::

    {
      "receipt_version": "1",
      "kind": "toolscore.evaluation",
      "created_at": "2026-11-02T10:00:00+00:00",
      "toolscore_version": "1.11.0",
      "inputs": {"gold": {"path": ..., "sha256": ..., "bytes": ...}, "trace": {...}, ...},
      "settings": {"format": "auto", "weights": {...} | null, "final_answer_sha256": ... | null},
      "contract_sha256": "<sha256 of the expected calls as canonical JSON>",
      "result": {"score": 0.93, "grade": "A", "required_call_recall": 1.0,
                 "record_schema_version": "2", "record_sha256": "..."},
      "receipt_sha256": "<sha256 of everything above>"
    }

Hashes are of canonical JSON (sorted keys, no whitespace, UTF-8), so they do
not depend on how a file was formatted, except input-file hashes, which are of
the bytes on disk.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult
    from toolscore.metrics.honesty import HonestyConfig

#: Layout version of a receipt.
RECEIPT_VERSION = "1"

#: The ``kind`` of an evaluation receipt.
RECEIPT_KIND = "toolscore.evaluation"


def canonical_json(value: Any) -> bytes:
    """``value`` as canonical JSON bytes: sorted keys, no whitespace, UTF-8.

    Non-JSON leaves (matchers, arbitrary objects) are written as their ``repr``.
    """
    from toolscore.core import _json_safe

    return json.dumps(
        _json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """The SHA-256 of ``data`` as hex."""
    return hashlib.sha256(data).hexdigest()


def json_sha256(value: Any) -> str:
    """The SHA-256 of ``value`` as canonical JSON (see :func:`canonical_json`)."""
    return sha256_hex(canonical_json(value))


def file_digest(path: str | Path) -> dict[str, Any]:
    """``{"path", "sha256", "bytes"}`` for a file on disk.

    Args:
        path: The file.

    Returns:
        The digest (``path`` as given, ``sha256`` of the bytes, size in bytes).
    """
    data = Path(path).read_bytes()
    return {"path": str(path), "sha256": sha256_hex(data), "bytes": len(data)}


def expected_calls_sha256(result: EvaluationResult) -> str:
    """The hash of what was expected: every gold call's tool and arguments, in order."""
    return json_sha256([{"tool": c.tool, "args": c.args} for c in result.gold_calls])


def record_sha256(result: EvaluationResult) -> str:
    """The hash of the full, deterministic :meth:`EvaluationResult.to_dict` record."""
    return json_sha256(result.to_dict())


def build_receipt(
    result: EvaluationResult,
    inputs: dict[str, str | Path | None] | None = None,
    settings: dict[str, Any] | None = None,
    final_answer: str | None = None,
) -> dict[str, Any]:
    """Build the receipt of one evaluation.

    Args:
        result: The evaluation.
        inputs: Input files by role (``"gold"``, ``"trace"``, ``"forbidden"``,
            ``"honesty_config"``, ``"injected"``...); ``None`` entries are left out.
        settings: Settings that changed the result (``format``, ``strict``...).
            The normalized weights are always added.
        final_answer: A final answer given from outside the trace; only its
            hash is stored.

    Returns:
        The receipt dict, with ``receipt_sha256`` last.
    """
    from toolscore import __version__

    receipt: dict[str, Any] = {
        "receipt_version": RECEIPT_VERSION,
        "kind": RECEIPT_KIND,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolscore_version": __version__,
        "inputs": {
            role: file_digest(path) for role, path in (inputs or {}).items() if path is not None
        },
        "settings": {
            **(settings or {}),
            "weights": dict(result._weights),
            "final_answer_sha256": (
                sha256_hex(final_answer.encode("utf-8")) if final_answer else None
            ),
        },
        "contract_sha256": expected_calls_sha256(result),
        "result": {
            "score": result.score,
            "grade": result.grade,
            "required_call_recall": result.required_call_recall,
            "record_schema_version": result.RECORD_SCHEMA_VERSION,
            "record_sha256": record_sha256(result),
        },
    }
    receipt["receipt_sha256"] = json_sha256(receipt)
    return receipt


def write_receipt(path: str | Path, receipt: dict[str, Any]) -> Path:
    """Write a receipt as indented JSON and return its path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def is_receipt(data: Any) -> bool:
    """Whether parsed JSON is a Toolscore evaluation receipt."""
    return isinstance(data, dict) and data.get("kind") == RECEIPT_KIND and "inputs" in data


def load_receipt(path: str | Path) -> dict[str, Any]:
    """Read a receipt file.

    Raises:
        ValueError: If the file is not a receipt.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not is_receipt(data):
        raise ValueError(f"{path} is not a Toolscore receipt (no kind {RECEIPT_KIND!r})")
    return dict(data)


def verify_receipt(receipt: dict[str, Any], base: str | Path | None = None) -> list[str]:
    """Check a receipt against itself and the files it names.

    Args:
        receipt: The receipt.
        base: Directory that relative input paths are resolved against (the
            receipt's own directory, usually); the current directory if ``None``.

    Returns:
        Problems found, empty when the receipt and every input check out. A
        missing input is a problem; so is one whose bytes changed.
    """
    problems: list[str] = []
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    if receipt.get("receipt_sha256") != json_sha256(body):
        problems.append("the receipt was changed after it was written (receipt_sha256 mismatch)")
    for role, digest in (receipt.get("inputs") or {}).items():
        path = resolve_input(digest.get("path", ""), base)
        if path is None:
            problems.append(f"{role}: {digest.get('path')} not found")
            continue
        actual = sha256_hex(path.read_bytes())
        if actual != digest.get("sha256"):
            problems.append(
                f"{role}: {digest.get('path')} changed since the receipt "
                f"(sha256 {actual[:12]}..., receipt has {str(digest.get('sha256'))[:12]}...)"
            )
    return problems


def resolve_input(path: str, base: str | Path | None) -> Path | None:
    """Find a receipt input: as given, else relative to ``base``; ``None`` if neither exists."""
    candidate = Path(path)
    if candidate.is_file():
        return candidate
    if base is not None and not candidate.is_absolute():
        relative = Path(base) / candidate
        if relative.is_file():
            return relative
    return None


@dataclass
class Regrade:
    """One regraded trace.

    Attributes:
        source: The receipt or trace that was regraded.
        result: The new evaluation.
        receipt: The new receipt.
        previous: The previous ``result`` block (``score``, ``grade``...) from
            the source receipt, or ``None`` when regrading a bare trace.
        problems: What :func:`verify_receipt` found (empty when it checked out
            or verification was off).
    """

    source: str
    result: EvaluationResult
    receipt: dict[str, Any]
    previous: dict[str, Any] | None = None
    problems: list[str] | None = None

    @property
    def score_delta(self) -> float | None:
        """New score minus the previous one, or ``None`` without a previous score."""
        if not self.previous or not isinstance(self.previous.get("score"), (int, float)):
            return None
        return self.result.score - float(self.previous["score"])


class ReceiptMismatchError(ValueError):
    """A receipt's inputs changed since it was written, so a regrade would not be faithful."""


def regrade(
    source: str | Path,
    gold: str | Path | None = None,
    weights: dict[str, float] | None = None,
    forbidden: str | Path | None = None,
    format: str | None = None,
    honesty: HonestyConfig | None = None,
    final_answer: str | None = None,
    verify: bool = True,
) -> Regrade:
    """Re-score a saved trace with a new gold file or contract, weights or rules.

    Nothing is re-run. ``source`` is a receipt (its trace, gold, format and
    weights are the defaults) or a trace file (then ``gold`` is required).

    Args:
        source: A receipt file or a trace file.
        gold: The new gold file or contract (default: the receipt's).
        weights: New score weights (default: the receipt's).
        forbidden: A forbidden-rules file (default: the receipt's, if any).
        format: The trace format (default: the receipt's, else ``"auto"``).
        honesty: Honesty-check configuration.
        final_answer: The final answer, when the trace does not hold one.
        verify: Refuse a receipt whose inputs changed (raises
            :class:`ReceiptMismatchError`); ``False`` regrades anyway and
            reports the problems.

    Returns:
        The :class:`Regrade`.

    Raises:
        ValueError: If a trace is given without ``gold``.
        ReceiptMismatchError: If ``verify`` is on and the receipt's inputs changed.
    """
    from toolscore.core import evaluate_trace
    from toolscore.metrics.policy import load_forbidden_rules

    source_path = Path(source)
    data: Any = None
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None

    previous: dict[str, Any] | None = None
    problems: list[str] = []
    settings: dict[str, Any] = {}
    if is_receipt(data):
        base = source_path.parent
        problems = verify_receipt(data, base=base)
        inputs = data.get("inputs") or {}
        if verify and problems:
            raise ReceiptMismatchError("; ".join(problems))
        trace_entry = inputs.get("trace")
        if not trace_entry:
            raise ValueError(f"{source} has no trace input to regrade")
        trace_path = resolve_input(trace_entry["path"], base) or Path(trace_entry["path"])
        if gold is None and inputs.get("gold"):
            gold = resolve_input(inputs["gold"]["path"], base) or inputs["gold"]["path"]
        if forbidden is None and inputs.get("forbidden"):
            forbidden = (
                resolve_input(inputs["forbidden"]["path"], base) or (inputs["forbidden"]["path"])
            )
        settings = dict(data.get("settings") or {})
        if weights is None and isinstance(settings.get("weights"), dict):
            weights = {k: float(v) for k, v in settings["weights"].items()}
        if format is None:
            format = str(settings.get("format") or "auto")
        previous = dict(data.get("result") or {})
    else:
        trace_path = source_path
    if gold is None:
        raise ValueError("regrading a trace needs a gold file or contract (gold=...)")

    rules = load_forbidden_rules(forbidden) if forbidden is not None else None
    result = evaluate_trace(
        gold,
        trace_path,
        format=format or "auto",
        weights=weights,
        forbidden=rules,
        final_answer=final_answer,
        honesty=honesty,
        validate_side_effects=False,
    )
    receipt = build_receipt(
        result,
        inputs={"gold": gold, "trace": trace_path, "forbidden": forbidden},
        settings={"format": format or "auto", "regraded_from": _source_hash(source_path, data)},
        final_answer=final_answer,
    )
    return Regrade(
        source=str(source),
        result=result,
        receipt=receipt,
        previous=previous,
        problems=problems,
    )


def _source_hash(path: Path, data: Any) -> str:
    """What a regrade came from: the source receipt's own hash, else the trace's file hash."""
    if is_receipt(data) and isinstance(data.get("receipt_sha256"), str):
        return str(data["receipt_sha256"])
    return sha256_hex(path.read_bytes())
