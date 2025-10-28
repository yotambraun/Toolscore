"""Database side-effect validator."""

from typing import Any

from toolscore.adapters.base import ToolCall


class SQLValidator:
    """Validator for SQL/database-related side effects.

    Checks if database queries returned expected number of rows or results.
    Can also validate specific data values in results.
    """

    def __init__(
        self,
        where: dict[str, Any] | None = None,
        contains_row: dict[str, Any] | None = None,
    ) -> None:
        """Initialize SQL validator.

        Args:
            where: Filter conditions that results must match (e.g., {"status": "active"}).
            contains_row: Specific row that must exist in results.
        """
        self.where = where
        self.contains_row = contains_row

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

        # Validate where conditions if specified
        if self.where and not self._check_where_conditions(call):
            return False

        # Validate contains_row if specified
        if self.contains_row and not self._check_contains_row(call):
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

    def _check_where_conditions(self, call: ToolCall) -> bool:
        """Check if result rows match WHERE conditions.

        Args:
            call: The tool call.

        Returns:
            True if all rows match the WHERE conditions, False otherwise.
        """
        if not self.where:
            return True

        rows = self._get_rows(call)
        if not rows:
            return False

        # Check if all rows match the where conditions
        for row in rows:
            if not isinstance(row, dict):
                continue

            for field, expected_value in self.where.items():
                if field not in row or row[field] != expected_value:
                    return False

        return True

    def _check_contains_row(self, call: ToolCall) -> bool:
        """Check if results contain a specific row.

        Args:
            call: The tool call.

        Returns:
            True if the specific row exists in results, False otherwise.
        """
        if not self.contains_row:
            return True

        rows = self._get_rows(call)
        if not rows:
            return False

        # Check if any row matches the expected row
        for row in rows:
            if not isinstance(row, dict):
                continue

            # Check if all fields in contains_row match
            matches = True
            for field, expected_value in self.contains_row.items():
                if field not in row or row[field] != expected_value:
                    matches = False
                    break

            if matches:
                return True

        return False

    def _get_rows(self, call: ToolCall) -> list[dict[str, Any]]:
        """Extract rows from call result.

        Args:
            call: The tool call.

        Returns:
            List of row dicts, or empty list if not available.
        """
        if call.result is None:
            return []

        # If result is already a list of dicts
        if isinstance(call.result, list):
            return [r for r in call.result if isinstance(r, dict)]

        # If result is a dict with rows key
        if isinstance(call.result, dict) and "rows" in call.result:
            rows = call.result["rows"]
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]

        return []
