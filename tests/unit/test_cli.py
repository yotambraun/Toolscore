"""Unit tests for CLI commands."""

import json
import shlex
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from toolscore.cli import main

FIXTURE_SERVER = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mcp_server.py"


def _fake_server_arg(*extra: str) -> str:
    """Return a single shell-quoted command string launching the fake server."""
    parts = [sys.executable, str(FIXTURE_SERVER), *extra]
    return shlex.join(parts)


@pytest.fixture
def runner():
    """Create CLI runner."""
    return CliRunner()


@pytest.fixture
def temp_files(tmp_path):
    """Create temporary test files."""
    # Create gold standard file
    gold_file = tmp_path / "gold.json"
    gold_data = [
        {
            "tool": "test_tool",
            "args": {"x": 1, "y": 2},
            "description": "Test tool call",
        }
    ]
    with gold_file.open("w") as f:
        json.dump(gold_data, f)

    # Create trace file (OpenAI format)
    trace_file = tmp_path / "trace.json"
    trace_data = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "type": "function",
                    "id": "call_123",
                    "function": {
                        "name": "test_tool",
                        "arguments": '{"x": 1, "y": 2}',
                    },
                }
            ],
        }
    ]
    with trace_file.open("w") as f:
        json.dump(trace_data, f)

    return {"gold": gold_file, "trace": trace_file, "dir": tmp_path}


class TestEvalCommand:
    """Tests for eval command."""

    def test_eval_basic(self, runner, temp_files):
        """Test basic evaluation."""
        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--format",
                "openai",
            ],
        )

        assert result.exit_code == 0
        assert "Overall Score" in result.output
        assert "Selection Accuracy" in result.output

    def test_eval_with_html_output(self, runner, temp_files):
        """Test evaluation with HTML output."""
        html_file = temp_files["dir"] / "report.html"

        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--html",
                str(html_file),
            ],
        )

        assert result.exit_code == 0
        assert html_file.exists()
        assert "HTML report:" in result.output

    def test_eval_with_json_output(self, runner, temp_files):
        """Test evaluation with custom JSON output path."""
        json_file = temp_files["dir"] / "custom_report.json"

        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--output",
                str(json_file),
            ],
        )

        assert result.exit_code == 0
        assert json_file.exists()
        assert "JSON report:" in result.output

    def test_eval_verbose(self, runner, temp_files):
        """Test evaluation with verbose output."""
        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--verbose",
            ],
        )

        assert result.exit_code == 0
        assert "Loading gold standard from" in result.output
        assert "Loading trace from" in result.output

    def test_eval_no_side_effects(self, runner, temp_files):
        """Test evaluation with side effects disabled."""
        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--no-side-effects",
            ],
        )

        assert result.exit_code == 0
        # Should not have side-effect metrics in output
        assert "Side-Effect" not in result.output

    def test_eval_missing_gold_file(self, runner, temp_files):
        """Test evaluation with missing gold file."""
        result = runner.invoke(
            main,
            [
                "eval",
                "/nonexistent/gold.json",
                str(temp_files["trace"]),
            ],
        )

        assert result.exit_code == 2  # Click file validation error
        assert "does not exist" in result.output.lower() or "error" in result.output.lower()

    def test_eval_missing_trace_file(self, runner, temp_files):
        """Test evaluation with missing trace file."""
        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                "/nonexistent/trace.json",
            ],
        )

        assert result.exit_code == 2  # Click file validation error
        assert "does not exist" in result.output.lower() or "error" in result.output.lower()

    def test_eval_auto_format_detection(self, runner, temp_files):
        """Test auto format detection."""
        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(temp_files["trace"]),
                "--format",
                "auto",
            ],
        )

        assert result.exit_code == 0
        assert "Overall Score" in result.output


