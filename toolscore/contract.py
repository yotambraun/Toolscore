"""Contracts (version 2): required, optional and forbidden calls, and alternatives.

A gold file lists the calls an agent must make. A **contract** also says which
calls are allowed but not needed, which must never happen, and where more than
one path is acceptable::

    {
      "contract_version": 2,
      "required": [
        {"tool": "search", "args": {"q": {"$regex": "cats?"}}},
        {"alternatives": [
          [{"tool": "create_note", "args": {"title": {"$any": true}}}],
          [{"tool": "upsert_note"}]
        ], "id": "save"}
      ],
      "optional": [{"tool": "list_notes"}],
      "forbidden": [{"tool": "delete_note", "reason": "never delete"}],
      "weights": {"required_call_recall": 0.3},
      "min_score": 0.9
    }

* **required** calls are scored like gold calls, in order. An element
  ``{"alternatives": [[calls], [calls], ...], "id": ...}`` is replaced by one
  of its options; every combination is scored and the highest composite score
  wins, ties going to the option declared first. A top-level ``alternatives``
  list of such groups is appended after ``required``.
* **optional** calls are neither penalized when absent nor counted as extra
  when present: a call that matches an optional entry (tool and arguments) is
  left out of the score metrics, unless it is needed to fill a required call
  of the same tool. The honesty, credential, forbidden-call and evidence checks
  still see every call.
* **forbidden** rules are the forbidden-call policy
  (:mod:`toolscore.metrics.policy`); violations are reported, not scored.
* ``weights`` are score weights (as for :func:`toolscore.evaluate`);
  ``min_score`` is the passing score for tools that need one.

Argument values may be plain values or matchers: in JSON, ``{"$regex": p}``
(found anywhere in the value), ``{"$contains": x}``, ``{"$one_of": [...]}``,
``{"$any": true}``, ``{"$type": "string" | "integer" | "number" | "boolean" |
"array" | "object" | "null"}`` and ``{"$approx": n}`` or ``{"$approx": {"value":
n, "rel": r, "abs": a}}``; in Python, any :class:`~toolscore.matchers.Matcher`.

The JSON Schema of a contract file ships as :data:`CONTRACT_SCHEMA_PATH`.
:func:`is_contract` tells a contract from a gold file, so ``toolscore eval``,
:func:`toolscore.evaluate_trace` and ``toolscore regrade`` accept either.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeGuard

from toolscore.matchers import ANY, Approx, IsType, Matcher
from toolscore.metrics.policy import _matcher_from_json, call_matches_rule, rules_from_json

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult
    from toolscore.metrics.honesty import HonestyConfig

#: The contract layout version this module reads.
CONTRACT_VERSION = 2
#: The JSON Schema of a contract file.
CONTRACT_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "contract-v2.schema.json"
#: Most combinations of alternatives that are scored.
MAX_COMBINATIONS = 256

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict,),
    "null": (type(None),),
}
_CONTRACT_KEYS = {"contract_version", "required", "optional", "forbidden", "alternatives", "weights",
                  "min_score", "description"}  # fmt: skip
_CALL_KEYS = {"tool", "args", "description", "side_effects"}


def matcher_from_json(value: Any) -> Any:
    """Turn ``$`` operators in a JSON value into matchers (see the module docstring)."""
    if isinstance(value, dict):
        if len(value) == 1:
            ((key, operand),) = value.items()
            if key == "$any":
                return ANY
            if key == "$type":
                names = operand if isinstance(operand, list) else [operand]
                if not names or any(n not in _JSON_TYPES for n in names):
                    raise ValueError(f"$type needs one of {sorted(_JSON_TYPES)}, got {operand!r}")
                return IsType(*{t for n in names for t in _JSON_TYPES[n]})
            if key == "$approx":
                if isinstance(operand, dict):
                    return Approx(
                        float(operand["value"]),
                        rel=float(operand.get("rel", 1e-6)),
                        abs=float(operand.get("abs", 0.0)),
                    )
                return Approx(float(operand))
            matcher = _matcher_from_json(value)
            if matcher is not None:
                return matcher
        return {k: matcher_from_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [matcher_from_json(v) for v in value]
    return value


def _call(entry: Any, where: str) -> dict[str, Any]:
    if not isinstance(entry, dict) or not isinstance(entry.get("tool"), str) or not entry["tool"]:
        raise ValueError(f"{where}: a call needs a non-empty 'tool' string, got {entry!r}")
    unknown = set(entry) - _CALL_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {sorted(unknown)}")
    call = dict(entry)
    if isinstance(entry.get("args"), dict):
        call["args"] = {k: matcher_from_json(v) for k, v in entry["args"].items()}
    elif entry.get("args") is not None:
        raise ValueError(f"{where}: 'args' must be an object")
    return call


@dataclass
class AlternativeGroup:
    """A place in the required calls where any one of several call lists is acceptable."""

    id: str
    options: list[list[dict[str, Any]]]


@dataclass
class Contract:
    """A parsed contract (see the module docstring).

    Attributes:
        required: Required calls and alternative groups, in order.
        optional: Calls that may be made without penalty.
        forbidden: Forbidden-call rules.
        weights: Score weights, or ``None``.
        min_score: The passing score.
    """

    required: list[dict[str, Any] | AlternativeGroup] = field(default_factory=list)
    optional: list[dict[str, Any]] = field(default_factory=list)
    forbidden: list[dict[str, Any]] = field(default_factory=list)
    weights: dict[str, float] | None = None
    min_score: float = 0.9

    @property
    def groups(self) -> list[AlternativeGroup]:
        """The alternative groups, in order."""
        return [item for item in self.required if isinstance(item, AlternativeGroup)]

    def expansions(self) -> list[tuple[list[dict[str, Any]], dict[str, int]]]:
        """Every combination of alternatives: ``(required calls, {group id: option index})``.

        In declaration order (the first option of every group first).

        Raises:
            ValueError: With more than :data:`MAX_COMBINATIONS` combinations.
        """
        groups = self.groups
        sizes = [len(g.options) for g in groups]
        total = 1
        for size in sizes:
            total *= size
        if total > MAX_COMBINATIONS:
            raise ValueError(
                f"the contract's alternatives make {total} combinations (at most "
                f"{MAX_COMBINATIONS} are scored); split it into smaller groups"
            )
        expansions = []
        for choice in itertools.product(*(range(n) for n in sizes)):
            picked = dict(zip((g.id for g in groups), choice, strict=True))
            calls: list[dict[str, Any]] = []
            for item in self.required:
                if isinstance(item, AlternativeGroup):
                    calls.extend(item.options[picked[item.id]])
                else:
                    calls.append(item)
            expansions.append((calls, picked))
        return expansions


def _group(entry: dict[str, Any], index: int, where: str) -> AlternativeGroup:
    options = entry.get("alternatives")
    if not isinstance(options, list) or len(options) < 2:
        raise ValueError(f"{where}: 'alternatives' needs at least two options (lists of calls)")
    unknown = set(entry) - {"alternatives", "id", "description"}
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {sorted(unknown)}")
    parsed = []
    for number, option in enumerate(options):
        if isinstance(option, dict):
            option = [option]
        if not isinstance(option, list):
            raise ValueError(f"{where} option {number}: an option is a list of calls")
        parsed.append([_call(c, f"{where} option {number}") for c in option])
    return AlternativeGroup(id=str(entry.get("id") or f"alternatives-{index + 1}"), options=parsed)


def contract_from_mapping(data: Any) -> Contract:
    """Validate and build a :class:`Contract` from parsed JSON (or a Python dict).

    Raises:
        ValueError: On a missing or unknown key, or a malformed call.
    """
    if not isinstance(data, dict):
        raise ValueError("a contract must be a JSON object")
    unknown = set(data) - _CONTRACT_KEYS
    if unknown:
        raise ValueError(f"unknown contract key(s): {sorted(unknown)}")
    version = data.get("contract_version", CONTRACT_VERSION)
    if version != CONTRACT_VERSION:
        raise ValueError(f"contract_version must be {CONTRACT_VERSION}, got {version!r}")
    required: list[dict[str, Any] | AlternativeGroup] = []
    raw_required = list(data.get("required") or [])
    raw_required.extend(data.get("alternatives") or [])
    group_index = 0
    for index, entry in enumerate(raw_required):
        where = f"required[{index}]"
        if isinstance(entry, dict) and "alternatives" in entry:
            required.append(_group(entry, group_index, where))
            group_index += 1
        else:
            required.append(_call(entry, where))
    ids = [g.id for g in required if isinstance(g, AlternativeGroup)]
    if len(set(ids)) != len(ids):
        raise ValueError("alternative group ids must be unique")
    optional = [_call(c, f"optional[{i}]") for i, c in enumerate(data.get("optional") or [])]
    forbidden_raw = data.get("forbidden") or []
    forbidden = (
        rules_from_json(forbidden_raw)
        if all(
            not isinstance(v, Matcher)
            for r in forbidden_raw
            for v in (r.get("args") or {}).values()
        )
        else list(forbidden_raw)
    )
    weights = data.get("weights")
    if weights is not None and not isinstance(weights, dict):
        raise ValueError("'weights' must be an object")
    return Contract(
        required=required,
        optional=optional,
        forbidden=forbidden,
        weights={k: float(v) for k, v in weights.items()} if weights else None,
        min_score=float(data.get("min_score", 0.9)),
    )


def is_contract(data: Any) -> TypeGuard[dict[str, Any]]:
    """Whether parsed JSON is a contract (it has ``contract_version``, or ``required``/``optional``)."""
    return isinstance(data, dict) and (
        "contract_version" in data or "required" in data or "optional" in data
    )


def load_contract(path: str | Path) -> Contract:
    """Read a contract file (JSON, or YAML with ``tool-scorer[yaml]``)."""
    from toolscore.mcp.fixtures import load_structured_file

    return contract_from_mapping(load_structured_file(path))


def _matches_entry(call: dict[str, Any], entry: dict[str, Any]) -> bool:
    return call_matches_rule(str(call.get("tool")), call.get("args"), entry)


def split_optional(
    actual: list[dict[str, Any]], required: list[dict[str, Any]], optional: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[int]]:
    """Leave out optional calls that are not needed to fill a required call.

    Walks the calls in order. A call matching an optional entry is dropped when
    the required calls of its tool are already filled by earlier calls (or the
    tool is not required at all); otherwise it is kept and fills one.

    Returns:
        ``(scored calls, indexes of the optional calls left out)``.
    """
    needed: dict[str, int] = {}
    for call in required:
        needed[call["tool"]] = needed.get(call["tool"], 0) + 1
    seen: dict[str, int] = {}
    kept: list[dict[str, Any]] = []
    dropped: list[int] = []
    for index, call in enumerate(actual):
        tool = str(call.get("tool"))
        is_optional = any(_matches_entry(call, entry) for entry in optional)
        if is_optional and seen.get(tool, 0) >= needed.get(tool, 0):
            dropped.append(index)
            continue
        seen[tool] = seen.get(tool, 0) + 1
        kept.append(call)
    return kept, dropped


def evaluate_contract(
    contract: Contract | dict[str, Any],
    actual: list[dict[str, Any]] | Any,
    weights: dict[str, float] | None = None,
    strict: bool = False,
    final_answer: str | None = None,
    honesty: HonestyConfig | None = None,
) -> EvaluationResult:
    """Evaluate tool calls against a contract.

    Args:
        contract: A :class:`Contract` or a contract mapping.
        actual: The calls (dicts, or any raw format :func:`toolscore.evaluate` reads).
        weights: Score weights (default: the contract's).
        strict: Exact argument comparison.
        final_answer: The agent's final answer, for the honesty checks.
        honesty: Honesty-check configuration.

    Returns:
        The evaluation of the best combination of alternatives, with
        ``metrics["contract_metrics"]``: ``contract_version``, ``alternatives``
        (the option chosen per group and every combination's score),
        ``optional_matched`` (the optional calls left out of the score) and the
        counts of required, optional and forbidden entries. ``trace_calls``
        holds every call, optional ones included.
    """
    from toolscore.core import (
        _add_trace_checks,
        _dicts_to_tool_calls,
        evaluate,
    )
    from toolscore.integrations import auto_extract
    from toolscore.transcript import final_answer_of

    parsed = contract if isinstance(contract, Contract) else contract_from_mapping(contract)
    final_source: str | None = "provided" if final_answer else None
    if not final_answer and isinstance(actual, (dict, list)):
        final_answer, final_source = final_answer_of(actual)
    calls = auto_extract(actual)
    if not isinstance(calls, list):
        raise TypeError("actual must be a list of call dicts or a supported trace")
    use_weights = weights if weights is not None else parsed.weights

    best: tuple[float, EvaluationResult, dict[str, int], list[int]] | None = None
    scores: list[dict[str, Any]] = []
    for required, picked in parsed.expansions():
        kept, dropped = split_optional(calls, required, parsed.optional)
        result = evaluate(
            required, kept, weights=use_weights, strict=strict, final_answer=final_answer or None
        )
        scores.append({"choice": picked, "score": result.score})
        if best is None or result.score > best[0] + 1e-12:
            best = (result.score, result, picked, dropped)
    assert best is not None
    _, result, picked, dropped = best

    # Every call, optional ones included, for the records and the trace checks.
    result.trace_calls = _dicts_to_tool_calls(calls)
    if final_answer is None and result.trace_calls:
        final_answer, final_source = final_answer_of(None, result.trace_calls)
    _add_trace_checks(
        result,
        result.gold_calls,
        result.trace_calls,
        parsed.forbidden or None,
        final_answer=final_answer,
        final_source=final_source,
        honesty=honesty,
    )
    result.metrics["contract_metrics"] = {
        "contract_version": CONTRACT_VERSION,
        "required_count": len(result.gold_calls),
        "optional_count": len(parsed.optional),
        "forbidden_count": len(parsed.forbidden),
        "alternatives": {
            "chosen": {
                group.id: {
                    "option": picked[group.id],
                    "calls": [c["tool"] for c in group.options[picked[group.id]]],
                }
                for group in parsed.groups
            },
            "combinations": scores if parsed.groups else [],
        },
        "optional_matched": [
            {"index": index, "tool": str(calls[index].get("tool"))} for index in dropped
        ],
        "min_score": parsed.min_score,
        "passed": result.score >= parsed.min_score - 1e-9,
    }
    return result


def contract_to_jsonable(contract: Contract) -> dict[str, Any]:
    """A contract as plain data (matchers as their ``repr``), for hashing and records."""
    from toolscore.core import _json_safe

    def item(entry: dict[str, Any] | AlternativeGroup) -> Any:
        if isinstance(entry, AlternativeGroup):
            return {"id": entry.id, "alternatives": entry.options}
        return entry

    return dict(
        _json_safe(
            {
                "contract_version": CONTRACT_VERSION,
                "required": [item(e) for e in contract.required],
                "optional": contract.optional,
                "forbidden": contract.forbidden,
                "weights": contract.weights,
                "min_score": contract.min_score,
            }
        )
    )


def contract_file_data(path: str | Path) -> Any:
    """Parsed JSON or YAML of a gold or contract file."""
    from toolscore.mcp.fixtures import load_structured_file

    return (
        load_structured_file(path)
        if Path(path).suffix in (".yaml", ".yml")
        else json.loads(Path(path).read_text(encoding="utf-8"))
    )
