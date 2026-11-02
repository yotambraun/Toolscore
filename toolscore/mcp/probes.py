"""Effect probes: check that a tool really did what it reported.

The scorecard's scenarios check that each tool *answers*. A tool can answer
"success" and still do nothing, lose data, or return the wrong content: the
official MCP memory server's ``create_entities`` reported success while it
skipped entities that already existed (modelcontextprotocol/servers#4887), its
graph file lost unreadable lines on the next write (#4885), and the filesystem
server's ``head: 0`` returned the whole file (#4178). None of these is an error,
so none of them lowers a pass rate. Probes check invariants instead:

**Round trips** (need ``allow_writes``). For a tool that stores something
(``create``, ``add``, ``update``, ``write``, ``set``, ``save``... in its name,
or ``readOnlyHint: false`` with ``destructiveHint: false``), the probe writes
values carrying a unique marker (``tsp<hex>-<field>``), then reads them back
through the server's read tools:

* ``probe-write-not-observable``: the write reported success, but no read tool
  shows the marker.
* ``probe-silent-noop``: a second write to the same key (the same ``name``,
  ``id``, ``title``, ``path``...) with new values reported success, did not say
  it skipped anything, and a read tool that showed the first values does not
  show the new ones: *reported success, state unchanged*.
* ``probe-data-lost``: a record that a read tool showed earlier is gone after a
  later write of a different record.

**Bounds** (read-only). A parameter named ``head`` or ``tail`` (lines) or
``limit``, ``max_results``, ``top_k``, ``page_size``... (items) of a read-only
tool must bound the result:

* ``probe-bound-exceeded``: ``N`` asked for, more returned.
* ``probe-bound-short``: fewer than ``min(N, all)`` returned, where ``all`` is
  the count without the parameter.
* ``probe-slice-mismatch``: ``head``/``tail`` content is not the start/end of
  the full content.

**Declared relations.** A probe config file adds bounds for any tool,
two-path agreements (``probe-paths-disagree``: ``search`` results missing from
``list``) and idempotency (``probe-not-idempotent``: the same read twice gives
different results).

Confidence decides what a failure does. ``high`` (declared in the config, or a
read tool that has already shown this record) is an error: it lowers the score
and caps the grade at C (see :mod:`toolscore.mcp.scorecard`).
``medium`` (inferred from names, such as a ``limit`` parameter or a read tool
that shares a word with the write tool) and ``low`` (any other read tool) are
warnings that never change the grade. Every result says how the pairing or the
relation was chosen (``basis``).

Probes that write run only with ``allow_writes=True`` (``--allow-writes``) and
leave marker records behind: point them at a disposable instance of the server.
"""

from __future__ import annotations

import copy
import json
import random
import re
import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from toolscore.generators.synthetic import generate_value_from_schema, primary_schema_type
from toolscore.mcp.client import MCPError
from toolscore.mcp.fixtures import ArgumentFixtures, load_structured_file
from toolscore.mcp.lint_rules import _READ_VERBS, _name_words

if TYPE_CHECKING:
    from pathlib import Path

    from toolscore.mcp.client import MCPClient, MCPToolDef

#: Verbs in a tool name that mean it stores something that can be read back.
STORE_VERBS = frozenset(
    {
        "create", "add", "update", "write", "set", "save", "put", "insert", "upsert",
        "append", "edit", "modify", "store", "remember", "record",
    }
)  # fmt: skip

#: Last word of a field name that identifies a record (kept on the second write).
_KEY_WORDS = frozenset(
    {"name", "id", "key", "title", "path", "slug", "uri", "url", "filename", "email", "username"}
)
#: Last word of a read parameter that takes the text to look for.
_QUERY_WORDS = frozenset(
    {"query", "q", "search", "term", "terms", "keyword", "keywords", "text", "pattern", "filter"}
)
#: Normalized names of parameters that cap how many lines a tool returns.
_HEAD_PARAMS = frozenset({"head"})
_TAIL_PARAMS = frozenset({"tail"})
#: Normalized names of parameters that cap how many items a tool returns.
_LIMIT_PARAMS = frozenset(
    {
        "limit", "maxresults", "topk", "topn", "maxitems", "pagesize", "perpage",
        "nresults", "numresults", "first", "last",
    }
)  # fmt: skip
#: Value passed to a reader's limit-like parameter so a probe record is on the page.
_READ_LIMIT = 100
#: At most this many read tools are tried for one write tool.
_MAX_READERS = 6
#: Characters of a result kept as evidence.
_EVIDENCE_CHARS = 160

#: Result text that says a write was skipped or refused, which makes "nothing
#: changed" an honest answer rather than a silent no-op.
_SKIP_RE = re.compile(
    r"\b(?:skip(?:ped|s)?|already\s+(?:exists?|present|there)|exists?|existing|duplicates?"
    r"|unchanged|ignored|not\s+(?:created|updated|modified|changed|added|saved|written))\b",
    re.IGNORECASE,
)