class TestValidateCommand:
    """Tests for validate command."""

    def test_validate_valid_trace(self, runner, temp_files):
        """Test validation of valid trace file."""
        result = runner.invoke(
            main,
            ["validate", str(temp_files["trace"]), "--format", "openai"],
        )

        assert result.exit_code == 0
        assert "Valid trace file" in result.output
        assert "Total calls:" in result.output

    def test_validate_with_details(self, runner, temp_files):
        """Test validation shows first call details."""
        result = runner.invoke(
            main,
            ["validate", str(temp_files["trace"])],
        )

        assert result.exit_code == 0
        assert "Total calls:" in result.output
        assert "First tool:" in result.output
        assert "First args:" in result.output

    def test_validate_invalid_file(self, runner, tmp_path):
        """Test validation of invalid trace file."""
        invalid_file = tmp_path / "invalid.json"
        with invalid_file.open("w") as f:
            f.write("not valid json{")

        result = runner.invoke(
            main,
            ["validate", str(invalid_file)],
        )

        assert result.exit_code == 1
        assert "Invalid trace file" in result.output

    def test_validate_missing_file(self, runner):
        """Test validation of missing file."""
        result = runner.invoke(
            main,
            ["validate", "/nonexistent/trace.json"],
        )

        assert result.exit_code == 2  # Click error for missing file


class TestMCPFormatChoice:
    """Verify that --format mcp is accepted by all relevant subcommands."""

    def test_eval_accepts_mcp_format(self, runner, temp_files, tmp_path):
        """eval command must accept --format mcp without a 'invalid choice' error."""
        # Create a minimal MCP trace file
        import json as _json

        mcp_trace = tmp_path / "mcp_trace.json"
        mcp_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "test_tool", "arguments": {"x": 1, "y": 2}},
            "id": 1,
        }
        mcp_trace.write_text(_json.dumps(mcp_data))

        result = runner.invoke(
            main,
            [
                "eval",
                str(temp_files["gold"]),
                str(mcp_trace),
                "--format",
                "mcp",
            ],
        )
        # Exit code 0 = success; exit code 2 would mean Click rejected the choice
        assert result.exit_code != 2, f"'mcp' rejected as format choice:\n{result.output}"

    def test_validate_accepts_mcp_format(self, runner, tmp_path):
        """validate command must accept --format mcp."""
        import json as _json

        mcp_trace = tmp_path / "mcp_trace.json"
        mcp_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "test_tool", "arguments": {"x": 1}},
            "id": 1,
        }
        mcp_trace.write_text(_json.dumps(mcp_data))

        result = runner.invoke(main, ["validate", str(mcp_trace), "--format", "mcp"])
        assert result.exit_code != 2, f"'mcp' rejected as format choice:\n{result.output}"

    def test_compare_accepts_mcp_format(self, runner, temp_files, tmp_path):
        """compare command must accept --format mcp without a 'invalid choice' error."""
        import json as _json

        mcp_trace = tmp_path / "mcp_trace.json"
        mcp_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "test_tool", "arguments": {"x": 1, "y": 2}},
            "id": 1,
        }
        mcp_trace.write_text(_json.dumps(mcp_data))

        result = runner.invoke(
            main,
            [
                "compare",
                str(temp_files["gold"]),
                str(mcp_trace),
                "--format",
                "mcp",
            ],
        )
        # Exit code 2 means Click rejected 'mcp' as an invalid choice value
        assert result.exit_code != 2, f"'mcp' rejected as format choice:\n{result.output}"

    def test_regression_accepts_mcp_format(self, runner, temp_files, tmp_path):
        """regression command must accept --format mcp without a 'invalid choice' error."""
        import json as _json

        # Build a minimal valid baseline file
        baseline_file = tmp_path / "baseline.json"
        baseline_data = {
            "version": "1.0.0",
            "created_at": "2026-01-01T00:00:00+00:00",
            "gold_file_hash": "",
            "metrics": {
                "invocation_accuracy": 1.0,
                "selection_accuracy": 1.0,
                "sequence_accuracy": 1.0,
                "argument_f1": 1.0,
                "redundant_rate": 0.0,
            },
            "metadata": {"gold_calls_count": 1, "trace_calls_count": 1},
        }
        baseline_file.write_text(_json.dumps(baseline_data))

        mcp_trace = tmp_path / "mcp_trace.json"
        mcp_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "test_tool", "arguments": {"x": 1, "y": 2}},
            "id": 1,
        }
        mcp_trace.write_text(_json.dumps(mcp_data))

        result = runner.invoke(
            main,
            [
                "regression",
                str(baseline_file),
                str(mcp_trace),
                "--gold-file",
                str(temp_files["gold"]),
                "--format",
                "mcp",
            ],
        )
        # Exit code 2 means Click rejected 'mcp' as an invalid choice value
        assert result.exit_code != 2, f"'mcp' rejected as format choice:\n{result.output}"


