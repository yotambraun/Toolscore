"""Export runs as neutral, versioned run records for evaluation frameworks.

``toolscore export --format aef`` (and :func:`export_records`) turns agent runs
(``toolscore agent run`` JSONL), trace files and receipts into one JSON record
per run, in a documented schema (``toolscore.run-record``, version "1",
:data:`SCHEMA_PATH`) that a study framework such as Agent Eval Flow can import
without knowing Toolscore's internals:

* **requested vs completed calls, correlated by ID.** ``requested_calls`` is
  what the model asked for (with denied calls); ``completed_calls`` is what came
  back, one per request, with the same ``call_id``. A trace without call IDs
  gets ``call-<n>`` IDs, marked ``call_id_source: "synthesized"``.
* **unknown coverage is explicit.** ``coverage`` counts the calls with a result,
  a duration and a cost, says whether the final answer is known, and lists what
  is ``unknown``. A call whose result was not captured has ``status:
  "unknown"``; a run without a price has ``cost.usd: null`` and ``cost.status:
  "unknown"``. Nothing unknown is written as 0 or as a pass.
* **hashes.** Every argument set, result and final answer has a SHA-256 of its
  canonical JSON, the record has ``hashes.record_sha256``, and the source file
  is named with its SHA-256. A manifest (``<output>.manifest.json``) lists the
  sources, the record count and the SHA-256 of the output file.

The schema is neutral: no field depends on a particular framework, and new
fields may be added in version 1; a change that could break a reader bumps
``schema_version``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from toolscore.receipts import file_digest, is_receipt, json_sha256, resolve_input, sha256_hex

if TYPE_CHECKING:
    from collections.abc import Iterable

    from toolscore.core import EvaluationResult

#: The schema name of a run record.
SCHEMA_NAME = "toolscore.run-record"
#: The schema version of a run record.
SCHEMA_VERSION = "1"
#: The JSON Schema of a run record, shipped with the package.
SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "run-record-v1.schema.json"
#: Export formats (``aef``: the neutral run record, ready for Agent Eval Flow and others).
EXPORT_FORMATS: tuple[str, ...] = ("aef",)


def _producer() -> dict[str, str]:
    from toolscore import __version__

    return {"name": "toolscore", "version": __version__}


def _text_hash(text: str | None) -> str | None:
    return None if text is None else sha256_hex(text.encode("utf-8"))


def _call_pairs(
    calls: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """``requested_calls``, ``completed_calls`` and the ``call_id_source``."""
    requested: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    synthesized = False
    for index, call in enumerate(calls, start=1):
        call_id = call.get("id")
        if call_id in (None, ""):
            call_id, synthesized = f"call-{index}", True
        arguments = call.get("args") if isinstance(call.get("args"), dict) else {}
        denied = bool(call.get("denied"))
        requested.append(
            {
                "call_id": str(call_id),
                "index": index,
                "tool": str(call.get("tool") or ""),
                "arguments": arguments,
                "arguments_sha256": json_sha256(arguments),
                "denied": denied,
                "deny_reason": call.get("deny_reason"),
            }
        )
        result = call.get("result")
        result_text = result if isinstance(result, str) or result is None else json.dumps(result)
        has_outcome = result is not None or "is_error" in call or bool(call.get("error"))
        if denied:
            status = "denied"
        elif not has_outcome:
            status = "unknown"
        else:
            status = "error" if call.get("is_error") or call.get("error") else "ok"
        duration = call.get("duration")
        completed.append(
            {
                "call_id": str(call_id),
                "status": status,
                "result_text": result_text,
                "result_sha256": _text_hash(result_text),
                "error": call.get("error"),
                "duration_s": duration if isinstance(duration, (int, float)) else None,
            }
        )
    return requested, completed, "synthesized" if synthesized else "trace"


def _coverage(
    completed: list[dict[str, Any]], cost_known: bool, final_known: bool, costs: int
) -> dict[str, Any]:
    results = sum(1 for c in completed if c["status"] != "unknown")
    # A denied call never ran, so it has no duration to miss.
    executed = [c for c in completed if c["status"] != "denied"]
    durations = sum(1 for c in executed if c["duration_s"] is not None)
    unknown = []
    if results < len(completed):
        unknown.append("results")
    if durations < len(executed):
        unknown.append("durations")
    if not cost_known:
        unknown.append("cost")
    if not final_known:
        unknown.append("final_answer")
    return {
        "calls": len(completed),
        "results": results,
        "durations": durations,
        "call_costs": costs,
        "cost": "known" if cost_known else "unknown",
        "final_answer": "known" if final_known else "unknown",
        "unknown": unknown,
    }


def _evaluation_block(evaluation: dict[str, Any] | None, outcome: str) -> dict[str, Any] | None:
    if evaluation is None:
        return None
    honesty = evaluation.get("honesty") or {}
    evidence = evaluation.get("evidence") or {}
    return {
        "score": evaluation.get("score"),
        "grade": evaluation.get("grade"),
        "passed": None if outcome in ("error", "unknown") else outcome == "pass",
        "required_call_recall": evaluation.get("required_call_recall"),
        "honesty_flagged": honesty.get("flagged"),
        "honesty_findings": [
            {
                "rule": f.get("rule"),
                "severity": f.get("severity"),
                "confidence": f.get("confidence"),
            }
            for f in honesty.get("findings") or []
        ],
        "false_success": honesty.get("false_success"),
        "evidence_counts": evidence.get("counts"),
        "checks": evidence.get("checks"),
    }


def _finish(record: dict[str, Any]) -> dict[str, Any]:
    record["hashes"]["record_sha256"] = json_sha256(
        {k: v for k, v in record.items() if k != "hashes"}
    )
    return record


def record_from_run(row: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """The run record of one ``toolscore agent run`` row.

    Args:
        row: The row.
        source: ``{"kind", "path", "sha256", "line"}`` of where it came from.

    Returns:
        The record (see the module docstring and :data:`SCHEMA_PATH`).
    """
    requested, completed, id_source = _call_pairs(list(row.get("calls") or []))
    cost = row.get("cost_usd")
    cost_known = isinstance(cost, (int, float)) and not isinstance(cost, bool)
    final = row.get("final_answer")
    outcome = str(row.get("outcome") or "unknown")
    usage = row.get("usage") if isinstance(row.get("usage"), dict) else None
    record: dict[str, Any] = {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "producer": _producer(),
        "source": source,
        "study": row.get("study"),
        "run_id": str(row.get("run_id") or row.get("cell_id") or ""),
        "task_id": str(row.get("task_id") or ""),
        "variant": str(row.get("arm_id") or ""),
        "repetition": row.get("repetition"),
        "status": str(row.get("status") or "unknown"),
        "outcome": outcome,
        "model": {"provider": row.get("provider"), "name": row.get("model")},
        "server": row.get("server"),
        "prompt_sha256": _text_hash(row.get("prompt")),
        "call_id_source": id_source,
        "requested_calls": requested,
        "completed_calls": completed,
        "final_answer": {
            "status": "known" if isinstance(final, str) and final.strip() else "unknown",
            "text": final,
            "sha256": _text_hash(final),
        },
        "coverage": _coverage(
            completed, cost_known, isinstance(final, str) and bool(final.strip()), 0
        ),
        "usage": usage,
        "cost": {
            "usd": cost if cost_known else None,
            "status": "known" if cost_known else "unknown",
        },
        "evaluation": _evaluation_block(row.get("evaluation"), outcome),
        "hashes": {"calls_sha256": json_sha256(requested)},
    }
    return _finish(record)


def record_from_evaluation(
    result: EvaluationResult,
    final_answer: str | None,
    source: dict[str, Any],
    variant: str = "",
    task_id: str = "",
    min_score: float = 0.9,
) -> dict[str, Any]:
    """The run record of a trace evaluated against a gold file (or of a bare trace).

    Args:
        result: The evaluation (with or without gold calls).
        final_answer: The final answer, if known.
        source: Where the trace came from.
        variant: The variant name.
        task_id: The task (default: the trace file stem).
        min_score: The passing score, for ``outcome``.
    """
    calls = [
        {
            "id": c.id,
            "tool": c.tool,
            "args": c.args or {},
            "result": c.result,
            **({"is_error": c.metadata["is_error"]} if "is_error" in c.metadata else {}),
            "error": c.metadata.get("error")
            if not isinstance(c.metadata.get("error"), bool)
            else None,
            "duration": c.duration,
        }
        for c in result.trace_calls
    ]
    requested, completed, id_source = _call_pairs(calls)
    costs = [c.cost for c in result.trace_calls if c.cost is not None]
    cost_known = bool(result.trace_calls) and len(costs) == len(result.trace_calls)
    record_dict = result.to_dict()
    if result.gold_calls:
        honesty = result.metrics.get("honesty_metrics") or {}
        dishonest = any(f.get("severity") == "error" for f in honesty.get("findings", []))
        outcome = "pass" if result.score >= min_score - 1e-9 and not dishonest else "fail"
    else:
        outcome = "unknown"
    evaluation = {
        "score": record_dict["score"] if result.gold_calls else None,
        "grade": record_dict["grade"] if result.gold_calls else None,
        "required_call_recall": record_dict["required_call_recall"],
        "honesty": record_dict["metrics"].get("honesty_metrics"),
        "evidence": record_dict["evidence"],
    }
    known = isinstance(final_answer, str) and bool(final_answer.strip())
    record: dict[str, Any] = {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "producer": _producer(),
        "source": source,
        "study": None,
        "run_id": str(source.get("path") or ""),
        "task_id": task_id or Path(str(source.get("path") or "trace")).stem,
        "variant": variant,
        "repetition": None,
        "status": "recorded",
        "outcome": outcome,
        "model": None,
        "server": None,
        "prompt_sha256": None,
        "call_id_source": id_source,
        "requested_calls": requested,
        "completed_calls": completed,
        "final_answer": {
            "status": "known" if known else "unknown",
            "text": final_answer if known else None,
            "sha256": _text_hash(final_answer) if known else None,
        },
        "coverage": _coverage(completed, cost_known, known, len(costs)),
        "usage": None,
        "cost": {
            "usd": sum(costs) if cost_known else None,
            "status": "known" if cost_known else "unknown",
        },
        "evaluation": _evaluation_block(evaluation, outcome),
        "hashes": {"calls_sha256": json_sha256(requested)},
    }
    return _finish(record)


def export_records(
    inputs: Iterable[str | Path],
    gold: str | Path | None = None,
    variant: str = "",
    min_score: float = 0.9,
) -> list[dict[str, Any]]:
    """Run records for agent-run JSONL files, trace files and receipts.

    Args:
        inputs: ``.jsonl`` files from ``toolscore agent run``, trace files
            (any supported format), or receipts from ``toolscore eval --receipt``.
        gold: A gold file or contract for traces (receipts carry their own).
        variant: The variant of traces and receipts.
        min_score: The passing score of traces and receipts.

    Returns:
        The records, in input order.

    Raises:
        ValueError: On an unreadable input.
    """
    from toolscore.core import evaluate_trace
    from toolscore.transcript import load_transcript

    records: list[dict[str, Any]] = []
    for item in inputs:
        path = Path(item)
        digest = file_digest(path)
        if path.suffix == ".jsonl":
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if isinstance(row, dict) and row.get("record") == "run":
                    source = {"kind": "agent-run", **digest, "line": number}
                    records.append(record_from_run(row, source))
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        trace_path, gold_path = path, gold
        kind = "trace"
        if is_receipt(data):
            inputs_block = data.get("inputs") or {}
            trace_entry = inputs_block.get("trace") or {}
            trace_path = resolve_input(str(trace_entry.get("path", "")), path.parent) or Path(
                str(trace_entry.get("path", ""))
            )
            if gold_path is None and inputs_block.get("gold"):
                gold_path = resolve_input(inputs_block["gold"]["path"], path.parent)
            kind = "receipt"
        transcript = load_transcript(trace_path)
        if gold_path is not None:
            result = evaluate_trace(gold_path, trace_path, validate_side_effects=False)
        else:
            from toolscore.core import EvaluationResult, _add_trace_checks

            result = EvaluationResult()
            result.trace_calls = transcript.calls
            _add_trace_checks(
                result,
                [],
                transcript.calls,
                final_answer=transcript.final_answer,
                final_source=transcript.final_source,
            )
        source = {"kind": kind, **digest}
        if kind == "receipt":
            source["trace"] = file_digest(trace_path)
        records.append(
            record_from_evaluation(
                result,
                transcript.final_answer,
                source,
                variant=variant,
                min_score=min_score,
            )
        )
    return records


def write_export(
    path: str | Path, records: list[dict[str, Any]], inputs: Iterable[str | Path]
) -> tuple[Path, Path]:
    """Write records as JSONL and a manifest next to it.

    Returns:
        ``(jsonl path, manifest path)``. The manifest holds the schema, the
        producer, the sources with their hashes, the record count and the
        SHA-256 of the JSONL file.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)
    # "\n" on every OS, so the manifest's sha256 is the hash of the file as written
    target.write_text(text, encoding="utf-8", newline="\n")
    manifest = {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "producer": _producer(),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "records": len(records),
        "output": {"path": str(target), "sha256": sha256_hex(text.encode("utf-8"))},
        "sources": [file_digest(p) for p in inputs],
    }
    manifest_path = target.with_name(target.name + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target, manifest_path


def validate_record(record: dict[str, Any]) -> list[str]:
    """Check a record against the shipped JSON Schema (Toolscore's conservative validator).

    Returns:
        Problems found (empty when the record conforms), plus a check that
        ``hashes.record_sha256`` matches the record.
    """
    from toolscore.mcp.output_schema import validate_instance

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    problems = list(validate_instance(record, schema))
    expected = json_sha256({k: v for k, v in record.items() if k != "hashes"})
    if (record.get("hashes") or {}).get("record_sha256") != expected:
        problems.append("hashes.record_sha256 does not match the record")
    return problems
