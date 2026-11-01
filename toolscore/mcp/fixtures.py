"""Known-good argument values for MCP tools: ``--arg`` options and fixture files.

Generated arguments are fine for most tools, but some servers only accept values
from a sandbox: the official filesystem and git servers reject any path outside
their allowed roots, so every generated path fails and the scorecard reads the
correct refusal as a broken tool. :class:`ArgumentFixtures` supplies the values a
server will accept. They replace the generated value in every happy-path
scenario and are the starting arguments of the effect probes
(:mod:`toolscore.mcp.probes`). Edge-case scenarios keep their deliberately bad
values.

Two scopes:

* **shared** values (``--arg path=/tmp/sandbox/notes.txt``) apply to every tool
  whose input schema has a parameter of that name;
* **per-tool** values (``--arg read_text_file:path=/tmp/sandbox/notes.txt``)
  always apply to that tool.

A fixture file holds both, as JSON or YAML (YAML needs PyYAML,
``pip install "tool-scorer[yaml]"``)::

    {
      "*": {"path": "/tmp/sandbox/notes.txt"},
      "list_directory": {"path": "/tmp/sandbox"}
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.mcp.client import MCPToolDef

#: Key of the shared section in a fixture file.
SHARED_KEY = "*"


def load_structured_file(path: str | Path) -> Any:
    """Read a JSON or YAML file (YAML by the ``.yaml``/``.yml`` suffix).

    Args:
        path: The file to read.

    Returns:
        The parsed data.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file cannot be parsed, or it is YAML and PyYAML is
            not installed.
    """
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if file.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise ValueError(
                f"{file} is YAML, which needs PyYAML: pip install 'tool-scorer[yaml]' "
                "(or write the file as JSON)"
            ) from exc
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"{file} is not valid YAML: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{file} is not valid JSON: {exc}") from exc


def parse_value(text: str) -> Any:
    """Read an option value as JSON when it is valid JSON, otherwise as a string.

    ``5`` becomes an integer, ``true`` a boolean and ``["a"]`` a list, while
    ``/tmp/x`` and ``007`` stay strings.
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text


def parse_arg(text: str) -> tuple[str | None, str, Any]:
    """Parse one ``--arg`` option: ``name=value`` or ``tool:name=value``.

    Args:
        text: The option value.

    Returns:
        ``(tool or None, parameter name, value)``.

    Raises:
        ValueError: If there is no ``=`` or the name is empty.
    """
    key, sep, raw = text.partition("=")
    if not sep or not key.strip():
        raise ValueError(f"expected NAME=VALUE or TOOL:NAME=VALUE, got {text!r}")
    tool, colon, name = key.strip().rpartition(":")
    if colon and (not tool or not name):
        raise ValueError(f"expected TOOL:NAME=VALUE, got {text!r}")
    return (tool or None), name, parse_value(raw)


def _schema_properties(tool: MCPToolDef) -> dict[str, Any]:
    schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
    properties = schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def _fit(value: Any, prop_schema: Any) -> Any:
    """Turn a scalar into a string when the parameter is declared a string (``--arg q=123``)."""
    if (
        isinstance(prop_schema, dict)
        and prop_schema.get("type") == "string"
        and isinstance(value, (int, float, bool))
    ):
        return json.dumps(value)
    return value


@dataclass
class ArgumentFixtures:
    """Argument values a server is known to accept.

    Attributes:
        shared: Values applied to every tool that declares a parameter of that name.
        per_tool: Values applied to one tool, by tool name, whether or not its
            schema declares them.
    """

    shared: dict[str, Any] = field(default_factory=dict)
    per_tool: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        """Whether any value is set."""
        return bool(self.shared) or any(self.per_tool.values())

    @classmethod
    def from_mapping(cls, data: Any) -> ArgumentFixtures:
        """Build fixtures from ``{"*": {...}, "<tool>": {...}}``.

        Args:
            data: The parsed fixture mapping.

        Returns:
            The fixtures.

        Raises:
            ValueError: If ``data`` or a section is not a mapping.
        """
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("argument fixtures must be a mapping of tool name to values")
        fixtures = cls()
        for key, values in data.items():
            if not isinstance(values, dict):
                raise ValueError(f"argument fixtures for {key!r} must be a mapping")
            if key == SHARED_KEY:
                fixtures.shared.update(values)
            else:
                fixtures.per_tool.setdefault(str(key), {}).update(values)
        return fixtures

    @classmethod
    def from_options(cls, options: tuple[str, ...] | list[str]) -> ArgumentFixtures:
        """Build fixtures from ``--arg`` option values (see :func:`parse_arg`)."""
        fixtures = cls()
        for option in options:
            tool, name, value = parse_arg(option)
            if tool is None:
                fixtures.shared[name] = value
            else:
                fixtures.per_tool.setdefault(tool, {})[name] = value
        return fixtures

    def merged(self, other: ArgumentFixtures) -> ArgumentFixtures:
        """A copy with ``other``'s values on top of these."""
        per_tool = {tool: dict(values) for tool, values in self.per_tool.items()}
        for tool, values in other.per_tool.items():
            per_tool.setdefault(tool, {}).update(values)
        return ArgumentFixtures(shared={**self.shared, **other.shared}, per_tool=per_tool)

    def for_tool(self, tool: MCPToolDef) -> dict[str, Any]:
        """The values that apply to ``tool``.

        Shared values are used only for parameters the tool declares; per-tool
        values always apply. Scalars given for a parameter declared as a string
        are passed as strings.
        """
        properties = _schema_properties(tool)
        values = {name: value for name, value in self.shared.items() if name in properties}
        values.update(self.per_tool.get(tool.name, {}))
        return {name: _fit(value, properties.get(name)) for name, value in values.items()}

    def apply(self, tool: MCPToolDef, arguments: dict[str, Any]) -> dict[str, Any]:
        """``arguments`` with this tool's fixture values on top."""
        return {**arguments, **self.for_tool(tool)}


def load_fixtures(path: str | Path) -> ArgumentFixtures:
    """Read an argument fixture file (JSON or YAML; see the module docstring)."""
    return ArgumentFixtures.from_mapping(load_structured_file(path))
