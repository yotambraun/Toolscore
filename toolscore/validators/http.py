"""HTTP side-effect validator."""

from typing import Any

from toolscore.adapters.base import ToolCall


class HTTPValidator:
    """Validator for HTTP-related side effects.

    Checks if HTTP requests succeeded based on status codes or
    result information.
    """

    def __init__(self) -> None:
        """Initialize HTTP validator."""
        self.success_codes = {200, 201, 202, 203, 204, 205, 206}

    def validate(self, call: ToolCall, expected: Any) -> bool:
        """Validate HTTP side effect.

        Args:
            call: The tool call to validate.
            expected: Expected value (True for any success, or specific status code).

        Returns:
            True if validation passes, False otherwise.
        """
        # Check result for status code
        if call.result is not None:
            if isinstance(call.result, dict):
                status = call.result.get("status") or call.result.get("status_code")
                if status:
                    if expected is True:
                        return int(status) in self.success_codes
                    return int(status) == int(expected)

            # Check if result is a status code directly
            if isinstance(call.result, int):
                if expected is True:
                    return call.result in self.success_codes
                return call.result == int(expected)

        # Check metadata for HTTP status
        if "http_status" in call.metadata:
            status = call.metadata["http_status"]
            if expected is True:
                return int(status) in self.success_codes
            return int(status) == int(expected)

        # Check if there's a URL in args and assume success if no error
        # If we got here and there's no error indication, assume success
        return bool(call.args and ("url" in call.args or "endpoint" in call.args) and
                    call.result and not isinstance(call.result, Exception))
