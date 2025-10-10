"""Filesystem side-effect validator."""

from pathlib import Path
from typing import Any

from toolscore.adapters.base import ToolCall


class FileSystemValidator:
    """Validator for filesystem-related side effects.

    Checks if files or directories exist or have expected properties.
    """

    def __init__(self, base_path: str | None = None) -> None:
        """Initialize filesystem validator.

        Args:
            base_path: Base directory for resolving relative paths.
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()

    def validate(self, call: ToolCall, expected: Any) -> bool:
        """Validate filesystem side effect.

        Args:
            call: The tool call to validate.
            expected: Expected value (filename/path that should exist).

        Returns:
            True if validation passes, False otherwise.
        """
        # Get the file path to check
        file_path = self._get_file_path(call, expected)

        if not file_path:
            return False

        # Check if file exists
        path = self.base_path / file_path if not Path(file_path).is_absolute() else Path(file_path)

        return path.exists()

    def _get_file_path(self, call: ToolCall, expected: Any) -> str | None:
        """Extract file path from call or expected value.

        Args:
            call: The tool call.
            expected: Expected value.

        Returns:
            File path string or None.
        """
        # If expected is a string, it's the path to check
        if isinstance(expected, str):
            return expected

        # Try to find path in call arguments
        if call.args:
            for key in ["path", "file", "filename", "filepath", "file_path", "output"]:
                if key in call.args:
                    return str(call.args[key])

        # Check result for file path
        if isinstance(call.result, str):
            return call.result

        if isinstance(call.result, dict) and "path" in call.result:
            return str(call.result["path"])

        return None