PROBE_RULES: dict[str, str] = {
    "probe-write-not-observable": "a write reported success but no read tool shows it",
    "probe-silent-noop": "a second write to the same key reported success and changed nothing",
    "probe-data-lost": "a record shown earlier is gone after a later write",
    "probe-bound-exceeded": "more lines or items returned than the bound parameter allows",
    "probe-bound-short": "fewer lines or items returned than the bound and the data allow",
    "probe-slice-mismatch": "head/tail content is not the start/end of the full content",
    "probe-paths-disagree": "two tools that should agree return different items",
    "probe-not-idempotent": "the same read returns different results",
}
"""Every probe rule ID with a one-line meaning."""

_FIX_ROUND_TRIP = (
    "Make the tool report what it did: return an error, or say which items were skipped, "
    "instead of success when nothing was stored."
)
_FIX_DATA_LOST = (
    "Writes must keep records they did not touch; check how the store is rewritten on save."
)
_FIX_BOUND = "Return exactly the requested number of lines or items (and none for 0)."
_FIX_AGREE = "Make both tools read the same data, or document why they differ."
_FIX_IDEMPOTENT = "A read-only call with the same arguments should return the same result."
_FIX_NOT_OBSERVABLE = (
    "Check the write really stores the value. If it does, declare the read tool to use in a "
    "probe config (pairs) so the probe can see it."
)


@dataclass
class ProbeResult:
    """The outcome of one probe.

    Attributes:
        probe: ``"round-trip"``, ``"bound"``, ``"agreement"`` or ``"idempotent"``.
        tool: The tool under test.
        status: ``"pass"``, ``"fail"``, ``"inconclusive"`` (the probe could not
            run, for example the write failed with generated values) or
            ``"skipped"`` (not run, for example writes not allowed).
        rule: The rule ID of a failure (see :data:`PROBE_RULES`); empty otherwise.
        confidence: ``"high"``, ``"medium"`` or ``"low"`` (see the module docstring);
            empty for skipped probes and round trips that could not run.
        message: What happened.
        basis: How the read tool or the relation was chosen.
        fix: A suggested fix for a failure.
        evidence: The calls the probe made: ``tool``, ``arguments``, ``is_error``
            and a short ``excerpt`` of the result.
        check: What was checked within the probe: the bound parameter, or the
            declared relation's ``id``; empty for round trips.
    """

    probe: str
    tool: str
    status: str
    rule: str = ""
    confidence: str = ""
    message: str = ""
    basis: str = ""
    fix: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    check: str = ""

    @property
    def severity(self) -> str | None:
        """``"error"`` for a high-confidence failure, ``"warning"`` for others, else ``None``."""
        if self.status != "fail":
            return None
        return "error" if self.confidence == "high" else "warning"

    @property
    def graded(self) -> bool:
        """Whether this result counts toward the grade (a high-confidence pass or fail)."""
        return self.confidence == "high" and self.status in ("pass", "fail")


# -- configuration ----------------------------------------------------------


@dataclass
class RoundTripPair:
    """A declared write tool and the read tool that shows what it wrote.

    Attributes:
        write: The write tool.
        read: The read tool.
        read_args: Arguments for the read tool; ``"{key}"`` in a string is
            replaced by the record's key value and ``"{marker}"`` by its first
            marker.
        write_args: Arguments for the write tool, on top of generated values.
        key: Field names that identify a record (overrides the name heuristic).
    """

    write: str
    read: str
    read_args: dict[str, Any] | None = None
    write_args: dict[str, Any] = field(default_factory=dict)
    key: list[str] | None = None


@dataclass
class BoundRelation:
    """A declared bound: ``param = N`` must return at most (or exactly) N lines or items.

    Attributes:
        tool: The tool.
        param: The bound parameter.
        values: The ``N`` values to try.
        expect: ``"at_most"``, ``"exact"`` (``min(N, all)``), ``"prefix"`` or
            ``"suffix"`` (exact, and the start/end of the full content).
        args: The other arguments.
        unit: ``"lines"``, ``"items"`` or ``"auto"`` (items when the result is a
            list, else lines).
        id: A name for the relation, shown in reports.
    """

    tool: str
    param: str
    values: list[int]
    expect: str = "exact"
    args: dict[str, Any] = field(default_factory=dict)
    unit: str = "auto"
    id: str = ""


@dataclass
class CallSpec:
    """One tool call in a declared relation."""

    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    field: str | None = None


@dataclass
class Agreement:
    """Two calls whose items should agree (``left`` within ``right``, or equal).

    Attributes:
        left: The first call (``field`` picks a key of dict items).
        right: The second call.
        expect: ``"subset"`` (every left item is in right) or ``"equal"``.
        id: A name for the relation.
    """

    left: CallSpec
    right: CallSpec
    expect: str = "subset"
    id: str = ""


