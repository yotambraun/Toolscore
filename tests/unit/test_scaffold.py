"""Tests for the framework-detecting init wizard (``toolscore.scaffold``)."""

from __future__ import annotations

import os
import textwrap
from typing import TYPE_CHECKING

import pytest

from toolscore.scaffold import (
    SUPPORTED_FRAMEWORKS,
    detect_frameworks,
    render_ci_workflow,
    render_test_file,
    scaffold,
)

if TYPE_CHECKING:
    from pathlib import Path

pytest_plugins = ["pytester"]


# ---------------------------------------------------------------------------
# detect_frameworks
# ---------------------------------------------------------------------------

_DIST_FOR = {
    "langgraph": "langgraph",
    "pydantic_ai": "pydantic-ai",
    "openai_agents": "openai-agents",
    "crewai": "crewai",
    "claude_agent_sdk": "claude-agent-sdk",
    "openai": "openai",
    "anthropic": "anthropic",
}


@pytest.mark.parametrize("framework,dist", list(_DIST_FOR.items()))
def test_detect_from_pyproject_dependencies(tmp_path: Path, framework: str, dist: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""
            [project]
            name = "demo"
            version = "0.1.0"
            dependencies = ["{dist}>=1.0", "rich"]
            """
        )
    )
    assert detect_frameworks(tmp_path) == [framework]


@pytest.mark.parametrize("framework,dist", list(_DIST_FOR.items()))
def test_detect_from_pyproject_optional_dependencies(
    tmp_path: Path, framework: str, dist: str
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""
            [project]
            name = "demo"
            version = "0.1.0"
            dependencies = []

            [project.optional-dependencies]
            agents = ["{dist}"]
            """
        )
    )
    assert detect_frameworks(tmp_path) == [framework]


@pytest.mark.parametrize("framework,dist", list(_DIST_FOR.items()))
def test_detect_from_requirements(tmp_path: Path, framework: str, dist: str) -> None:
    (tmp_path / "requirements.txt").write_text(f"# deps\n{dist}==2.0  # pinned\nrich\n")
    assert detect_frameworks(tmp_path) == [framework]


def test_detect_import_scan_fallback(tmp_path: Path) -> None:
    # No dependency declarations at all — must fall back to scanning imports.
    (tmp_path / "app.py").write_text("import langgraph\nfrom rich import print\n")
    assert detect_frameworks(tmp_path) == ["langgraph"]


def test_detect_import_scan_skips_venv(tmp_path: Path) -> None:
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "vendored.py").write_text("import crewai\n")
    (tmp_path / "main.py").write_text("import anthropic\n")
    assert detect_frameworks(tmp_path) == ["anthropic"]


def test_detect_ordering_langgraph_beats_openai(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "demo"
            version = "0.1.0"
            dependencies = ["openai>=1.0", "langgraph>=0.2"]
            """
        )
    )
    detected = detect_frameworks(tmp_path)
    assert detected == ["langgraph", "openai"]
    assert detected.index("langgraph") < detected.index("openai")


def test_detect_empty_returns_generic(tmp_path: Path) -> None:
    assert detect_frameworks(tmp_path) == ["generic"]


def test_detect_dependencies_take_priority_over_imports(tmp_path: Path) -> None:
    # When pyproject declares a framework, the import scan is not consulted.
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "demo"
            version = "0.1.0"
            dependencies = ["openai"]
            """
        )
    )
    (tmp_path / "app.py").write_text("import crewai\n")
    assert detect_frameworks(tmp_path) == ["openai"]


# ---------------------------------------------------------------------------
# render / scaffold
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("framework", SUPPORTED_FRAMEWORKS)
def test_render_test_file_is_valid_python(framework: str) -> None:
    source = render_test_file(framework)
    compile(source, f"<{framework}>", "exec")
    assert "TODO: import your agent" in source
    assert "toolscore_snapshot" in source
    assert "expect(" in source  # commented matcher example present


def test_render_ci_workflow_mentions_pip_and_pytest() -> None:
    yaml = render_ci_workflow()
    assert "actions/checkout" in yaml
    assert "actions/setup-python" in yaml
    assert "pip install tool-scorer" in yaml
    assert "pytest" in yaml


@pytest.mark.parametrize("framework", SUPPORTED_FRAMEWORKS)
def test_scaffold_writes_expected_files(tmp_path: Path, framework: str) -> None:
    created = scaffold(framework, tmp_path, with_ci=True)
    test_file = tmp_path / "tests" / "test_agent_tools.py"
    gitkeep = tmp_path / ".toolscore" / "snapshots" / ".gitkeep"
    ci_file = tmp_path / ".github" / "workflows" / "toolscore.yml"
    assert test_file.exists()
    assert gitkeep.exists()
    assert ci_file.exists()
    assert set(created) == {test_file, gitkeep, ci_file}
    compile(test_file.read_text(), str(test_file), "exec")


def test_scaffold_no_ci_skips_workflow(tmp_path: Path) -> None:
    scaffold("generic", tmp_path, with_ci=False)
    assert not (tmp_path / ".github" / "workflows" / "toolscore.yml").exists()
    assert (tmp_path / "tests" / "test_agent_tools.py").exists()


def test_scaffold_refuses_overwrite(tmp_path: Path) -> None:
    scaffold("generic", tmp_path, with_ci=True)
    with pytest.raises(FileExistsError):
        scaffold("generic", tmp_path, with_ci=True)


def test_scaffold_force_overwrites(tmp_path: Path) -> None:
    scaffold("generic", tmp_path, with_ci=True)
    test_file = tmp_path / "tests" / "test_agent_tools.py"
    test_file.write_text("# clobbered\n")
    scaffold("langgraph", tmp_path, with_ci=True, force=True)
    assert "LangGraph" in test_file.read_text()


# ---------------------------------------------------------------------------
# The magic moment: rendered file PASSES pytest on first run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("framework", ["generic", "openai", "langgraph"])
def test_rendered_file_passes_pytest_and_records_snapshot(
    pytester: pytest.Pytester, framework: str
) -> None:
    # Ensure we are NOT treated as CI (where snapshots may not be minted).
    for var in ("CI", "GITHUB_ACTIONS", "TOOLSCORE_RECORD", "TOOLSCORE_RECORD_UPDATE"):
        os.environ.pop(var, None)

    paths = scaffold(framework, pytester.path, with_ci=False)
    test_file = next(p for p in paths if p.name == "test_agent_tools.py")
    assert test_file.exists()

    result = pytester.runpytest_subprocess("-p", "toolscore", str(test_file))
    result.assert_outcomes(passed=1)

    snap_dir = pytester.path / ".toolscore" / "snapshots"
    assert snap_dir.exists()
    snapshots = list(snap_dir.glob("*.json"))
    assert snapshots, "first run must record a snapshot file"