class TestMainCommand:
    """Tests for main command group."""

    def test_version_option(self, runner):
        """Test --version option."""
        result = runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "toolscore" in result.output.lower()

    def test_help_option(self, runner):
        """Test --help option."""
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "Toolscore" in result.output
        assert "eval" in result.output
        assert "validate" in result.output

    def test_eval_help(self, runner):
        """Test eval command help."""
        result = runner.invoke(main, ["eval", "--help"])

        assert result.exit_code == 0
        assert "GOLD_FILE" in result.output
        assert "TRACE_FILE" in result.output
        assert "--format" in result.output
        assert "--html" in result.output

    def test_mcp_group_in_help(self, runner):
        """The mcp sub-group should be listed in the main help."""
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "mcp" in result.output


class TestMCPCommands:
    """Tests for the `toolscore mcp` list/lint/test sub-group."""

    def test_mcp_list(self, runner):
        """list should print a table of the fake server's tools."""
        result = runner.invoke(main, ["mcp", "list", _fake_server_arg()])
        assert result.exit_code == 0, result.output
        assert "add" in result.output
        assert "flaky" in result.output
        assert "bad_schema" in result.output

    def test_mcp_lint_exits_nonzero_on_errors(self, runner):
        """lint should exit 1 because bad_schema produces error-severity issues."""
        result = runner.invoke(main, ["mcp", "lint", _fake_server_arg()])
        assert result.exit_code == 1, result.output
        assert "bad_schema" in result.output

    def test_mcp_test_default_human_output(self, runner):
        """test should print a scorecard with a grade by default."""
        result = runner.invoke(main, ["mcp", "test", _fake_server_arg(), "--cases", "2"])
        assert result.exit_code == 0, result.output
        assert "Scorecard" in result.output or "Grade" in result.output
        assert "fake-mcp" in result.output

    def test_mcp_test_no_edge_cases(self, runner):
        """--no-edge-cases is accepted and still produces a scorecard."""
        result = runner.invoke(
            main,
            ["mcp", "test", _fake_server_arg(), "--cases", "2", "--no-edge-cases"],
        )
        assert result.exit_code == 0, result.output
        assert "fake-mcp" in result.output

    def test_mcp_test_report_json_output(self, runner, tmp_path):
        """--report json --output writes a JSON file and prints a summary."""
        out = tmp_path / "scorecard.json"
        result = runner.invoke(
            main,
            [
                "mcp",
                "test",
                _fake_server_arg(),
                "--cases",
                "2",
                "--report",
                "json",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["server"]["name"] == "fake-mcp"
        assert data["grade"] in {"A", "B", "C", "D", "F"}
        # A one-line summary is still printed to the console.
        assert "Grade" in result.output or "grade" in result.output.lower()

    def test_mcp_test_report_md_output(self, runner, tmp_path):
        """--report md --output writes a Markdown file."""
        out = tmp_path / "scorecard.md"
        result = runner.invoke(
            main,
            [
                "mcp",
                "test",
                _fake_server_arg(),
                "--cases",
                "2",
                "--report",
                "md",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        text = out.read_text()
        assert "MCP Scorecard" in text
        assert "| Tool |" in text

    def test_mcp_test_fail_under_failing(self, runner):
        """--fail-under A should fail (exit 1) since the fake server is not an A."""
        result = runner.invoke(
            main,
            ["mcp", "test", _fake_server_arg(), "--cases", "2", "--fail-under", "A"],
        )
        assert result.exit_code == 1, result.output

    def test_mcp_test_fail_under_passing(self, runner):
        """--fail-under F should always pass."""
        result = runner.invoke(
            main,
            ["mcp", "test", _fake_server_arg(), "--cases", "2", "--fail-under", "F"],
        )
        assert result.exit_code == 0, result.output

    def test_mcp_test_both_config_and_positional_errors(self, runner, tmp_path):
        """Providing both a positional command and --config is an error."""
        config = tmp_path / "mcp.json"
        config.write_text(json.dumps({"mcpServers": {"x": {"command": "echo", "args": ["hi"]}}}))
        result = runner.invoke(
            main,
            ["mcp", "test", _fake_server_arg(), "--config", str(config)],
        )
        assert result.exit_code != 0
        assert "config" in result.output.lower() or "exactly one" in result.output.lower()

    def test_mcp_test_neither_config_nor_positional_errors(self, runner):
        """Providing neither a positional command nor --config is an error."""
        result = runner.invoke(main, ["mcp", "test"])
        assert result.exit_code != 0
        assert "config" in result.output.lower() or "command" in result.output.lower()

    def test_mcp_list_via_config(self, runner, tmp_path):
        """list should work through --config + --server."""
        config = tmp_path / "mcp.json"
        config.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "fake": {
                            "command": sys.executable,
                            "args": [str(FIXTURE_SERVER)],
                        }
                    }
                }
            )
        )
        result = runner.invoke(main, ["mcp", "list", "--config", str(config)])
        assert result.exit_code == 0, result.output
        assert "add" in result.output