@dataclass
class ProbeConfig:
    """What to probe. Every field is optional; the defaults probe by heuristics.

    Attributes:
        args: Known-good argument values (as for ``--args-file``).
        builtins: Run the built-in bound relations on read-only tools.
        writes: Extra tools to treat as write tools for round trips.
        exclude: Tools never probed.
        pairs: Declared round-trip pairs (high confidence).
        relations: Declared bound relations (high confidence).
        agreements: Declared two-path agreements (high confidence).
        idempotent: Declared calls that must return the same result twice.
    """

    args: ArgumentFixtures = field(default_factory=ArgumentFixtures)
    builtins: bool = True
    writes: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    pairs: list[RoundTripPair] = field(default_factory=list)
    relations: list[BoundRelation] = field(default_factory=list)
    agreements: list[Agreement] = field(default_factory=list)
    idempotent: list[CallSpec] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: Any) -> ProbeConfig:
        """Build a config from parsed JSON or YAML (see ``docs/effect_probes.rst``).

        Raises:
            ValueError: On an unknown key or a malformed entry.
        """
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("a probe config must be a mapping")
        known = {
            "args", "builtins", "writes", "exclude", "pairs", "relations", "agreements",
            "idempotent",
        }  # fmt: skip
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown probe config key(s): {sorted(unknown)}")
        try:
            return cls(
                args=ArgumentFixtures.from_mapping(data.get("args")),
                builtins=bool(data.get("builtins", True)),
                writes=_names(data.get("writes", []), "writes"),
                exclude=_names(data.get("exclude", []), "exclude"),
                pairs=[_pair(_entry(p, "pairs")) for p in data.get("pairs", [])],
                relations=[_relation(_entry(r, "relations")) for r in data.get("relations", [])],
                agreements=[
                    _agreement(_entry(a, "agreements")) for a in data.get("agreements", [])
                ],
                idempotent=[
                    CallSpec(**_entry(c, "idempotent")) for c in data.get("idempotent", [])
                ],
            )
        except TypeError as exc:
            raise ValueError(f"malformed probe config entry: {exc}") from exc


