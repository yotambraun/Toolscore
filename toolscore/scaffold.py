"""Framework detection and project scaffolding for ``toolscore init``.

This module powers the 60-second onboarding wizard.  It can:

* :func:`detect_frameworks` — inspect a project's dependency declarations and
  source imports to guess which agent framework(s) are in use.
* :func:`scaffold` — render a working pytest suite (plus an optional GitHub
  Actions workflow) tailored to a detected framework.

Templates live in ``toolscore/templates/init`` and are packaged inside the
wheel so the wizard works from a plain ``pip install`` (the old ``init`` copied
from a repo-relative ``examples/`` path that does not ship in wheels).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

if sys.version_info >= (3, 11):
    import tomllib

    _toml_loads = tomllib.loads
    _TOMLError: type[Exception] = tomllib.TOMLDecodeError
else:  # pragma: no cover - exercised only on Python 3.10
    # ``tomllib`` is stdlib from 3.11.  On 3.10, prefer ``tomli`` if installed;
    # otherwise dependency parsing is skipped and detection falls back to the
    # import scan (so the wizard still works, just slightly less precisely).
    try:
        import tomli as _tomli  # type: ignore[import-not-found]

        _toml_loads = _tomli.loads
        _TOMLError = _tomli.TOMLDecodeError
    except ModuleNotFoundError:

        def _toml_loads(_s: str) -> dict[str, object]:
            raise _TOMLError("no TOML parser available")

        _TOMLError = ValueError

# Ordered by specificity: framework SDKs before bare provider SDKs, and a
# "generic" last-resort that depends on nothing in particular.
SUPPORTED_FRAMEWORKS: list[str] = [
    "langgraph",
    "pydantic_ai",
    "openai_agents",
    "crewai",
    "claude_agent_sdk",
    "openai",
    "anthropic",
    "generic",
]

# Maps a normalised distribution name (lowercase, hyphens) to the framework key.
_DIST_TO_FRAMEWORK: dict[str, str] = {
    "langgraph": "langgraph",
    "pydantic-ai": "pydantic_ai",
    "pydantic-ai-slim": "pydantic_ai",
    "openai-agents": "openai_agents",
    "crewai": "crewai",
    "claude-agent-sdk": "claude_agent_sdk",
    "openai": "openai",
    "anthropic": "anthropic",
}

# Maps a top-level import module to the framework key (for the source-scan
# fallback).  ``openai-agents`` is imported as ``agents``.
_IMPORT_TO_FRAMEWORK: dict[str, str] = {
    "langgraph": "langgraph",
    "pydantic_ai": "pydantic_ai",
    "agents": "openai_agents",
    "crewai": "crewai",
    "claude_agent_sdk": "claude_agent_sdk",
    "openai": "openai",
    "anthropic": "anthropic",
}

_TEMPLATES_ROOT = Path(__file__).parent / "templates"
_INIT_TEMPLATES = _TEMPLATES_ROOT / "init"

_SKIP_DIRS = {".venv", "venv", "node_modules", ".git", "__pycache__", ".tox", "build", "dist"}
_MAX_SCAN_FILES = 200


# ---------------------------------------------------------------------------
# Per-framework template context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FrameworkProfile:
    """Static, framework-specific data used to render the test template."""

    key: str
    label: str
    # A short, idiomatic snippet (commented out in the rendered file) showing
    # how to import and call the user's real agent.
    import_example: list[str]
    # A Python expression that evaluates to a fake response in the framework's
    # native format.  ``toolscore_snapshot`` runs it through ``auto_extract``.
    fake_response: str
    # The expected tool name + one arg, for the commented ``expect()`` example.
    example_tool: str = "search"
    example_arg: str = "query"
    extras: list[str] = field(default_factory=list)


_PROFILES: dict[str, FrameworkProfile] = {
    "langgraph": FrameworkProfile(
        key="langgraph",
        label="LangGraph",
        import_example=[
            "from langgraph.prebuilt import create_react_agent",
            "",
            "agent = create_react_agent(model, tools)",
            'result = agent.invoke({"messages": [("user", prompt)]})',
        ],
        fake_response=(
            "{\n"
            '        "messages": [\n'
            "            {\n"
            '                "tool_calls": [\n'
            "                    {\n"
            '                        "name": "search",\n'
            '                        "args": {"query": "toolscore"},\n'
            '                        "id": "call_1",\n'
            "                    }\n"
            "                ]\n"
            "            }\n"
            "        ]\n"
            "    }"
        ),
    ),
    "pydantic_ai": FrameworkProfile(
        key="pydantic_ai",
        label="Pydantic AI",
        import_example=[
            "from pydantic_ai import Agent",
            "",
            "agent = Agent('openai:gpt-4o', tools=[...])",
            "result = agent.run_sync(prompt)",
        ],
        fake_response=(
            "[\n"
            "        {\n"
            '            "parts": [\n'
            "                {\n"
            '                    "part_kind": "tool-call",\n'
            '                    "tool_name": "search",\n'
            '                    "args": {"query": "toolscore"},\n'
            "                }\n"
            "            ]\n"
            "        }\n"
            "    ]"
        ),
    ),
    "openai_agents": FrameworkProfile(
        key="openai_agents",
        label="OpenAI Agents SDK",
        import_example=[
            "from agents import Agent, Runner",
            "",
            "agent = Agent(name='Assistant', tools=[...])",
            "result = Runner.run_sync(agent, prompt)",
        ],
        fake_response=(
            "[\n"
            "        {\n"
            '            "type": "tool_call_item",\n'
            '            "raw_item": {\n'
            '                "name": "search",\n'
            '                "arguments": "{\\"query\\": \\"toolscore\\"}",\n'
            "            },\n"
            "        }\n"
            "    ]"
        ),
    ),
    "crewai": FrameworkProfile(
        key="crewai",
        label="CrewAI",
        import_example=[
            "from crewai import Agent, Crew, Task",
            "",
            "crew = Crew(agents=[...], tasks=[...])",
            "result = crew.kickoff(inputs={'prompt': prompt})",
        ],
        fake_response=(
            "[\n"
            "        {\n"
            '            "tool_name": "search",\n'
            '            "tool_args": {"query": "toolscore"},\n'
            "        }\n"
            "    ]"
        ),
    ),
    "claude_agent_sdk": FrameworkProfile(
        key="claude_agent_sdk",
        label="Claude Agent SDK",
        import_example=[
            "from claude_agent_sdk import query",
            "",
            "messages = list(query(prompt=prompt, options=options))",
        ],
        fake_response=(
            "[\n"
            "        {\n"
            '            "content": [\n'
            "                {\n"
            '                    "type": "tool_use",\n'
            '                    "name": "search",\n'
            '                    "input": {"query": "toolscore"},\n'
            "                }\n"
            "            ]\n"
            "        }\n"
            "    ]"
        ),
    ),
    "openai": FrameworkProfile(
        key="openai",
        label="OpenAI (raw SDK)",
        import_example=[
            "from openai import OpenAI",
            "",
            "client = OpenAI()",
            "response = client.chat.completions.create(",
            "    model='gpt-4o', messages=[{'role': 'user', 'content': prompt}], tools=[...]",
            ")",
        ],
        fake_response=(
            "{\n"
            '        "choices": [\n'
            "            {\n"
            '                "message": {\n'
            '                    "tool_calls": [\n'
            "                        {\n"
            '                            "function": {\n'
            '                                "name": "search",\n'
            '                                "arguments": "{\\"query\\": \\"toolscore\\"}",\n'
            "                            }\n"
            "                        }\n"
            "                    ]\n"
            "                }\n"
            "            }\n"
            "        ]\n"
            "    }"
        ),
    ),
    "anthropic": FrameworkProfile(
        key="anthropic",
        label="Anthropic (raw SDK)",
        import_example=[
            "import anthropic",
            "",
            "client = anthropic.Anthropic()",
            "response = client.messages.create(",
            "    model='claude-sonnet-4-5', max_tokens=1024,",
            "    messages=[{'role': 'user', 'content': prompt}], tools=[...]",
            ")",
        ],
        fake_response=(
            "{\n"
            '        "content": [\n'
            "            {\n"
            '                "type": "tool_use",\n'
            '                "name": "search",\n'
            '                "input": {"query": "toolscore"},\n'
            "            }\n"
            "        ]\n"
            "    }"
        ),
    ),
    "generic": FrameworkProfile(
        key="generic",
        label="Generic / any framework",
        import_example=[
            "from my_app.agent import run_agent",
            "",
            "result = run_agent(prompt)",
        ],
        fake_response=('[\n        {"tool": "search", "args": {"query": "toolscore"}},\n    ]'),
    ),
}


def _profile(framework: str) -> FrameworkProfile:
    """Return the :class:`FrameworkProfile` for *framework* (or ``generic``)."""
    return _PROFILES.get(framework, _PROFILES["generic"])


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _normalise_dist(raw: str) -> str:
    """Extract a normalised distribution name from a requirement string."""
    # Strip extras, version specifiers, environment markers, and comments.
    spec = raw.split("#", 1)[0].strip()
    if not spec:
        return ""
    # Drop environment markers and version constraints.
    for sep in (";", "[", "@"):
        spec = spec.split(sep, 1)[0]
    for op in ("===", "==", ">=", "<=", "~=", "!=", ">", "<"):
        spec = spec.split(op, 1)[0]
    return spec.strip().lower().replace("_", "-")


def _frameworks_from_requirements(text: str) -> set[str]:
    """Collect framework keys from requirements-file style lines."""
    found: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        dist = _normalise_dist(line)
        if dist in _DIST_TO_FRAMEWORK:
            found.add(_DIST_TO_FRAMEWORK[dist])
    return found


def _frameworks_from_pyproject(path: Path) -> set[str]:
    """Collect framework keys from a pyproject.toml's declared dependencies."""
    found: set[str] = set()
    try:
        data = _toml_loads(path.read_text(encoding="utf-8"))
    except (OSError, _TOMLError):
        return found

    project = data.get("project", {})
    deps: list[str] = list(project.get("dependencies", []) or [])
    optional = project.get("optional-dependencies", {}) or {}
    for group in optional.values():
        deps.extend(group or [])

    # Also support PEP 735 dependency-groups and Poetry-style tables.
    for group in (data.get("dependency-groups", {}) or {}).values():
        deps.extend(item for item in (group or []) if isinstance(item, str))

    poetry = data.get("tool", {}).get("poetry", {})
    for name in poetry.get("dependencies", {}) or {}:
        norm = name.lower().replace("_", "-")
        if norm in _DIST_TO_FRAMEWORK:
            found.add(_DIST_TO_FRAMEWORK[norm])

    for dep in deps:
        if not isinstance(dep, str):
            continue
        dist = _normalise_dist(dep)
        if dist in _DIST_TO_FRAMEWORK:
            found.add(_DIST_TO_FRAMEWORK[dist])
    return found


