"""Database side-effect validator."""

from typing import Any

from toolscore.adapters.base import ToolCall


class SQLValidator:
    """Validator for SQL/database-related side effects.

    Checks if database queries returned expected number of rows or results.
    """

    def validate(self, call: ToolCall, expected: Any) -> bool:
        """Validate SQL side effect.

        Args:
            call: The tool call to validate.
            expected: Expected value (True for non-empty result, or specific row count).

        Returns:
            True if validation passes, False otherwise.
        """
        row_count = self._get_row_count(call)

        if row_count is None:
            return False

        # If expected is True, just check for non-empty result
        if expected is True:
            return row_count > 0

        # If expected is a number, check exact count
        if isinstance(expected, int):
            return row_count == expected

        # If expected is a dict with min/max
        if isinstance(expected, dict):
            if "min" in expected and row_count < expected["min"]:
                return False
            return not ("max" in expected and row_count > expected["max"])

        return False

    def _get_row_count(self, call: ToolCall) -> int | None:
        """Extract row count from call result.

        Args:
            call: The tool call.

        Returns:
            Row count or None if not available.
        """
        # Check result for row count
        if call.result is not None:
            if isinstance(call.result, int):
                return call.result

            if isinstance(call.result, list):
                return len(call.result)

            if isinstance(call.result, dict):
                # Check for various row count field names
                for key in ["rows_affected", "rowcount", "row_count", "count"]:
                    if key in call.result:
                        return int(call.result[key])

                # Check for rows list
                if "rows" in call.result:
                    if isinstance(call.result["rows"], list):
                        return len(call.result["rows"])
                    if isinstance(call.result["rows"], int):
                        return int(call.result["rows"])

        # Check metadata
        for key in ["rows_affected", "rowcount", "row_count"]:
            if key in call.metadata:
                return int(call.metadata[key])

        return None