def _names(value: Any, key: str) -> list[str]:
    """A list of names; a bare string is an error, not a list of characters."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"probe config {key!r} must be a list of names, got {value!r}")
    return list(value)


def _pair(data: dict[str, Any]) -> RoundTripPair:
    pair = RoundTripPair(**data)
    if pair.key is not None:
        pair.key = _names(pair.key, "key")
    return pair


def _entry(value: Any, section: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"each entry of {section!r} must be a mapping, got {value!r}")
    return value


def _relation(data: dict[str, Any]) -> BoundRelation:
    relation = BoundRelation(**data)
    if relation.expect not in ("at_most", "exact", "prefix", "suffix"):
        raise ValueError(f"relation expect must be at_most, exact, prefix or suffix: {data!r}")
    if relation.unit not in ("auto", "lines", "items"):
        raise ValueError(f"relation unit must be auto, lines or items: {data!r}")
    if not relation.values or not all(
        isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in relation.values
    ):
        raise ValueError(f"relation values must be non-negative integers: {data!r}")
    return relation


def _agreement(data: dict[str, Any]) -> Agreement:
    left, right = data.get("left"), data.get("right")
    if not isinstance(left, dict) or not isinstance(right, dict):
        raise ValueError(f"an agreement needs left and right calls: {data!r}")
    agreement = Agreement(
        left=CallSpec(**left),
        right=CallSpec(**right),
        expect=str(data.get("expect", "subset")),
        id=str(data.get("id", "")),
    )
    if agreement.expect not in ("subset", "equal"):
        raise ValueError(f"agreement expect must be subset or equal: {data!r}")
    return agreement


def load_probe_config(path: str | Path) -> ProbeConfig:
    """Read a probe config file (JSON, or YAML with PyYAML installed)."""
    return ProbeConfig.from_mapping(load_structured_file(path))


# -- small helpers ------------------------------------------------------------


def _norm(name: str) -> str:
    """A parameter name lowercased without separators (``maxResults`` -> ``maxresults``)."""
    return re.sub(r"[_\-\s.]", "", name).lower()


def _last_word(name: str) -> str:
    words = _name_words(name)
    return words[-1] if words else ""


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _properties(tool: MCPToolDef) -> dict[str, Any]:
    schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
    properties = schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def _required(tool: MCPToolDef) -> list[str]:
    schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
    required = schema.get("required")
    return [r for r in required if isinstance(r, str)] if isinstance(required, list) else []


def is_read_tool(tool: MCPToolDef) -> bool:
    """Whether a tool only reads: ``readOnlyHint: true``, or a read verb first and no hint against it."""
    hints = tool.annotations if isinstance(tool.annotations, dict) else {}
    if hints.get("readOnlyHint") is True:
        return True
    if hints.get("readOnlyHint") is False:
        return False
    words = _name_words(tool.name)
    return bool(words) and words[0] in _READ_VERBS


def write_basis(tool: MCPToolDef) -> str | None:
    """Why a tool counts as a write tool for round trips, or ``None`` if it does not."""
    hints = tool.annotations if isinstance(tool.annotations, dict) else {}
    if hints.get("readOnlyHint") is True or hints.get("destructiveHint") is True:
        return None
    words = _name_words(tool.name)
    if words and words[0] in _READ_VERBS:
        return None
    verbs = [w for w in words if w in STORE_VERBS]
    if verbs:
        return f"its name says it stores ({verbs[0]!r})"
    if hints.get("readOnlyHint") is False and hints.get("destructiveHint") is False:
        return "annotations readOnlyHint: false, destructiveHint: false"
    return None


def _nouns(tool: MCPToolDef) -> set[str]:
    return {
        _singular(w)
        for w in _name_words(tool.name)
        if w not in STORE_VERBS and w not in _READ_VERBS and len(w) > 2
    }


def _text_of(result: Any) -> str:
    """The text of a result plus its structured content, for marker searches."""
    text = result.text if result is not None else ""
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        text += "\n" + json.dumps(structured, ensure_ascii=False, sort_keys=True)
    return text


def _excerpt(text: str) -> str:
    collapsed = " ".join(text.split())
    return (
        collapsed if len(collapsed) <= _EVIDENCE_CHARS else collapsed[: _EVIDENCE_CHARS - 1] + "…"
    )


class _Caller:
    """Calls tools for a probe and keeps the evidence."""

    def __init__(self, client: MCPClient) -> None:
        self.client = client
        self.evidence: list[dict[str, Any]] = []

    def call(self, tool: str, arguments: dict[str, Any]) -> tuple[bool, Any, str]:
        """Call a tool. Returns ``(ok, result or None, text)``; transport errors count as not ok."""
        try:
            result = self.client.call_tool(tool, arguments)
        except MCPError as exc:
            self.evidence.append(
                {"tool": tool, "arguments": arguments, "is_error": True, "excerpt": str(exc)}
            )
            return False, None, str(exc)
        text = _text_of(result)
        self.evidence.append(
            {
                "tool": tool,
                "arguments": arguments,
                "is_error": result.is_error,
                "excerpt": _excerpt(result.text),
            }
        )
        return not result.is_error, result, text

    def take(self) -> list[dict[str, Any]]:
        evidence, self.evidence = self.evidence, []
        return evidence


# -- round trips -------------------------------------------------------------


@dataclass
class _Record:
    """The arguments of one probe write and the marker strings it carries."""

    args: dict[str, Any]
    markers: dict[tuple[Any, ...], str]
    key_paths: set[tuple[Any, ...]]

    @property
    def key_markers(self) -> list[str]:
        return [v for p, v in self.markers.items() if p in self.key_paths]

    @property
    def value_markers(self) -> list[str]:
        return [v for p, v in self.markers.items() if p not in self.key_paths]

    @property
    def key_value(self) -> str | None:
        keys = self.key_markers
        if keys:
            return keys[0]
        for path, value in _strings(self.args):
            if path and isinstance(path[-1], str) and _last_word(path[-1]) in _KEY_WORDS:
                return value
        return None

    def first_marker(self) -> str:
        values = self.key_markers or self.value_markers
        return values[0] if values else ""


def _strings(value: Any, path: tuple[Any, ...] = ()) -> list[tuple[tuple[Any, ...], str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, dict):
        return [item for k, v in value.items() for item in _strings(v, (*path, k))]
    if isinstance(value, list):
        return [item for i, v in enumerate(value) for item in _strings(v, (*path, i))]
    return []


def _is_key_field(name: str, key_fields: list[str] | None) -> bool:
    if key_fields is not None:
        return _norm(name) in {_norm(k) for k in key_fields}
    return _last_word(name) in _KEY_WORDS


def _marked_value(
    name: str,
    schema: Any,
    token: str,
    path: tuple[Any, ...],
    rng: random.Random,
    record: _Record,
    key_fields: list[str] | None,
    depth: int = 0,
) -> Any:
    """A value for one property; strings carry ``<token>-<name>`` markers."""
    schema = schema if isinstance(schema, dict) else {}
    kind = primary_schema_type(schema)
    if kind == "string" and not schema.get("enum") and not schema.get("format"):
        marker = f"{token}-{_norm(name) or 'value'}"
        record.markers[path] = marker
        if _is_key_field(name, key_fields):
            record.key_paths.add(path)
        return marker
    if kind == "array" and depth < 4:
        items = schema.get("items")
        item_name = _singular(name)
        return [
            _marked_value(item_name, items, token, (*path, 0), rng, record, key_fields, depth + 1)
        ]
    if kind == "object" and depth < 4 and isinstance(schema.get("properties"), dict):
        required = set(schema.get("required") or [])
        value: dict[str, Any] = {}
        for prop, sub in schema["properties"].items():
            sub_kind = primary_schema_type(sub if isinstance(sub, dict) else {})
            if prop in required or sub_kind in ("string", "array"):
                value[prop] = _marked_value(
                    prop, sub, token, (*path, prop), rng, record, key_fields, depth + 1
                )
        return value
    return generate_value_from_schema(name, schema, "normal", rng)


def _write_record(
    tool: MCPToolDef,
    fixtures: ArgumentFixtures,
    extra: dict[str, Any],
    key_fields: list[str] | None,
    keep_keys: _Record | None = None,
) -> _Record:
    """Build marked write arguments; ``keep_keys`` reuses another record's key values."""
    token = "tsp" + secrets.token_hex(3)
    rng = random.Random(tool.name)
    record = _Record(args={}, markers={}, key_paths=set())
    required = set(_required(tool))
    for name, schema in _properties(tool).items():
        kind = primary_schema_type(schema if isinstance(schema, dict) else {})
        if name in required or kind in ("string", "array"):
            record.args[name] = _marked_value(name, schema, token, (name,), rng, record, key_fields)
    for name, value in {**fixtures.for_tool(tool), **extra}.items():
        record.args[name] = copy.deepcopy(value)
        for path in [p for p in record.markers if p[0] == name]:
            del record.markers[path]
            record.key_paths.discard(path)
    if keep_keys is not None:
        for path in keep_keys.key_paths:
            if path in keep_keys.markers and path in record.markers:
                _set_path(record.args, path, keep_keys.markers[path])
                record.markers[path] = keep_keys.markers[path]
    return record


