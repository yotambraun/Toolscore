"""Pytest plugin for Toolscore integration.

This plugin allows you to use Toolscore evaluations directly in your pytest test suite.

Example:
    def test_agent_performance(toolscore_eval):
        result = toolscore_eval("gold_calls.json", "trace.json")
        assert result.metrics['invocation_accuracy'] >= 0.9
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from toolscore.core import EvaluationResult, evaluate, evaluate_trace


def pytest_addoption(parser: Any) -> None:
    """Add Toolscore-specific command line options to pytest.

    Args:
        parser: Pytest parser object
    """
    group = parser.getgroup("toolscore", "LLM tool usage evaluation")

    group.addoption(
        "--toolscore-gold-dir",
        action="store",
        default="tests/gold_standards",
        help="Directory containing gold standard files (default: tests/gold_standards)",
    )

    group.addoption(
        "--toolscore-trace-dir",
        action="store",
        default="tests/traces",
        help="Directory containing trace files (default: tests/traces)",
    )

    group.addoption(
        "--toolscore-update",
        action="store_true",
        default=False,
        help="Re-record snapshots used by the toolscore_snapshot fixture "
        "(overwrite and re-approve). Also honored via TOOLSCORE_RECORD_UPDATE=1.",
    )

    group.addoption(
        "--toolscore-snapshot-dir",
        action="store",
        default=".toolscore/snapshots",
        help="Root directory for snapshot files, relative to the pytest rootdir "
        "(default: .toolscore/snapshots).",
    )

    group.addoption(
        "--toolscore-allow-pending",
        action="store_true",
        default=False,
        help="Treat missing/pending snapshots as non-fatal even in CI "
        "(warn instead of failing). Useful for staged rollouts.",
    )


def pytest_configure(config: Any) -> None:
    """Register Toolscore markers.

    Args:
        config: Pytest config object
    """
    config.addinivalue_line(
        "markers",
        "toolscore: mark test as a Toolscore evaluation test",
    )


@pytest.fixture
def toolscore_gold_dir(request: Any) -> Path:
    """Get the gold standards directory from config.

    Args:
        request: Pytest request object

    Returns:
        Path to gold standards directory
    """
    return Path(request.config.getoption("--toolscore-gold-dir"))


@pytest.fixture
def toolscore_trace_dir(request: Any) -> Path:
    """Get the traces directory from config.

    Args:
        request: Pytest request object

    Returns:
        Path to traces directory
    """
    return Path(request.config.getoption("--toolscore-trace-dir"))


@pytest.fixture
def toolscore_eval(
    toolscore_gold_dir: Path,
    toolscore_trace_dir: Path,
) -> Any:
    """Fixture for evaluating traces against gold standards.

    This fixture provides a convenient function for running evaluations
    in pytest tests. It automatically resolves file paths relative to
    the configured directories.

    Args:
        toolscore_gold_dir: Path to gold standards directory
        toolscore_trace_dir: Path to traces directory

    Returns:
        Function that evaluates a trace against a gold standard

    Example:
        def test_my_agent(toolscore_eval):
            result = toolscore_eval("my_gold.json", "my_trace.json")
            assert result.metrics['invocation_accuracy'] >= 0.9
    """

    def evaluate(
        gold_file: str | Path,
        trace_file: str | Path,
        format: str = "auto",
        validate_side_effects: bool = True,
    ) -> EvaluationResult:
        """Evaluate a trace against a gold standard.

        Args:
            gold_file: Gold standard filename or path
            trace_file: Trace filename or path
            format: Trace format (auto, openai, anthropic, custom)
            validate_side_effects: Whether to validate side effects

        Returns:
            EvaluationResult object with metrics

        Raises:
            FileNotFoundError: If files don't exist
            ValueError: If files are invalid
        """
        # Resolve paths
        gold_path = Path(gold_file)
        if not gold_path.is_absolute():
            gold_path = toolscore_gold_dir / gold_path

        trace_path = Path(trace_file)
        if not trace_path.is_absolute():
            trace_path = toolscore_trace_dir / trace_path

        # Run evaluation
        return evaluate_trace(
            gold_file=gold_path,
            trace_file=trace_path,
            format=format,
            validate_side_effects=validate_side_effects,
        )

    return evaluate


class ToolscoreAssertions:
    """Helper class for Toolscore-specific assertions."""

    @staticmethod
    def assert_invocation_accuracy(
        result: EvaluationResult,
        threshold: float,
        msg: str | None = None,
    ) -> None:
        """Assert that invocation accuracy meets minimum threshold.

        Args:
            result: Evaluation result
            threshold: Minimum required accuracy (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If accuracy is below threshold
        """
        accuracy = result.metrics["invocation_accuracy"]
        if msg is None:
            msg = f"Invocation accuracy {accuracy:.1%} below minimum {threshold:.1%}"
        assert accuracy >= threshold, msg

    @staticmethod
    def assert_selection_accuracy(
        result: EvaluationResult,
        threshold: float,
        msg: str | None = None,
    ) -> None:
        """Assert that selection accuracy meets minimum threshold.

        Args:
            result: Evaluation result
            threshold: Minimum required accuracy (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If accuracy is below threshold
        """
        accuracy = result.metrics["selection_accuracy"]
        if msg is None:
            msg = f"Selection accuracy {accuracy:.1%} below minimum {threshold:.1%}"
        assert accuracy >= threshold, msg

    @staticmethod
    def assert_sequence_accuracy(
        result: EvaluationResult,
        threshold: float,
        msg: str | None = None,
    ) -> None:
        """Assert that sequence accuracy meets minimum threshold.

        Args:
            result: Evaluation result
            threshold: Minimum required accuracy (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If accuracy is below threshold
        """
        accuracy = result.metrics["sequence_metrics"]["sequence_accuracy"]
        if msg is None:
            msg = f"Sequence accuracy {accuracy:.1%} below minimum {threshold:.1%}"
        assert accuracy >= threshold, msg

    @staticmethod
    def assert_argument_f1(
        result: EvaluationResult,
        min_f1: float,
        msg: str | None = None,
    ) -> None:
        """Assert that argument F1 score meets minimum threshold.

        Args:
            result: Evaluation result
            min_f1: Minimum required F1 score (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If F1 score is below threshold
        """
        f1 = result.metrics["argument_metrics"]["f1"]
        if msg is None:
            msg = f"Argument F1 score {f1:.1%} below minimum {min_f1:.1%}"
        assert f1 >= min_f1, msg

    @staticmethod
    def assert_redundancy_below(
        result: EvaluationResult,
        max_rate: float,
        msg: str | None = None,
    ) -> None:
        """Assert that redundant call rate is below maximum threshold.

        Args:
            result: Evaluation result
            max_rate: Maximum allowed redundancy rate (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If redundancy rate exceeds threshold
        """
        rate = result.metrics["efficiency_metrics"]["redundant_rate"]
        if msg is None:
            msg = f"Redundant call rate {rate:.1%} exceeds maximum {max_rate:.1%}"
        assert rate <= max_rate, msg

    @staticmethod
    def assert_score(
        expected: list[dict[str, Any]],
        actual: list[dict[str, Any]],
        min_score: float = 0.9,
        weights: dict[str, float] | None = None,
        strict: bool = False,
    ) -> EvaluationResult:
        """Assert that actual tool calls meet a minimum composite score.

        Delegates to toolscore.core.evaluate() and checks the composite score.

        Args:
            expected: List of expected tool calls (dicts with 'tool' and optional 'args').
            actual: List of actual tool calls from the agent, same format.
            min_score: Minimum composite score required (0.0 to 1.0).
            weights: Optional custom weights for the composite score.
            strict: When True, argument comparison uses pure equality (no
                int/float coercion, no string stripping).  Passed through to
                :func:`toolscore.core.evaluate`.  Default is False.

        Returns:
            EvaluationResult if assertion passes.

        Raises:
            AssertionError: If the composite score is below min_score.
        """
        result = evaluate(expected, actual, weights=weights, strict=strict)
        score = result.score
        assert score >= min_score, f"Composite score {score:.3f} below minimum {min_score:.3f}"
        return result

    @staticmethod
    def assert_all_metrics_above(
        result: EvaluationResult,
        threshold: float,
        msg: str | None = None,
    ) -> None:
        """Assert that all core metrics meet minimum threshold.

        Args:
            result: Evaluation result
            threshold: Minimum required accuracy (0.0 to 1.0)
            msg: Optional custom error message

        Raises:
            AssertionError: If any metric is below threshold
        """
        metrics_to_check = [
            ("invocation_accuracy", result.metrics["invocation_accuracy"]),
            ("selection_accuracy", result.metrics["selection_accuracy"]),
            (
                "sequence_accuracy",
                result.metrics["sequence_metrics"]["sequence_accuracy"],
            ),
            ("argument_f1", result.metrics["argument_metrics"]["f1"]),
        ]

        failures = [(name, value) for name, value in metrics_to_check if value < threshold]

        if failures:
            if msg is None:
                failure_str = ", ".join(f"{name}={value:.1%}" for name, value in failures)
                msg = f"Metrics below {threshold:.1%}: {failure_str}"
            raise AssertionError(msg)


@pytest.fixture
def toolscore_assert() -> ToolscoreAssertions:
    """Fixture providing Toolscore-specific assertion helpers.

    Returns:
        ToolscoreAssertions instance

    Example:
        def test_agent(toolscore_eval, toolscore_assert):
            result = toolscore_eval("gold.json", "trace.json")
            toolscore_assert.assert_invocation_accuracy(result, 0.9)
            toolscore_assert.assert_selection_accuracy(result, 0.9)
    """
    return ToolscoreAssertions()


@pytest.fixture
def toolscore_assert_tools() -> Any:
    """Fixture that directly exposes the assert_tools one-liner.

    Returns:
        The toolscore.core.assert_tools function.

    Example:
        def test_agent(toolscore_assert_tools):
            toolscore_assert_tools(
                expected=[{"tool": "search", "args": {"q": "test"}}],
                actual=[{"tool": "search", "args": {"q": "test"}}],
                min_score=0.9,
            )
    """
    from toolscore.core import assert_tools

    return assert_tools


# ---------------------------------------------------------------------------
# Snapshot fixture — "Jest snapshots for tool calls"
# ---------------------------------------------------------------------------

# Env var that mirrors --toolscore-update (set by the `toolscore record` CLI).
_ENV_UPDATE = "TOOLSCORE_RECORD_UPDATE"
# Stash key under which the per-session snapshot stats accumulator lives.
_STATS_KEY = "_toolscore_snapshot_stats"


class _SnapshotStats:
    """Per-session accumulator of snapshot fixture outcomes.

    The fixture records what happened for each ``toolscore_snapshot(...)`` call
    so :func:`pytest_terminal_summary` can print a single Jest-style summary
    line at the end of the run.
    """

    def __init__(self) -> None:
        self.created = 0
        self.updated = 0
        self.pending = 0
        self.passed = 0
        self.failed = 0

    def summary_line(self) -> str | None:
        """Return a one-line summary, or None when no snapshot activity occurred.

        Example: ``2 snapshots created (pending approval), 1 updated, 5 passed``.
        """
        parts: list[str] = []
        if self.created:
            noun = "snapshot" if self.created == 1 else "snapshots"
            parts.append(f"{self.created} {noun} created (pending approval)")
        if self.updated:
            parts.append(f"{self.updated} updated")
        if self.pending:
            parts.append(f"{self.pending} pending")
        if self.passed:
            parts.append(f"{self.passed} passed")
        if self.failed:
            parts.append(f"{self.failed} failed")
        if not parts:
            return None
        return "toolscore: " + ", ".join(parts)


def _stats_for(config: Any) -> _SnapshotStats:
    """Return the session-scoped stats accumulator, creating it on first use.

    The accumulator is stashed on the pytest ``config`` object so it is shared
    across every fixture instance in the run and readable from the terminal
    summary hook.  Works with the real pytest ``Stash`` (which is mapping-like)
    and with a plain dict in tests.
    """
    stash = config.stash
    # pytest's Stash supports ``in`` / item access via StashKey, but here we use
    # a plain string key, which works for both Stash and a dict in unit tests.
    try:
        existing = stash[_STATS_KEY]
    except KeyError:
        existing = _SnapshotStats()
        stash[_STATS_KEY] = existing
    return existing  # type: ignore[no-any-return]


class _SuppressCI:
    """Context manager that temporarily removes the ``CI`` env signal.

    ``snapshot_check`` (and the snapshots state machine) decides whether to
    *raise* (CI) or *warn* (local) for missing/pending snapshots by reading
    ``os.environ["CI"]`` at call time.  ``--toolscore-allow-pending`` asks us to
    treat those non-evaluating states as non-fatal *even in CI*; the cleanest,
    most robust way to express that within the fixture is to suppress the CI
    signal for the duration of the ``snapshot_check`` call, which deterministically
    routes missing/pending to the warn-and-create path.  Approved snapshots are
    unaffected — they always evaluate regardless of CI.
    """

    def __init__(self, active: bool) -> None:
        self.active = active
        self._saved: str | None = None

    def __enter__(self) -> _SuppressCI:
        if self.active:
            self._saved = os.environ.pop("CI", None)
        return self

    def __exit__(self, *exc: object) -> None:
        if self.active and self._saved is not None:
            os.environ["CI"] = self._saved


class SnapshotFixture:
    """Callable returned by the ``toolscore_snapshot`` fixture.

    Calling the instance records, approves or replays a snapshot for the current
    test via :func:`toolscore.snapshots.snapshot_check`.  Snapshot names default
    to the pytest node id; a second unnamed call in the same test appends
    ``-2``, ``-3`` … so multiple snapshots per test never collide.

    Example::

        def test_booking(toolscore_snapshot):
            result = toolscore_snapshot(agent("book a flight to NYC"))
    """

    def __init__(self, request: Any) -> None:
        self._request = request
        config = request.config
        root = Path(config.getoption("toolscore_snapshot_dir"))
        if not root.is_absolute():
            root = Path(config.rootpath) / root
        from toolscore.snapshots import SnapshotStore

        self._store = SnapshotStore(root)
        self._update = bool(config.getoption("toolscore_update")) or _env_update()
        self._allow_pending = bool(config.getoption("toolscore_allow_pending"))
        self._stats = _stats_for(config)
        # Number of unnamed calls already made in this test (for -2/-3 suffixes).
        self._unnamed_count = 0

    def _default_name(self) -> str:
        """Return the auto-generated snapshot name for an unnamed call."""
        base: str = self._request.node.nodeid
        self._unnamed_count += 1
        if self._unnamed_count == 1:
            return base
        return f"{base}-{self._unnamed_count}"

    def __call__(
        self,
        actual: Any,
        *,
        min_score: float = 1.0,
        weights: dict[str, float] | None = None,
        strict: bool = False,
        name: str | None = None,
    ) -> EvaluationResult | None:
        """Record / approve / replay a snapshot for *actual*.

        Args:
            actual: A raw provider response or list of tool-call dicts.
            min_score: Minimum composite score required when replaying an
                approved baseline (default 1.0 — an exact replay).
            weights: Optional custom metric weights for the composite score.
            strict: When True, argument comparison uses pure equality.
            name: Snapshot name; defaults to the pytest node id (with a ``-2``,
                ``-3`` … suffix for repeated unnamed calls in one test).

        Returns:
            The :class:`~toolscore.core.EvaluationResult` when an approved
            baseline was replayed; otherwise ``None``.
        """
        from toolscore.core import ToolScoreAssertionError
        from toolscore.snapshots import snapshot_check

        snap_name = name if name is not None else self._default_name()
        existed_before = self._store.exists(snap_name)

        try:
            with _SuppressCI(self._allow_pending):
                result = snapshot_check(
                    snap_name,
                    actual,
                    store=self._store,
                    update=self._update,
                    min_score=min_score,
                    weights=weights,
                    strict=strict,
                )
        except ToolScoreAssertionError:
            # An approved replay drifted, or (in CI without allow-pending) a
            # missing/pending snapshot was rejected.  Count and re-raise so the
            # test fails as expected.
            self._stats.failed += 1
            raise

        # Categorize the non-raising outcome for the terminal summary.
        if self._update:
            self._stats.updated += 1
        elif result is not None:
            # State 4: an approved baseline was replayed and matched.
            self._stats.passed += 1
        elif not existed_before:
            # State 1 (local / allow-pending): a new snapshot was created.
            self._stats.created += 1
        else:
            # State 3: the snapshot exists but is still pending approval.
            self._stats.pending += 1

        return result


def _env_update() -> bool:
    """Return True when TOOLSCORE_RECORD_UPDATE is set to a truthy value.

    Read at call time so tests can monkeypatch ``os.environ``.  Any non-empty
    value other than ``"0"``/``"false"``/``"no"`` (case-insensitive) is truthy.
    """
    raw = os.environ.get(_ENV_UPDATE, "")
    return raw.strip().lower() not in {"", "0", "false", "no"}


@pytest.fixture
def toolscore_snapshot(request: Any) -> SnapshotFixture:
    """Jest-style snapshot fixture for agent tool calls.

    Returns a callable that records an agent's tool calls on first run, replays
    them against an approved baseline afterwards, and fails the test on drift.

    The snapshot store root comes from ``--toolscore-snapshot-dir`` (relative to
    the pytest rootdir); ``--toolscore-update`` (or ``TOOLSCORE_RECORD_UPDATE=1``)
    re-records baselines; ``--toolscore-allow-pending`` downgrades the CI failure
    for missing/pending snapshots to a warning.

    Example::

        def test_books_a_flight(toolscore_snapshot):
            toolscore_snapshot(my_agent("book a flight to NYC"))
            # First run: records a pending snapshot and warns.
            # After `toolscore approve`: replays and fails on drift.
    """
    return SnapshotFixture(request)


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:  # noqa: ARG001
    """Print a one-line snapshot activity summary at the end of the run.

    Nothing is printed when no ``toolscore_snapshot`` calls happened.

    Args:
        terminalreporter: Pytest's terminal reporter.
        exitstatus: The run's exit status (unused).
        config: The pytest config holding the snapshot stats accumulator.
    """
    stash = getattr(config, "stash", None)
    if stash is None:
        return
    try:
        stats = stash[_STATS_KEY]
    except KeyError:
        return
    line = stats.summary_line()
    if line:
        terminalreporter.write_line(line)