# ---------------------------------------------------------------------------
# Helpers for snapshot CLI tests
# ---------------------------------------------------------------------------


def _make_trace_file(tmp_path: Path, name: str = "trace.json") -> Path:
    """Write a minimal custom-format trace that load_trace can parse."""
    data = [
        {"tool": "search", "args": {"query": "flights"}},
        {"tool": "book", "args": {"flight_id": "AA123"}},
    ]
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return p


def _snap_dir(tmp_path: Path) -> Path:
    return tmp_path / "snaps"


# ---------------------------------------------------------------------------
# record command
# ---------------------------------------------------------------------------


class TestRecordCommand:
    """Tests for `toolscore record`."""

    # --- subprocess mode ---

    def test_record_subprocess_propagates_exit_code_zero(self, runner, tmp_path):
        """Subprocess mode with a zero-exit command passes the code through."""
        result = runner.invoke(
            main,
            ["record", "--", sys.executable, "-c", "import sys; sys.exit(0)"],
        )
        assert result.exit_code == 0, result.output

    def test_record_subprocess_propagates_nonzero_exit_code(self, runner, tmp_path):
        """Subprocess mode with a non-zero exit command propagates that code."""
        result = runner.invoke(
            main,
            ["record", "--", sys.executable, "-c", "import sys; sys.exit(42)"],
        )
        assert result.exit_code == 42, result.output

    def test_record_subprocess_sets_toolscore_record_env(self, runner, tmp_path):
        """Subprocess receives TOOLSCORE_RECORD=1 in its environment."""
        result = runner.invoke(
            main,
            [
                "record",
                "--",
                sys.executable,
                "-c",
                "import os, sys; sys.exit(0 if os.environ.get('TOOLSCORE_RECORD')=='1' else 1)",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_record_subprocess_sets_update_env_when_flag_given(self, runner, tmp_path):
        """--update passes TOOLSCORE_RECORD_UPDATE=1 to the subprocess."""
        result = runner.invoke(
            main,
            [
                "record",
                "--update",
                "--",
                sys.executable,
                "-c",
                (
                    "import os, sys; "
                    "sys.exit(0 if os.environ.get('TOOLSCORE_RECORD_UPDATE')=='1' else 1)"
                ),
            ],
        )
        assert result.exit_code == 0, result.output

    def test_record_subprocess_prints_recording_line(self, runner, tmp_path):
        """The rich one-liner before the child run mentions the command."""
        result = runner.invoke(
            main,
            ["record", "--", sys.executable, "-c", "pass"],
        )
        assert (
            "recording snapshots via:" in result.output.lower()
            or "recording" in result.output.lower()
        ), result.output

    # --- trace mode ---

    def test_record_from_trace_creates_pending_snapshot(self, runner, tmp_path):
        """--from-trace with a new name creates an unapproved snapshot."""
        sd = _snap_dir(tmp_path)
        trace = _make_trace_file(tmp_path)
        result = runner.invoke(
            main,
            [
                "record",
                "--from-trace",
                str(trace),
                "--name",
                "booking_snap",
                "--format",
                "custom",
                "--dir",
                str(sd),
            ],
        )
        assert result.exit_code == 0, result.output
        # A snapshot file should exist in the store
        from toolscore.snapshots import SnapshotStore

        store = SnapshotStore(sd)
        snap = store.load("booking_snap")
        assert snap is not None
        assert snap.approved is False
        assert snap.source == "trace"
        assert len(snap.calls) == 2

    def test_record_from_trace_duplicate_errors_without_update(self, runner, tmp_path):
        """Recording the same name twice without --update exits non-zero."""
        sd = _snap_dir(tmp_path)
        trace = _make_trace_file(tmp_path)
        args = [
            "record",
            "--from-trace",
            str(trace),
            "--name",
            "dup_snap",
            "--format",
            "custom",
            "--dir",
            str(sd),
        ]
        result1 = runner.invoke(main, args)
        assert result1.exit_code == 0, result1.output

        result2 = runner.invoke(main, args)
        assert result2.exit_code != 0

    def test_record_from_trace_update_overwrites_and_approves(self, runner, tmp_path):
        """--update on an existing snapshot overwrites it and sets approved=True."""
        sd = _snap_dir(tmp_path)
        trace = _make_trace_file(tmp_path)
        base_args = [
            "record",
            "--from-trace",
            str(trace),
            "--name",
            "update_snap",
            "--format",
            "custom",
            "--dir",
            str(sd),
        ]
        runner.invoke(main, base_args)  # first record

        update_args = [
            "record",
            "--update",
            "--from-trace",
            str(trace),
            "--name",
            "update_snap",
            "--format",
            "custom",
            "--dir",
            str(sd),
        ]
        result = runner.invoke(main, update_args)
        assert result.exit_code == 0, result.output

        from toolscore.snapshots import SnapshotStore

        snap = SnapshotStore(sd).load("update_snap")
        assert snap is not None
        assert snap.approved is True

    def test_record_from_trace_requires_name(self, runner, tmp_path):
        """--from-trace without --name is an error."""
        trace = _make_trace_file(tmp_path)
        result = runner.invoke(
            main,
            ["record", "--from-trace", str(trace), "--dir", str(_snap_dir(tmp_path))],
        )
        assert result.exit_code != 0

    def test_record_mutually_exclusive_modes(self, runner, tmp_path):
        """Passing both --from-trace and a trailing command is an error."""
        trace = _make_trace_file(tmp_path)
        result = runner.invoke(
            main,
            [
                "record",
                "--from-trace",
                str(trace),
                "--name",
                "x",
                "--",
                sys.executable,
                "-c",
                "pass",
            ],
        )
        assert result.exit_code != 0

    def test_record_no_mode_errors(self, runner, tmp_path):
        """Providing neither --from-trace nor a command is an error."""
        result = runner.invoke(main, ["record", "--dir", str(_snap_dir(tmp_path))])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# approve command
# ---------------------------------------------------------------------------


class TestApproveCommand:
    """Tests for `toolscore approve`."""

    def _seed_snapshot(self, snap_dir: Path, name: str, approved: bool = False) -> None:
        """Write a snapshot directly into the store."""
        from toolscore.snapshots import Snapshot, SnapshotStore

        store = SnapshotStore(snap_dir)
        snap = Snapshot(
            name=name,
            calls=[{"tool": "search", "args": {"q": "test"}}],
            approved=approved,
            source="trace",
        )
        store.save(snap)

    def test_approve_by_name(self, runner, tmp_path):
        """Approving a snapshot by name sets approved=True."""
        sd = _snap_dir(tmp_path)
        self._seed_snapshot(sd, "my_snap")

        result = runner.invoke(main, ["approve", "my_snap", "--dir", str(sd)])
        assert result.exit_code == 0, result.output

        from toolscore.snapshots import SnapshotStore

        snap = SnapshotStore(sd).load("my_snap")
        assert snap is not None
        assert snap.approved is True

    def test_approve_by_name_shows_table(self, runner, tmp_path):
        """Approve output includes the snapshot name and call count."""
        sd = _snap_dir(tmp_path)
        self._seed_snapshot(sd, "table_snap")

        result = runner.invoke(main, ["approve", "table_snap", "--dir", str(sd)])
        assert result.exit_code == 0, result.output
        assert "table_snap" in result.output

    def test_approve_missing_name_exits_one(self, runner, tmp_path):
        """Approving a non-existent snapshot exits with code 1."""
        sd = _snap_dir(tmp_path)
        result = runner.invoke(main, ["approve", "ghost_snap", "--dir", str(sd)])
        assert result.exit_code == 1

    def test_approve_all_approves_pending(self, runner, tmp_path):
        """--all approves every pending snapshot."""
        sd = _snap_dir(tmp_path)
        self._seed_snapshot(sd, "pending_a")
        self._seed_snapshot(sd, "pending_b")

        result = runner.invoke(main, ["approve", "--all", "--dir", str(sd)])
        assert result.exit_code == 0, result.output

        from toolscore.snapshots import SnapshotStore

        store = SnapshotStore(sd)
        assert store.load("pending_a").approved is True  # type: ignore[union-attr]
        assert store.load("pending_b").approved is True  # type: ignore[union-attr]

    def test_approve_all_friendly_message_when_none_pending(self, runner, tmp_path):
        """--all with no pending snapshots prints a friendly message and exits 0."""
        sd = _snap_dir(tmp_path)
        self._seed_snapshot(sd, "already_done", approved=True)

        result = runner.invoke(main, ["approve", "--all", "--dir", str(sd)])
        assert result.exit_code == 0, result.output
        # Should not error; should say nothing to approve
        assert "nothing" in result.output.lower() or "no pending" in result.output.lower()

    def test_approve_no_args_errors(self, runner, tmp_path):
        """Providing neither names nor --all is an error."""
        result = runner.invoke(main, ["approve", "--dir", str(_snap_dir(tmp_path))])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# snapshots sub-group
# ---------------------------------------------------------------------------


class TestSnapshotsSubgroup:
    """Tests for `toolscore snapshots list/show/rm`."""

    def _seed(self, snap_dir: Path, name: str, approved: bool = False, n_calls: int = 1) -> None:
        from toolscore.snapshots import Snapshot, SnapshotStore

        store = SnapshotStore(snap_dir)
        snap = Snapshot(
            name=name,
            calls=[{"tool": f"tool_{i}", "args": {"i": i}} for i in range(n_calls)],
            approved=approved,
            source="trace",
        )
        store.save(snap)

    # --- list ---

    def test_snapshots_list_shows_all(self, runner, tmp_path):
        """snapshots list shows both approved and pending."""
        sd = _snap_dir(tmp_path)
        self._seed(sd, "snap_a", approved=True)
        self._seed(sd, "snap_b", approved=False)

        result = runner.invoke(main, ["snapshots", "list", "--dir", str(sd)])
        assert result.exit_code == 0, result.output
        assert "snap_a" in result.output
        assert "snap_b" in result.output

    def test_snapshots_list_pending_filter(self, runner, tmp_path):
        """snapshots list --pending shows only unapproved snapshots."""
        sd = _snap_dir(tmp_path)
        self._seed(sd, "approved_snap", approved=True)
        self._seed(sd, "pending_snap", approved=False)

        result = runner.invoke(main, ["snapshots", "list", "--pending", "--dir", str(sd)])
        assert result.exit_code == 0, result.output
        assert "pending_snap" in result.output
        assert "approved_snap" not in result.output

    def test_snapshots_list_empty(self, runner, tmp_path):
        """snapshots list on an empty store prints a friendly message."""
        sd = _snap_dir(tmp_path)
        result = runner.invoke(main, ["snapshots", "list", "--dir", str(sd)])
        assert result.exit_code == 0, result.output
        assert "no snapshots" in result.output.lower()

    # --- show ---

    def test_snapshots_show_contains_tool_names(self, runner, tmp_path):
        """snapshots show includes the tool name(s) from the recorded calls."""
        sd = _snap_dir(tmp_path)
        self._seed(sd, "show_snap", n_calls=2)

        result = runner.invoke(main, ["snapshots", "show", "show_snap", "--dir", str(sd)])
        assert result.exit_code == 0, result.output
        assert "tool_0" in result.output
        assert "tool_1" in result.output

    def test_snapshots_show_contains_metadata(self, runner, tmp_path):
        """snapshots show includes the snapshot name and status."""
        sd = _snap_dir(tmp_path)
        self._seed(sd, "meta_snap", approved=True)

        result = runner.invoke(main, ["snapshots", "show", "meta_snap", "--dir", str(sd)])
        assert result.exit_code == 0, result.output
        assert "meta_snap" in result.output
        assert "approved" in result.output.lower()

    def test_snapshots_show_missing_exits_nonzero(self, runner, tmp_path):
        """snapshots show on a non-existent snapshot exits with a non-zero code."""
        sd = _snap_dir(tmp_path)
        result = runner.invoke(main, ["snapshots", "show", "ghost", "--dir", str(sd)])
        assert result.exit_code != 0

    # --- rm ---

    def test_snapshots_rm_with_yes_deletes(self, runner, tmp_path):
        """snapshots rm --yes deletes the snapshot without prompting."""
        sd = _snap_dir(tmp_path)
        self._seed(sd, "delete_me")

        result = runner.invoke(main, ["snapshots", "rm", "delete_me", "--yes", "--dir", str(sd)])
        assert result.exit_code == 0, result.output

        from toolscore.snapshots import SnapshotStore

        assert SnapshotStore(sd).load("delete_me") is None

    def test_snapshots_rm_with_n_input_keeps_snapshot(self, runner, tmp_path):
        """Answering 'n' at the confirmation prompt keeps the snapshot."""
        sd = _snap_dir(tmp_path)
        self._seed(sd, "keep_me")

        result = runner.invoke(main, ["snapshots", "rm", "keep_me", "--dir", str(sd)], input="n\n")
        assert result.exit_code == 0, result.output

        from toolscore.snapshots import SnapshotStore

        assert SnapshotStore(sd).load("keep_me") is not None

    def test_snapshots_rm_missing_exits_nonzero(self, runner, tmp_path):
        """Trying to delete a non-existent snapshot exits with a non-zero code."""
        sd = _snap_dir(tmp_path)
        result = runner.invoke(main, ["snapshots", "rm", "ghost_snap", "--yes", "--dir", str(sd)])
        assert result.exit_code != 0
