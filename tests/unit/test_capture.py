"""Unit tests for TraceCapture - including the lazy-directory wart fix."""

import subprocess
import sys
from pathlib import Path


class TestLazyTracesDirectory:
    """Verify that importing toolscore does NOT create a traces/ directory."""

    def test_import_does_not_create_traces_dir(self, tmp_path: Path) -> None:
        """Importing toolscore in a fresh cwd must not create traces/.

        We use a subprocess so module-level side-effects are isolated and
        importlib.reload() ordering issues are avoided entirely.
        """
        result = subprocess.run(
            [sys.executable, "-c", "import toolscore"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"import failed: {result.stderr}"
        assert not (tmp_path / "traces").exists(), (
            "import toolscore must not create a traces/ directory in the cwd"
        )

    def test_traces_dir_created_when_trace_is_saved(self, tmp_path: Path) -> None:
        """The traces/ directory is created the first time a trace is saved."""
        from toolscore.capture import TraceCapture

        capture = TraceCapture(dataset_dir=str(tmp_path / "my_traces"))
        assert not (tmp_path / "my_traces").exists()

        tools = [{"tool": "search", "args": {"q": "test"}}]
        capture.capture_tools(tools, name="lazy_test")

        assert (tmp_path / "my_traces").exists()