def _set_path(target: Any, path: tuple[Any, ...], value: Any) -> None:
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value


def _reader_args(
    reader: MCPToolDef,
    record: _Record,
    fixtures: ArgumentFixtures,
    declared: dict[str, Any] | None,
) -> dict[str, Any]:
    """Arguments that make ``reader`` show ``record``."""
    if declared is not None:
        substituted = _substitute(declared, record)
        return substituted if isinstance(substituted, dict) else {}
    written = {
        _norm(str(path[-1])): value
        for path, value in _strings(record.args)
        if path and isinstance(path[-1], str)
    }
    rng = random.Random(reader.name)
    args: dict[str, Any] = {}
    required = set(_required(reader))
    for name, schema in _properties(reader).items():
        schema = schema if isinstance(schema, dict) else {}
        kind = primary_schema_type(schema)
        norm = _norm(name)
        match = written.get(norm) or written.get(_singular(norm))
        if match is not None and kind in ("string", "array"):
            args[name] = [match] if kind == "array" else match
        elif _last_word(name) in _QUERY_WORDS and kind == "string":
            args[name] = record.key_value or record.first_marker()
        elif norm in _LIMIT_PARAMS and kind in ("integer", "number"):
            maximum = schema.get("maximum")
            args[name] = (
                min(_READ_LIMIT, int(maximum))
                if isinstance(maximum, (int, float)) and not isinstance(maximum, bool)
                else _READ_LIMIT
            )
        elif name in required:
            args[name] = generate_value_from_schema(name, schema, "normal", rng)
    for name, value in fixtures.for_tool(reader).items():
        args.setdefault(name, value)
    return args


def _substitute(value: Any, record: _Record) -> Any:
    if isinstance(value, str):
        return value.replace("{key}", record.key_value or "").replace(
            "{marker}", record.first_marker()
        )
    if isinstance(value, dict):
        return {k: _substitute(v, record) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, record) for v in value]
    return value