def _frameworks_from_imports(root: Path) -> set[str]:
    """Scan up to ``_MAX_SCAN_FILES`` source files for framework imports."""
    found: set[str] = set()
    scanned = 0
    for py in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in py.parts):
            continue
        if scanned >= _MAX_SCAN_FILES:
            break
        scanned += 1
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            # Take the first dotted module token after import/from.
            parts = stripped.split()
            if len(parts) < 2:
                continue
            module = parts[1].split(".", 1)[0]
            if module in _IMPORT_TO_FRAMEWORK:
                found.add(_IMPORT_TO_FRAMEWORK[module])
    return found


def detect_frameworks(root: Path) -> list[str]:
    """Detect agent frameworks used in the project rooted at *root*.

    Detection strategy, in order:

    1. Parse ``[project.dependencies]`` and ``[project.optional-dependencies]``
       from ``root/pyproject.toml`` plus any ``requirements*.txt`` files.
    2. If nothing is found, fall back to scanning up to 200 ``*.py`` files for
       matching ``import`` statements (skipping virtualenvs, ``.git`` etc.).

    Args:
        root: Project root directory to inspect.

    Returns:
        A list of detected framework keys ordered by specificity (framework
        SDKs before bare provider SDKs).  Always non-empty: falls back to
        ``["generic"]`` when nothing matches.
    """
    found: set[str] = set()

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        found |= _frameworks_from_pyproject(pyproject)

    for req in sorted(root.glob("requirements*.txt")):
        try:
            found |= _frameworks_from_requirements(req.read_text(encoding="utf-8"))
        except OSError:
            continue

    # Fallback: scan imports only when dependency declarations told us nothing.
    if not found:
        found |= _frameworks_from_imports(root)

    if not found:
        return ["generic"]

    # Order by the canonical specificity ordering.
    return [fw for fw in SUPPORTED_FRAMEWORKS if fw in found]


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


