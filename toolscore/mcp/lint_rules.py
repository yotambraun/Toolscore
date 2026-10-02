"""Lint rules that read what a model reads: references to missing tools and tool poisoning.

Tool descriptions, parameter descriptions and the server ``instructions`` are all
sent to the model. Two kinds of problems hide in that text:

* **Dangling tool references.** A description tells the model to use a tool the
  server does not expose (for example after a rename, or when a feature flag
  removes it). The model follows the advice and fails. Found in GitHub's official
  MCP server, where ``label_write`` points to an ``update_issue`` tool that does
  not exist.
* **Tool poisoning.** Text meant for the model but hidden from, or concealed
  from, the user: Unicode tag characters (invisible ASCII), bidirectional
  overrides that make text read differently than it is stored, and directives
  such as "do not mention this to the user" or "ignore previous instructions".
  These are the published attack patterns against MCP clients.

Both checks favour precision: a scanner that cries wolf gets ignored.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

    from toolscore.mcp.client import MCPToolDef
    from toolscore.mcp.harness import LintIssue

#: Tool name used for issues found in the server ``instructions``.
INSTRUCTIONS = "<instructions>"

_NAME = r"[A-Za-z][\w.-]*"
_QUOTE = r"[`'\"]"
# "use the 'x' tool", "call `x`", "invoke the "x" tool": a quoted name after a verb.
_AFTER_VERB = re.compile(
    rf"\b(?:use|call|invoke|run|try)\s+(?:the\s+)?{_QUOTE}(?P<name>{_NAME}){_QUOTE}", re.IGNORECASE
)
# "the 'x' tool": a quoted name followed by the word tool.
_BEFORE_TOOL = re.compile(rf"{_QUOTE}(?P<name>{_NAME}){_QUOTE}\s+tool\b", re.IGNORECASE)
# "use the x_y tool": an unquoted snake_case name between a verb and the word tool.
_UNQUOTED = re.compile(
    r"\b(?:use|call|invoke)\s+(?:the\s+)?(?P<name>[a-z][a-z0-9]*(?:_[a-z0-9]+)+)\s+tool\b",
    re.IGNORECASE,
)

_TOOL_WORD = re.compile(r"\s+tool\b", re.IGNORECASE)
_TOOL_SHAPED = re.compile(r"[a-z][a-z0-9]*(?:[_-][a-z0-9]+)+")

#: Characters that carry hidden instructions or make text display differently
#: than it is stored. Never needed in a tool description.
_HIDDEN_RANGES = ((0xE0000, 0xE007F),)  # Unicode tag characters (invisible ASCII)
_BIDI_CONTROLS = frozenset(range(0x202A, 0x202F)) | frozenset(range(0x2066, 0x206A))

#: Directives that only make sense when text is written for a model behind the
#: user's back, taken from published MCP tool-poisoning examples.
_DIRECTIVES = (
    (
        re.compile(
            r"\b(?:do\s+not|don'?t|never)\s+(?:tell|mention|inform|reveal|show|disclose)\b"
            r"[^.\n]{0,60}\buser\b",
            re.IGNORECASE,
        ),
        "tells the model to hide something from the user",
    ),
    (
        re.compile(
            r"\b(?:ignore|disregard|forget)\s+(?:all\s+|any\s+)?(?:the\s+)?"
            r"(?:previous|prior|above|earlier|other)\s+(?:instructions|rules|prompts?)\b",
            re.IGNORECASE,
        ),
        "tells the model to ignore its other instructions",
    ),
    (
        re.compile(r"<\s*/?\s*(?:important|system|instructions?)\s*>", re.IGNORECASE),
        "contains a hidden instruction block (an <IMPORTANT>-style tag)",
    ),
)

_FIX_REFERENCE = "Point the text at a tool this server exposes, or remove the reference."
_FIX_HIDDEN = (
    "Remove the hidden characters. If they were not added on purpose, the text was copied "
    "from a source that injected them; treat the server as compromised until reviewed."
)
_FIX_INVISIBLE = (
    "Remove zero-width and direction marks unless the text needs them (they are normal in "
    "Persian, Hebrew, Arabic and Indic scripts)."
)
_FIX_DIRECTIVE = (
    "Describe what the tool does and what it needs. Instructions to the model that the user "
    "cannot see are the pattern of a tool-poisoning attack."
)


def _texts(tools: list[MCPToolDef], instructions: str | None) -> Iterator[tuple[str, str]]:
    """Yield ``(owner, text)`` for every piece of text a model reads."""
    for tool in tools:
        if tool.description:
            yield tool.name, tool.description
        for text in _schema_descriptions(tool.input_schema):
            yield tool.name, text
    if instructions:
        yield INSTRUCTIONS, instructions


def _schema_descriptions(schema: Any) -> Iterator[str]:
    """Yield every ``description`` string inside a JSON schema."""
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "description" and isinstance(value, str):
                yield value
            else:
                yield from _schema_descriptions(value)
    elif isinstance(schema, list):
        for item in schema:
            yield from _schema_descriptions(item)


def _schema_names(schema: Any) -> set[str]:
    """Property names and string enum/const values anywhere in a JSON schema."""
    names: set[str] = set()
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            names.update(str(key) for key in properties)
        for key in ("enum", "const"):
            values = schema.get(key)
            if isinstance(values, list):
                names.update(v for v in values if isinstance(v, str))
            elif isinstance(values, str):
                names.add(values)
        for value in schema.values():
            names |= _schema_names(value)
    elif isinstance(schema, list):
        for item in schema:
            names |= _schema_names(item)
    return names


def _closest_tool(name: str, tool_names: set[str]) -> str | None:
    """The exposed tool most likely meant by ``name``.

    Tool names are made of words (``update_issue``, ``issue_write``), so shared
    words count first; character similarity breaks ties and covers typos.
    """

    def words(value: str) -> set[str]:
        return {w for w in re.split(r"[_.\-]+|(?<=[a-z])(?=[A-Z])", value.lower()) if w}

    wanted = words(name)
    best: tuple[float, float, str] | None = None
    for candidate in sorted(tool_names):
        shared = len(wanted & words(candidate)) / max(len(wanted | words(candidate)), 1)
        similar = difflib.SequenceMatcher(None, name.lower(), candidate.lower()).ratio()
        if shared == 0 and similar < 0.75:
            continue
        key = (shared, similar, candidate)
        if best is None or key[:2] > best[:2]:
            best = key
    return best[2] if best else None


def dangling_reference_issues(
    tools: list[MCPToolDef], instructions: str | None = None
) -> list[LintIssue]:
    """Find text that tells the model to use a tool the server does not expose.

    A name counts as a tool reference only in phrasing that names a tool: a quoted
    name followed by *tool*; a quoted name after *use/call/invoke/run/try* that is
    shaped like a tool name (``snake_case`` or ``kebab-case``, so fields such as
    ``endCursor`` and values such as ``add`` are not read as tools); or an unquoted
    ``snake_case`` name between *use/call/invoke* and *tool*. Names that
    exist as a tool, a parameter, or an allowed parameter value anywhere in the
    server are not reported (methods such as ``get_comments`` are often values of
    a ``method`` parameter).

    Args:
        tools: The server's tools.
        instructions: The server's ``instructions``, if any.

    Returns:
        One warning per distinct missing name per owner (tool or ``<instructions>``).
    """
    from toolscore.mcp.harness import LintIssue

    tool_names = {tool.name for tool in tools}
    known = set(tool_names)
    for tool in tools:
        known |= _schema_names(tool.input_schema)

    issues: list[LintIssue] = []
    seen: set[tuple[str, str]] = set()
    for owner, text in _texts(tools, instructions):
        for pattern in (_AFTER_VERB, _BEFORE_TOOL, _UNQUOTED):
            for match in pattern.finditer(text):
                name = match.group("name")
                if name in known or (owner, name) in seen:
                    continue
                # "use 'x'" without the word "tool" also names fields and values
                # ("use the 'endCursor' from the response", "use `add` with ..."), so
                # there the name must look like a tool name: lowercase words joined
                # by "_" or "-".
                says_tool = _TOOL_WORD.match(text, match.end()) is not None
                if pattern is _AFTER_VERB and not says_tool and not _TOOL_SHAPED.fullmatch(name):
                    continue
                seen.add((owner, name))
                suggestion = _closest_tool(name, tool_names)
                fix = f"Did you mean {suggestion!r}? " if suggestion else ""
                issues.append(
                    LintIssue(
                        tool=owner,
                        severity="warning",
                        message=f"refers to tool {name!r}, which this server does not expose",
                        fix=fix + _FIX_REFERENCE,
                    )
                )
    return issues


def _hidden_characters(text: str) -> tuple[list[str], list[str], list[str]]:
    """Split suspicious characters into (tag chars, bidi controls, other invisible marks)."""
    tags: list[str] = []
    bidi: list[str] = []
    invisible: list[str] = []
    for char in text:
        code = ord(char)
        if any(low <= code <= high for low, high in _HIDDEN_RANGES):
            tags.append(char)
        elif code in _BIDI_CONTROLS:
            bidi.append(char)
        elif unicodedata.category(char) == "Cf":
            invisible.append(char)
    return tags, bidi, invisible


def poisoning_issues(tools: list[MCPToolDef], instructions: str | None = None) -> list[LintIssue]:
    """Find hidden text and concealment directives in what the model reads.

    Errors:

    * Unicode tag characters (invisible text a model still reads),
    * bidirectional override/isolate controls (text that displays differently than
      it is stored),
    * directives to hide things from the user, to ignore other instructions, or
      ``<IMPORTANT>``-style hidden blocks.

    Warning: other invisible format characters (zero-width characters, direction
    marks, BOM). They are normal in some scripts, so they are only surfaced.

    Tool names are checked for hidden characters too.

    Args:
        tools: The server's tools.
        instructions: The server's ``instructions``, if any.

    Returns:
        The issues found, at most one per kind per owner.
    """
    from toolscore.mcp.harness import LintIssue

    issues: list[LintIssue] = []
    reported: set[tuple[str, str]] = set()

    def add(owner: str, kind: str, severity: str, message: str, fix: str) -> None:
        if (owner, kind) not in reported:
            reported.add((owner, kind))
            issues.append(LintIssue(tool=owner, severity=severity, message=message, fix=fix))

    pieces = [(tool.name, tool.name) for tool in tools]
    pieces.extend(_texts(tools, instructions))
    for owner, text in pieces:
        tags, bidi, invisible = _hidden_characters(text)
        if tags:
            add(
                owner,
                "tags",
                "error",
                f"contains {len(tags)} hidden Unicode tag characters (invisible text the model reads)",
                _FIX_HIDDEN,
            )
        if bidi:
            add(
                owner,
                "bidi",
                "error",
                "contains bidirectional control characters (text displays differently than it is stored)",
                _FIX_HIDDEN,
            )
        if invisible:
            names = sorted({f"U+{ord(c):04X}" for c in invisible})
            add(
                owner,
                "invisible",
                "warning",
                f"contains invisible format characters ({', '.join(names)})",
                _FIX_INVISIBLE,
            )
        for pattern, what in _DIRECTIVES:
            if pattern.search(text):
                add(
                    owner,
                    f"directive:{what}",
                    "error",
                    f"{what}: a tool-poisoning instruction pattern",
                    _FIX_DIRECTIVE,
                )
    return issues