def _reports_skip(text: str) -> bool:
    """Whether a write result says it skipped or refused something.

    A JSON field named like ``skipped`` counts only when it is not empty, so
    ``{"created": [...], "skipped": []}`` is not a skip report.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return _SKIP_RE.search(text) is not None

    def walk(node: Any) -> bool:
        if isinstance(node, dict):
            return any(
                (bool(v) if _SKIP_RE.search(str(k)) else False) or walk(v) for k, v in node.items()
            )
        if isinstance(node, list):
            return any(walk(v) for v in node)
        return isinstance(node, str) and _SKIP_RE.search(node) is not None

    return walk(data)


@dataclass
class _Reader:
    tool: MCPToolDef
    confidence: str
    basis: str
    declared_args: dict[str, Any] | None = None


def _readers_for(
    write: MCPToolDef, tools: list[MCPToolDef], config: ProbeConfig
) -> tuple[list[_Reader], RoundTripPair | None]:
    by_name = {t.name: t for t in tools}
    declared = [p for p in config.pairs if p.write == write.name]
    if declared:
        readers = [
            _Reader(by_name[p.read], "high", f"declared pair {p.write} -> {p.read}", p.read_args)
            for p in declared
            if p.read in by_name
        ]
        return readers, declared[0]
    nouns = _nouns(write)
    shared: list[_Reader] = []
    other: list[_Reader] = []
    for tool in tools:
        if tool.name == write.name or tool.name in config.exclude or not is_read_tool(tool):
            continue
        common = sorted(nouns & _nouns(tool))
        if common:
            shared.append(
                _Reader(tool, "medium", f"read tool sharing the word {common[0]!r} with the write")
            )
        else:
            other.append(_Reader(tool, "low", "read-only tool on the same server"))
    return (shared + other)[:_MAX_READERS], None


def _probe_round_trip(
    caller: _Caller,
    write: MCPToolDef,
    tools: list[MCPToolDef],
    config: ProbeConfig,
    basis: str,
) -> ProbeResult:
    readers, pair = _readers_for(write, tools, config)
    extra = pair.write_args if pair else {}
    key_fields = pair.key if pair else None
    fixtures = config.args

    def result(status: str, **kwargs: Any) -> ProbeResult:
        return ProbeResult(
            probe="round-trip", tool=write.name, status=status, evidence=caller.take(), **kwargs
        )

    if not readers:
        return result("inconclusive", message="no read tool to check the write with", basis=basis)

    first = _write_record(write, fixtures, extra, key_fields)
    if not first.markers:
        return result(
            "inconclusive",
            message="the write takes no free-text field to trace",
            basis=basis,
        )
    ok, _, text = caller.call(write.name, first.args)
    if not ok:
        return result(
            "inconclusive",
            message=f"the write failed with probe values ({_excerpt(text)}); supply values with --arg",
            basis=basis,
        )

    def visible(reader: _Reader, record: _Record) -> tuple[bool, list[str]]:
        args = _reader_args(reader.tool, record, fixtures, reader.declared_args)
        ok, _, text = caller.call(reader.tool.name, args)
        return ok, [m for m in record.markers.values() if m in text]

    seen: dict[str, list[str]] = {}
    answered = []
    for reader in readers:
        ok, found = visible(reader, first)
        if ok:
            answered.append(reader)
        if found:
            seen[reader.tool.name] = found
    if not answered:
        return result(
            "inconclusive", message="no read tool answered with probe values", basis=basis
        )
    if not seen:
        best = answered[0]
        return result(
            "fail",
            rule="probe-write-not-observable",
            confidence=best.confidence,
            message=(
                "reported success, but "
                f"{', '.join(r.tool.name for r in answered)} do not show the value"
            ),
            basis=best.basis,
            fix=_FIX_NOT_OBSERVABLE,
        )

    confirmed = [r for r in answered if r.tool.name in seen]
    with_values = [r for r in confirmed if any(m in first.value_markers for m in seen[r.tool.name])]
    names = ", ".join(r.tool.name for r in confirmed)
    confirmed_basis = f"{names} showed the first write"

    # Same key, new values: a silent no-op answers success and changes nothing.
    latest = first
    skip_reported = False
    if first.key_markers and with_values:
        second = _write_record(write, fixtures, extra, key_fields, keep_keys=first)
        ok, _, text = caller.call(write.name, second.args)
        skip_reported = ok and _reports_skip(text)
        if ok and not skip_reported:
            shown = False
            for reader in with_values:
                found = visible(reader, second)[1]
                if any(m in found for m in second.value_markers):
                    shown = True
                    break
            if not shown:
                return result(
                    "fail",
                    rule="probe-silent-noop",
                    confidence="high",
                    message=(
                        f"a second write to key {first.key_markers[0]!r} reported success; "
                        "state unchanged"
                    ),
                    basis=confirmed_basis,
                    fix=_FIX_ROUND_TRIP,
                )
            latest = second

    # A different record: the first must survive it.
    other = _write_record(write, fixtures, extra, key_fields)
    ok, _, _ = caller.call(write.name, other.args)
    if ok:
        expected = latest.key_markers or latest.value_markers
        for reader in confirmed:
            answered_again, found = visible(reader, latest)
            if not answered_again:
                continue  # a failed read proves nothing about the stored data
            lost = [m for m in expected if m in seen[reader.tool.name] and m not in found]
            if lost:
                return result(
                    "fail",
                    rule="probe-data-lost",
                    confidence="high",
                    message=(
                        f"{lost[0]!r} is gone from {reader.tool.name} after a write of "
                        "another record"
                    ),
                    basis=confirmed_basis,
                    fix=_FIX_DATA_LOST,
                )

    return result(
        "pass",
        confidence="high",
        message="write visible and kept after another write"
        + ("; a same-key write took effect" if latest is not first else "")
        + ("; a same-key write was reported as skipped" if skip_reported else ""),
        basis=confirmed_basis,
    )


# -- bounds ------------------------------------------------------------------


def _items(result: Any) -> tuple[list[Any] | None, str]:
    """The result as a list of items, and where they came from (``structured``/``json``)."""
    structured = getattr(result, "structured_content", None)
    for source, data in (("structured", structured), ("json", _json_or_none(result))):
        if isinstance(data, list):
            return data, source
        if isinstance(data, dict):
            lists = [v for v in data.values() if isinstance(v, list)]
            if len(lists) == 1:
                return lists[0], source
    return None, ""


def _json_or_none(result: Any) -> Any:
    try:
        return json.loads(result.text) if result is not None else None
    except (json.JSONDecodeError, ValueError):
        return None


def _lines(result: Any) -> list[str]:
    return result.text.splitlines() if result is not None else []


def _measure(result: Any, unit: str) -> tuple[list[Any] | None, str]:
    """Count a result in ``unit``: ``(items or lines, "items"/"lines")``, or ``(None, "")``."""
    if unit != "lines":
        items, _ = _items(result)
        if items is not None:
            return items, "items"
        if unit == "items":
            return None, ""
    return _lines(result), "lines"


def _run_bound(
    caller: _Caller,
    tool: MCPToolDef,
    relation: BoundRelation,
    confidence: str,
    basis: str,
) -> ProbeResult:
    """Check one bound relation; built-in limits counted in lines drop to low confidence."""
    state = {"confidence": confidence}

    def result(status: str, **kwargs: Any) -> ProbeResult:
        return ProbeResult(
            probe="bound",
            tool=tool.name,
            status=status,
            check=relation.id or relation.param,
            confidence=state["confidence"],
            basis=basis,
            evidence=caller.take(),
            **kwargs,
        )

    full: list[Any] | None = None
    full_unit = ""
    if relation.param not in _required(tool):
        ok, response, _ = caller.call(tool.name, dict(relation.args))
        if ok:
            full, full_unit = _measure(response, relation.unit)
    tried = 0
    for n in relation.values:
        ok, response, _ = caller.call(tool.name, {**relation.args, relation.param: n})
        if not ok:
            continue
        got, unit = _measure(response, relation.unit)
        if got is None:
            continue
        tried += 1
        if confidence == "medium" and relation.unit == "auto" and unit == "lines":
            state["confidence"] = "low"
        label = f"{relation.param}={n} returned {len(got)} {unit}"
        if len(got) > n:
            return result(
                "fail",
                rule="probe-bound-exceeded",
                message=f"{label} (at most {n} expected)",
                fix=_FIX_BOUND,
            )
        if full is None or relation.expect == "at_most" or unit != full_unit:
            continue
        want = min(n, len(full))
        if len(got) < want:
            return result(
                "fail",
                rule="probe-bound-short",
                message=f"{label}; {want} expected ({len(full)} without {relation.param})",
                fix=_FIX_BOUND,
            )
        if unit == "lines" and relation.expect in ("prefix", "suffix"):
            expected = full[:n] if relation.expect == "prefix" else (full[-n:] if n else [])
            if got != expected:
                where = "first" if relation.expect == "prefix" else "last"
                return result(
                    "fail",
                    rule="probe-slice-mismatch",
                    message=f"{relation.param}={n} did not return the {where} {n} lines",
                    fix=_FIX_BOUND,
                )
    if not tried:
        return result(
            "inconclusive",
            message=f"no call with {relation.param} succeeded; supply values with --arg",
        )
    return result("pass", message=f"{relation.param} bounded the result for {relation.values}")


def builtin_relations(tool: MCPToolDef, fixtures: ArgumentFixtures) -> list[BoundRelation]:
    """The built-in bound relations for a read-only tool (empty for other tools).

    ``head``/``tail`` integer parameters are tried with 0, 1 and 2 and must
    return exactly that many first/last lines; ``limit``-like ones with 1 and 2
    and must return at most that many items (exactly that many when there are
    enough). 0 is not tried for limits, since some APIs read ``limit: 0`` as
    "no limit".
    """
    if not is_read_tool(tool):
        return []
    properties = _properties(tool)
    required = _required(tool)
    rng = random.Random(tool.name)
    base: dict[str, Any] = {}
    for name in required:
        schema = properties.get(name)
        base[name] = generate_value_from_schema(
            name, schema if isinstance(schema, dict) else {}, "normal", rng
        )
    base.update(fixtures.for_tool(tool))
    relations: list[BoundRelation] = []
    for name, schema in properties.items():
        if primary_schema_type(schema if isinstance(schema, dict) else {}) not in (
            "integer",
            "number",
        ):
            continue
        norm = _norm(name)
        args = {k: v for k, v in base.items() if k != name}
        if norm in _HEAD_PARAMS or norm in _TAIL_PARAMS:
            expect = "prefix" if norm in _HEAD_PARAMS else "suffix"
            relations.append(
                BoundRelation(tool.name, name, [0, 1, 2], expect, args, "lines", f"builtin-{norm}")
            )
        elif norm in _LIMIT_PARAMS:
            relations.append(
                BoundRelation(tool.name, name, [1, 2], "exact", args, "auto", f"builtin-{norm}")
            )
    return relations


# -- declared agreements and idempotency ----------------------------------------


def _item_set(result: Any, pick: str | None) -> set[str] | None:
    items, _ = _items(result)
    if items is None:
        items = [line for line in _lines(result) if line.strip()]
    values: set[str] = set()
    for item in items:
        if pick is not None:
            if not isinstance(item, dict) or pick not in item:
                return None
            item = item[pick]
        values.add(json.dumps(item, sort_keys=True, ensure_ascii=False))
    return values


def _run_agreement(caller: _Caller, agreement: Agreement) -> ProbeResult:
    name = agreement.id or f"{agreement.left.tool} vs {agreement.right.tool}"

    def result(status: str, **kwargs: Any) -> ProbeResult:
        return ProbeResult(
            probe="agreement",
            tool=agreement.left.tool,
            status=status,
            check=name,
            confidence="high",
            basis=f"declared agreement {name!r}",
            evidence=caller.take(),
            **kwargs,
        )

    ok_left, left, _ = caller.call(agreement.left.tool, dict(agreement.left.args))
    ok_right, right, _ = caller.call(agreement.right.tool, dict(agreement.right.args))
    if not (ok_left and ok_right):
        return result("inconclusive", message="one of the calls failed")
    left_items = _item_set(left, agreement.left.field)
    right_items = _item_set(right, agreement.right.field)
    if left_items is None or right_items is None:
        return result("inconclusive", message="could not read items from the results")
    missing = sorted(left_items - right_items)
    extra = sorted(right_items - left_items) if agreement.expect == "equal" else []
    if missing or extra:
        detail = (
            f"{len(missing)} item(s) from {agreement.left.tool} missing in {agreement.right.tool}"
            + (f" (e.g. {missing[0]})" if missing else "")
            + (f"; {len(extra)} extra" if extra else "")
        )
        return result("fail", rule="probe-paths-disagree", message=detail, fix=_FIX_AGREE)
    return result("pass", message=f"{len(left_items)} item(s) agree ({agreement.expect})")


def _run_idempotent(caller: _Caller, spec: CallSpec) -> ProbeResult:
    def result(status: str, **kwargs: Any) -> ProbeResult:
        return ProbeResult(
            probe="idempotent",
            tool=spec.tool,
            status=status,
            confidence="high",
            basis="declared idempotent call",
            evidence=caller.take(),
            **kwargs,
        )

    ok_a, _, first = caller.call(spec.tool, dict(spec.args))
    ok_b, _, second = caller.call(spec.tool, dict(spec.args))
    if not (ok_a and ok_b):
        return result("inconclusive", message="a call failed")
    if first.strip() != second.strip():
        return result(
            "fail",
            rule="probe-not-idempotent",
            message="two identical calls returned different results",
            fix=_FIX_IDEMPOTENT,
        )
    return result("pass", message="two identical calls returned the same result")


# -- entry point ---------------------------------------------------------------


def run_probes(
    client: MCPClient,
    tools: list[MCPToolDef],
    config: ProbeConfig | None = None,
    allow_writes: bool = False,
    fixtures: ArgumentFixtures | None = None,
) -> list[ProbeResult]:
    """Run the effect probes against a started client.

    Args:
        client: A started MCP client.
        tools: The server's tools (from :meth:`MCPClient.list_tools`).
        config: Declared pairs, relations and argument values; ``None`` probes
            by heuristics only.
        allow_writes: Run probes that call write tools (round trips, and
            declared relations on tools that are not read-only). Off by
            default; writes leave marker records behind.
        fixtures: Extra known-good argument values (``--arg``), on top of the
            config's ``args``.

    Returns:
        One :class:`ProbeResult` per probe, including skipped and inconclusive ones.
    """
    config = config or ProbeConfig()
    if fixtures:
        config = copy.copy(config)
        config.args = config.args.merged(fixtures)
    by_name = {t.name: t for t in tools}
    caller = _Caller(client)
    results: list[ProbeResult] = []

    def writes_ok(tool_name: str, probe: str) -> bool:
        tool = by_name.get(tool_name)
        if allow_writes or (tool is not None and is_read_tool(tool)):
            return True
        results.append(
            ProbeResult(
                probe=probe,
                tool=tool_name,
                status="skipped",
                message="the tool may write; run with --allow-writes to probe it",
            )
        )
        return False

    declared = {(r.tool, r.param) for r in config.relations}
    for relation in config.relations:
        tool = by_name.get(relation.tool)
        if tool is None or relation.tool in config.exclude:
            continue
        if writes_ok(relation.tool, "bound"):
            relation = copy.copy(relation)
            relation.args = {**config.args.for_tool(tool), **relation.args}
            basis = f"declared relation {relation.id!r}" if relation.id else "declared relation"
            results.append(_run_bound(caller, tool, relation, "high", basis))

    if config.builtins:
        for tool in tools:
            if tool.name in config.exclude:
                continue
            for relation in builtin_relations(tool, config.args):
                if (relation.tool, relation.param) in declared:
                    continue
                basis = f"built-in: read-only tool with a {relation.param!r} parameter"
                results.append(_run_bound(caller, tool, relation, "medium", basis))

    for agreement in config.agreements:
        if writes_ok(agreement.left.tool, "agreement") and writes_ok(
            agreement.right.tool, "agreement"
        ):
            results.append(_run_agreement(caller, agreement))

    for spec in config.idempotent:
        if writes_ok(spec.tool, "idempotent"):
            results.append(_run_idempotent(caller, spec))

    paired = {p.write for p in config.pairs}
    for tool in tools:
        if tool.name in config.exclude:
            continue
        if tool.name in paired:
            basis = "declared in the probe config"
        elif tool.name in config.writes:
            basis = "listed under writes in the probe config"
        else:
            basis = write_basis(tool) or ""
        if not basis:
            continue
        if not allow_writes:
            results.append(
                ProbeResult(
                    probe="round-trip",
                    tool=tool.name,
                    status="skipped",
                    message="writes; run with --allow-writes to check the write is stored",
                    basis=basis,
                )
            )
            continue
        results.append(_probe_round_trip(caller, tool, tools, config, basis))

    return results