def _environment() -> Environment:
    """Return a Jinja2 environment rooted at the init templates directory."""
    return Environment(
        loader=FileSystemLoader(str(_INIT_TEMPLATES)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )


def render_test_file(framework: str) -> str:
    """Render the test suite source for *framework* (no files written).

    Args:
        framework: One of :data:`SUPPORTED_FRAMEWORKS`.

    Returns:
        The rendered Python source as a string.
    """
    if framework not in SUPPORTED_FRAMEWORKS:
        framework = "generic"
    profile = _profile(framework)
    env = _environment()
    template = env.get_template("test_agent_tools.py.j2")
    return template.render(profile=profile)


def render_ci_workflow() -> str:
    """Render the GitHub Actions workflow YAML (no files written)."""
    env = _environment()
    template = env.get_template("toolscore-ci.yml.j2")
    return template.render()


def scaffold(
    framework: str,
    output_dir: Path,
    with_ci: bool = True,
    force: bool = False,
) -> list[Path]:
    """Scaffold a working Toolscore test suite into *output_dir*.

    Writes:

    * ``tests/test_agent_tools.py`` — a rendered, immediately-passing suite.
    * ``.toolscore/snapshots/.gitkeep`` — so the snapshot dir is committed.
    * ``.github/workflows/toolscore.yml`` — when *with_ci* is true.

    Args:
        framework: One of :data:`SUPPORTED_FRAMEWORKS` (falls back to generic).
        output_dir: Target project root.
        with_ci: Whether to also write the CI workflow.
        force: Overwrite existing files instead of refusing.

    Returns:
        The list of created (or overwritten) file paths.

    Raises:
        FileExistsError: If a target file already exists and *force* is False.
    """
    if framework not in SUPPORTED_FRAMEWORKS:
        framework = "generic"

    output_dir = Path(output_dir)
    created: list[Path] = []

    test_file = output_dir / "tests" / "test_agent_tools.py"
    gitkeep = output_dir / ".toolscore" / "snapshots" / ".gitkeep"
    ci_file = output_dir / ".github" / "workflows" / "toolscore.yml"

    targets: list[tuple[Path, str]] = [
        (test_file, render_test_file(framework)),
        (gitkeep, ""),
    ]
    if with_ci:
        targets.append((ci_file, render_ci_workflow()))

    # Refuse up-front if any non-empty content target already exists.
    if not force:
        for path, content in targets:
            if content and path.exists():
                raise FileExistsError(str(path))

    for path, content in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force and not content:
            # Never clobber an existing .gitkeep; just keep it.
            continue
        path.write_text(content, encoding="utf-8")
        created.append(path)

    return created
