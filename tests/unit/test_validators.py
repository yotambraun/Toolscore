"""Unit tests for side-effect validators."""


from toolscore.adapters.base import ToolCall
from toolscore.validators.database import SQLValidator
from toolscore.validators.filesystem import FileSystemValidator
from toolscore.validators.http import HTTPValidator


class TestHTTPValidator:
    """Tests for HTTP validator."""

    def test_validate_status_in_result_dict(self):
        """Test validation with status in result dict."""
        validator = HTTPValidator()
        call = ToolCall(
            tool="make_request",
            args={"url": "http://example.com"},
            result={"status": 200, "body": "OK"},
        )

        assert validator.validate(call, expected=True)
        assert validator.validate(call, expected=200)

    def test_validate_status_code_in_result_dict(self):
        """Test validation with status_code in result dict."""
        validator = HTTPValidator()
        call = ToolCall(
            tool="make_request",
            args={"url": "http://example.com"},
            result={"status_code": 201, "body": "Created"},
        )

        assert validator.validate(call, expected=True)
        assert validator.validate(call, expected=201)

    def test_validate_status_as_int_result(self):
        """Test validation with status code as direct result."""
        validator = HTTPValidator()
        call = ToolCall(
            tool="make_request",
            args={"url": "http://example.com"},
            result=200,
        )

        assert validator.validate(call, expected=True)
        assert validator.validate(call, expected=200)

    def test_validate_status_in_metadata(self):
        """Test validation with status in metadata."""
        validator = HTTPValidator()
        call = ToolCall(
            tool="make_request",
            args={"url": "http://example.com"},
            metadata={"http_status": 200},
        )

        assert validator.validate(call, expected=True)
        assert validator.validate(call, expected=200)

    def test_validate_success_codes(self):
        """Test validation accepts all 2xx success codes."""
        validator = HTTPValidator()

        for code in [200, 201, 202, 203, 204, 205, 206]:
            call = ToolCall(
                tool="make_request",
                result={"status": code},
            )
            assert validator.validate(call, expected=True)

    def test_validate_fail_on_error_status(self):
        """Test validation fails on error status codes."""
        validator = HTTPValidator()
        call = ToolCall(
            tool="make_request",
            result={"status": 404},
        )

        assert not validator.validate(call, expected=True)

    def test_validate_specific_status_match(self):
        """Test validation for specific status code match."""
        validator = HTTPValidator()
        call = ToolCall(
            tool="make_request",
            result={"status": 200},
        )

        assert validator.validate(call, expected=200)
        assert not validator.validate(call, expected=201)

    def test_validate_with_url_in_args(self):
        """Test validation with URL in args fallback."""
        validator = HTTPValidator()
        call = ToolCall(
            tool="make_request",
            args={"url": "http://example.com"},
            result="success",
        )

        assert validator.validate(call, expected=True)

    def test_validate_with_endpoint_in_args(self):
        """Test validation with endpoint in args fallback."""
        validator = HTTPValidator()
        call = ToolCall(
            tool="make_request",
            args={"endpoint": "/api/users"},
            result="success",
        )

        assert validator.validate(call, expected=True)

    def test_validate_fail_on_exception_result(self):
        """Test validation fails on exception result."""
        validator = HTTPValidator()
        call = ToolCall(
            tool="make_request",
            args={"url": "http://example.com"},
            result=Exception("Connection failed"),
        )

        assert not validator.validate(call, expected=True)

    def test_validate_no_result_no_url(self):
        """Test validation fails with no result and no URL."""
        validator = HTTPValidator()
        call = ToolCall(
            tool="make_request",
            args={"method": "GET"},
        )

        assert not validator.validate(call, expected=True)


class TestFileSystemValidator:
    """Tests for filesystem validator."""

    def test_validate_file_exists(self, tmp_path):
        """Test validation when file exists."""
        validator = FileSystemValidator()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call = ToolCall(tool="create_file", args={"path": str(test_file)})

        assert validator.validate(call, expected=str(test_file))

    def test_validate_file_not_exists(self, tmp_path):
        """Test validation when file doesn't exist."""
        validator = FileSystemValidator()
        test_file = tmp_path / "nonexistent.txt"

        call = ToolCall(tool="create_file", args={"path": str(test_file)})

        assert not validator.validate(call, expected=str(test_file))

    def test_validate_directory_exists(self, tmp_path):
        """Test validation when directory exists."""
        validator = FileSystemValidator()
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        call = ToolCall(tool="create_directory", args={"path": str(test_dir)})

        assert validator.validate(call, expected=str(test_dir))

    def test_validate_with_filename_in_args(self, tmp_path):
        """Test validation with 'filename' key in args."""
        validator = FileSystemValidator()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call = ToolCall(tool="create_file", args={"filename": str(test_file)})

        assert validator.validate(call, expected=str(test_file))

    def test_validate_with_file_in_args(self, tmp_path):
        """Test validation with 'file' key in args."""
        validator = FileSystemValidator()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call = ToolCall(tool="create_file", args={"file": str(test_file)})

        assert validator.validate(call, expected=str(test_file))

    def test_validate_with_result_path(self, tmp_path):
        """Test validation using path from result."""
        validator = FileSystemValidator()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call = ToolCall(
            tool="create_file",
            args={},
            result={"path": str(test_file)},
        )

        assert validator.validate(call, expected=str(test_file))

    def test_validate_with_result_filename(self, tmp_path):
        """Test validation using filename from result."""
        validator = FileSystemValidator()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call = ToolCall(
            tool="create_file",
            args={},
            result={"filename": str(test_file)},
        )

        assert validator.validate(call, expected=str(test_file))

    def test_validate_expected_true_checks_args(self, tmp_path):
        """Test validation with expected=True checks args."""
        validator = FileSystemValidator()
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call = ToolCall(tool="create_file", args={"path": str(test_file)})

        assert validator.validate(call, expected=True)

    def test_validate_expected_true_file_not_found(self, tmp_path):
        """Test validation with expected=True when file not found."""
        validator = FileSystemValidator()
        test_file = tmp_path / "nonexistent.txt"

        call = ToolCall(tool="create_file", args={"path": str(test_file)})

        assert not validator.validate(call, expected=True)

    def test_validate_relative_path(self, tmp_path, monkeypatch):
        """Test validation with relative path."""
        monkeypatch.chdir(tmp_path)
        validator = FileSystemValidator()

        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        call = ToolCall(tool="create_file", args={"path": "test.txt"})

        assert validator.validate(call, expected="test.txt")


class TestSQLValidator:
    """Tests for SQL validator."""

    def test_validate_rows_affected_in_result(self):
        """Test validation with rows_affected in result."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            args={"query": "INSERT INTO users VALUES (1, 'John')"},
            result={"rows_affected": 1},
        )

        assert validator.validate(call, expected=1)

    def test_validate_rowcount_in_result(self):
        """Test validation with rowcount in result."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            args={"query": "UPDATE users SET name='Jane' WHERE id=1"},
            result={"rowcount": 1},
        )

        assert validator.validate(call, expected=1)

    def test_validate_row_count_in_result(self):
        """Test validation with row_count in result."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            args={"query": "DELETE FROM users WHERE id=1"},
            result={"row_count": 1},
        )

        assert validator.validate(call, expected=1)

    def test_validate_count_in_result(self):
        """Test validation with count in result."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            args={"query": "SELECT * FROM users"},
            result={"count": 5},
        )

        assert validator.validate(call, expected=5)

    def test_validate_rows_list_length(self):
        """Test validation with rows list."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            args={"query": "SELECT * FROM users"},
            result={"rows": [{"id": 1}, {"id": 2}, {"id": 3}]},
        )

        assert validator.validate(call, expected=3)

    def test_validate_result_list_length(self):
        """Test validation with direct result list."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            args={"query": "SELECT * FROM users"},
            result=[{"id": 1}, {"id": 2}],
        )

        assert validator.validate(call, expected=2)

    def test_validate_expected_true_any_rows(self):
        """Test validation with expected=True for any rows."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            result={"rows_affected": 3},
        )

        assert validator.validate(call, expected=True)

    def test_validate_expected_true_no_rows(self):
        """Test validation with expected=True for no rows."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            result={"rows_affected": 0},
        )

        assert not validator.validate(call, expected=True)

    def test_validate_mismatch_row_count(self):
        """Test validation fails on mismatched row count."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            result={"rows_affected": 5},
        )

        assert not validator.validate(call, expected=3)

    def test_validate_rows_in_metadata(self):
        """Test validation with rows in metadata."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            metadata={"rows_affected": 2},
        )

        assert validator.validate(call, expected=2)

    def test_validate_no_row_info(self):
        """Test validation fails when no row info available."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            result={"status": "success"},
        )

        assert not validator.validate(call, expected=1)

    def test_validate_zero_rows_expected(self):
        """Test validation succeeds for expected zero rows."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            result={"rows_affected": 0},
        )

        assert validator.validate(call, expected=0)

    def test_validate_large_row_count(self):
        """Test validation with large row counts."""
        validator = SQLValidator()
        call = ToolCall(
            tool="execute_query",
            result={"rows_affected": 1000},
        )

        assert validator.validate(call, expected=1000)
        assert not validator.validate(call, expected=999)
