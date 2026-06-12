"""Unit tests for pytest plugin assertion helpers and the snapshot fixture."""

import pytest

from toolscore.adapters.base import ToolCall
from toolscore.core import EvaluationResult
from toolscore.pytest_plugin import ToolscoreAssertions

# Enable pytester so the snapshot-fixture tests can run pytest-in-pytest and
# exercise the full Jest-style record / approve / replay loop end to end.
pytest_plugins = ["pytester"]


@pytest.fixture
def mock_result():
    """Create a mock evaluation result for testing."""
    gold_calls = [
        ToolCall(tool="test_tool", args={"x": 1}),
    ]
    trace_calls = [
        ToolCall(tool="test_tool", args={"x": 1}),
    ]

    metrics = {
        "invocation_accuracy": 0.95,
        "selection_accuracy": 0.90,
        "sequence_metrics": {
            "edit_distance": 0.0,
            "normalized_distance": 0.0,
            "sequence_accuracy": 1.0,
        },
        "argument_metrics": {
            "precision": 0.88,
            "recall": 0.92,
            "f1": 0.90,
        },
        "efficiency_metrics": {
            "redundant_count": 0,
            "total_calls": 1,
            "redundant_rate": 0.0,
        },
        "side_effect_metrics": {
            "total_checks": 0,
            "passed_checks": 0,
            "success_rate": 1.0,
            "details": [],
        },
    }

    result = EvaluationResult()
    result.gold_calls = gold_calls
    result.trace_calls = trace_calls
    result.metrics = metrics

    return result


class TestToolscoreAssertions:
    """Tests for ToolscoreAssertions helper class."""

    def test_assert_invocation_accuracy_pass(self, mock_result):
        """Test invocation accuracy assertion passes."""
        assertions = ToolscoreAssertions()
        # Should not raise
        assertions.assert_invocation_accuracy(mock_result, 0.9)

    def test_assert_invocation_accuracy_fail(self, mock_result):
        """Test invocation accuracy assertion fails."""
        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Invocation accuracy"):
            assertions.assert_invocation_accuracy(mock_result, 0.99)

    def test_assert_invocation_accuracy_custom_msg(self, mock_result):
        """Test invocation accuracy assertion with custom message."""
        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Custom error"):
            assertions.assert_invocation_accuracy(mock_result, 0.99, msg="Custom error")

    def test_assert_selection_accuracy_pass(self, mock_result):
        """Test selection accuracy assertion passes."""
        assertions = ToolscoreAssertions()
        assertions.assert_selection_accuracy(mock_result, 0.85)

    def test_assert_selection_accuracy_fail(self, mock_result):
        """Test selection accuracy assertion fails."""
        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Selection accuracy"):
            assertions.assert_selection_accuracy(mock_result, 0.95)

    def test_assert_sequence_accuracy_pass(self, mock_result):
        """Test sequence accuracy assertion passes."""
        assertions = ToolscoreAssertions()
        assertions.assert_sequence_accuracy(mock_result, 0.95)

    def test_assert_sequence_accuracy_fail(self, mock_result):
        """Test sequence accuracy assertion fails."""
        # Modify result to have lower sequence accuracy
        mock_result.metrics["sequence_metrics"]["sequence_accuracy"] = 0.5

        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Sequence accuracy"):
            assertions.assert_sequence_accuracy(mock_result, 0.8)

    def test_assert_argument_f1_pass(self, mock_result):
        """Test argument F1 assertion passes."""
        assertions = ToolscoreAssertions()
        assertions.assert_argument_f1(mock_result, 0.85)

    def test_assert_argument_f1_fail(self, mock_result):
        """Test argument F1 assertion fails."""
        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Argument F1"):
            assertions.assert_argument_f1(mock_result, 0.95)

    def test_assert_redundancy_below_pass(self, mock_result):
        """Test redundancy assertion passes."""
        assertions = ToolscoreAssertions()
        assertions.assert_redundancy_below(mock_result, 0.1)

    def test_assert_redundancy_below_fail(self, mock_result):
        """Test redundancy assertion fails."""
        # Modify result to have high redundancy
        mock_result.metrics["efficiency_metrics"]["redundant_rate"] = 0.5

        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="Redundant call rate"):
            assertions.assert_redundancy_below(mock_result, 0.2)

    def test_assert_all_metrics_above_pass(self, mock_result):
        """Test all metrics assertion passes."""
        assertions = ToolscoreAssertions()
        assertions.assert_all_metrics_above(mock_result, 0.85)

    def test_assert_all_metrics_above_fail(self, mock_result):
        """Test all metrics assertion fails when one metric is low."""
        # Modify one metric to be below threshold
        mock_result.metrics["selection_accuracy"] = 0.5

        assertions = ToolscoreAssertions()
        with pytest.raises(AssertionError, match="selection_accuracy"):
            assertions.assert_all_metrics_above(mock_result, 0.8)

    def test_assert_all_metrics_above_multiple_failures(self, mock_result):
        """Test all metrics assertion shows all failing metrics."""
        # Modify multiple metrics to be below threshold
        mock_result.metrics["invocation_accuracy"] = 0.5
        mock_result.metrics["selection_accuracy"] = 0.6

        assertions = ToolscoreAssertions()
        with pytest.raises(
            AssertionError,
            match=r"invocation_accuracy.*selection_accuracy",
        ):
            assertions.assert_all_metrics_above(mock_result, 0.8)

    def test_assert_score_pass(self):
        """assert_score with low threshold should pass for matching calls."""
        assertions = ToolscoreAssertions()
        expected = [{"tool": "search", "args": {"q": "weather"}}]
        actual = [{"tool": "search", "args": {"q": "weather"}}]
        result = assertions.assert_score(expected, actual, min_score=0.5)
        assert result.score >= 0.5

    def test_assert_score_fail(self):
        """assert_score with high threshold should fail for mismatched calls."""
        assertions = ToolscoreAssertions()
        expected = [{"tool": "search", "args": {"q": "weather"}}]
        actual = [{"tool": "lookup", "args": {"q": "news"}}]
        with pytest.raises(AssertionError, match="Composite score"):
            assertions.assert_score(expected, actual, min_score=0.99)

    def test_assert_score_strict_propagates(self):
        """assert_score(strict=True) must propagate strict to evaluate().

        With strict=False, int 1 == float 1.0, so argument F1 == 1.0 and the
        assertion passes.  With strict=True the types differ, so argument F1
        drops below 1.0, meaning the assertion must fail at threshold 0.99.
        """
        assertions = ToolscoreAssertions()
        expected = [{"tool": "t", "args": {"x": 1}}]
        actual = [{"tool": "t", "args": {"x": 1.0}}]

        # Lenient: should pass at high threshold (full score)
        result = assertions.assert_score(expected, actual, min_score=0.0, strict=False)
        lenient_arg_f1 = result.metrics["argument_metrics"]["f1"]
        assert lenient_arg_f1 == 1.0, "Lenient mode must treat int 1 == float 1.0"

        # Strict: argument F1 drops, so assertion should fail at threshold 0.99
        with pytest.raises(AssertionError, match="Composite score"):
            assertions.assert_score(expected, actual, min_score=0.99, strict=True)


def test_toolscore_assert_tools_fixture():
    """Verify toolscore_assert_tools fixture returns a callable."""
    from toolscore.core import assert_tools

    assert callable(assert_tools)


def test_min_accuracy_marker_not_registered():
    """The dead min_accuracy marker must no longer be registered by the plugin.

    We inspect the plugin source directly so the test doesn't depend on a
    live pytest session having the plugin loaded.
    """
    import inspect

    from toolscore import pytest_plugin

    source = inspect.getsource(pytest_plugin)
    assert "min_accuracy" not in source, (
        "The 'min_accuracy' marker registration was supposed to be removed "
        "but is still present in toolscore/pytest_plugin.py"
    )


# ---------------------------------------------------------------------------
# Snapshot fixture unit behaviour (SnapshotFixture class, in-process)
# ---------------------------------------------------------------------------


class _FakeNode:
    def __init__(self, nodeid):
        self.nodeid = nodeid


class _FakeConfig:
    """Minimal stand-in for pytest's config object for unit tests."""

    def __init__(self, rootpath, options):
        self._rootpath = rootpath
        self._options = options
        self.stash = {}

    @property
    def rootpath(self):
        return self._rootpath

    def getoption(self, name):
        return self._options[name]


class _FakeRequest:
    def __init__(self, config, nodeid):
        self.config = config
        self.node = _FakeNode(nodeid)


def _make_request(tmp_path, nodeid, *, snapshot_dir=".toolscore/snapshots", update=False):
    options = {
        "toolscore_snapshot_dir": snapshot_dir,
        "toolscore_update": update,
        "toolscore_allow_pending": False,
    }
    config = _FakeConfig(tmp_path, options)
    return _FakeRequest(config, nodeid)


def test_snapshot_fixture_default_name_is_nodeid(tmp_path, monkeypatch):
    """An unnamed call uses request.node.nodeid as the snapshot name."""
    monkeypatch.delenv("CI", raising=False)
    from toolscore.pytest_plugin import SnapshotFixture
    from toolscore.snapshots import SnapshotStore

    request = _make_request(tmp_path, "tests/test_x.py::test_foo")
    fixture = SnapshotFixture(request)
    with pytest.warns(UserWarning):
        fixture([{"tool": "search", "args": {"q": "x"}}])

    store = SnapshotStore(tmp_path / ".toolscore/snapshots")
    assert store.exists("tests/test_x.py::test_foo")


def test_snapshot_fixture_explicit_name_used_verbatim(tmp_path, monkeypatch):
    """An explicit name= is used verbatim, not the nodeid."""
    monkeypatch.delenv("CI", raising=False)
    from toolscore.pytest_plugin import SnapshotFixture
    from toolscore.snapshots import SnapshotStore

    request = _make_request(tmp_path, "tests/test_x.py::test_foo")
    fixture = SnapshotFixture(request)
    with pytest.warns(UserWarning):
        fixture([{"tool": "search", "args": {"q": "x"}}], name="my_custom_snap")

    store = SnapshotStore(tmp_path / ".toolscore/snapshots")
    assert store.exists("my_custom_snap")
    assert not store.exists("tests/test_x.py::test_foo")


def test_snapshot_fixture_unnamed_calls_get_suffixes(tmp_path, monkeypatch):
    """Two unnamed calls in one test create distinct -2 suffixed names."""
    monkeypatch.delenv("CI", raising=False)
    from toolscore.pytest_plugin import SnapshotFixture
    from toolscore.snapshots import SnapshotStore

    request = _make_request(tmp_path, "tests/test_x.py::test_foo")
    fixture = SnapshotFixture(request)
    with pytest.warns(UserWarning):
        fixture([{"tool": "a", "args": {}}])
    with pytest.warns(UserWarning):
        fixture([{"tool": "b", "args": {}}])

    store = SnapshotStore(tmp_path / ".toolscore/snapshots")
    assert store.exists("tests/test_x.py::test_foo")
    assert store.exists("tests/test_x.py::test_foo-2")


def test_snapshot_fixture_custom_dir(tmp_path, monkeypatch):
    """A custom --toolscore-snapshot-dir is respected, relative to rootpath."""
    monkeypatch.delenv("CI", raising=False)
    from toolscore.pytest_plugin import SnapshotFixture
    from toolscore.snapshots import SnapshotStore

    request = _make_request(tmp_path, "test::t", snapshot_dir="custom/snaps")
    fixture = SnapshotFixture(request)
    with pytest.warns(UserWarning):
        fixture([{"tool": "a", "args": {}}])

    assert (tmp_path / "custom/snaps").is_dir()
    store = SnapshotStore(tmp_path / "custom/snaps")
    assert store.exists("test::t")


def test_snapshot_fixture_env_update(tmp_path, monkeypatch):
    """TOOLSCORE_RECORD_UPDATE=1 forces an update (overwrite + approve)."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("TOOLSCORE_RECORD_UPDATE", "1")
    from toolscore.pytest_plugin import SnapshotFixture
    from toolscore.snapshots import SnapshotStore

    request = _make_request(tmp_path, "test::t")
    fixture = SnapshotFixture(request)
    with pytest.warns(UserWarning, match="updated"):
        fixture([{"tool": "a", "args": {}}])

    store = SnapshotStore(tmp_path / ".toolscore/snapshots")
    snap = store.load("test::t")
    assert snap is not None
    assert snap.approved is True


def test_snapshot_fixture_replay_approved_passes(tmp_path, monkeypatch):
    """A matching replay against an approved snapshot returns a result."""
    monkeypatch.delenv("CI", raising=False)
    from toolscore.pytest_plugin import SnapshotFixture
    from toolscore.snapshots import SnapshotStore

    calls = [{"tool": "search", "args": {"q": "x"}}]
    store = SnapshotStore(tmp_path / ".toolscore/snapshots")
    request = _make_request(tmp_path, "test::t")
    fixture = SnapshotFixture(request)
    with pytest.warns(UserWarning):
        fixture(calls)
    store.approve("test::t")

    # Fresh fixture instance to reset the per-instance counter.
    fixture2 = SnapshotFixture(_make_request(tmp_path, "test::t"))
    result = fixture2(calls)
    assert result is not None
    assert result.score >= 0.99


def test_snapshot_fixture_replay_drift_fails(tmp_path, monkeypatch):
    """A drifted replay against an approved snapshot raises with a diff."""
    monkeypatch.delenv("CI", raising=False)
    from toolscore.core import ToolScoreAssertionError
    from toolscore.pytest_plugin import SnapshotFixture
    from toolscore.snapshots import SnapshotStore

    store = SnapshotStore(tmp_path / ".toolscore/snapshots")
    request = _make_request(tmp_path, "test::t")
    fixture = SnapshotFixture(request)
    with pytest.warns(UserWarning):
        fixture([{"tool": "search", "args": {"q": "x"}}])
    store.approve("test::t")

    fixture2 = SnapshotFixture(_make_request(tmp_path, "test::t"))
    with pytest.raises(ToolScoreAssertionError):
        fixture2([{"tool": "delete_everything", "args": {}}])


def test_snapshot_fixture_ci_missing_fails(tmp_path, monkeypatch):
    """In CI, a missing snapshot raises and is NOT created."""
    monkeypatch.setenv("CI", "1")
    from toolscore.core import ToolScoreAssertionError
    from toolscore.pytest_plugin import SnapshotFixture
    from toolscore.snapshots import SnapshotStore

    request = _make_request(tmp_path, "test::t")
    fixture = SnapshotFixture(request)
    with pytest.raises(ToolScoreAssertionError):
        fixture([{"tool": "a", "args": {}}])

    store = SnapshotStore(tmp_path / ".toolscore/snapshots")
    assert not store.exists("test::t")


def test_snapshot_fixture_ci_allow_pending_warns(tmp_path, monkeypatch):
    """--toolscore-allow-pending downgrades the CI missing/pending raise to a warning."""
    monkeypatch.setenv("CI", "1")
    from toolscore.pytest_plugin import SnapshotFixture
    from toolscore.snapshots import SnapshotStore

    options = {
        "toolscore_snapshot_dir": ".toolscore/snapshots",
        "toolscore_update": False,
        "toolscore_allow_pending": True,
    }
    config = _FakeConfig(tmp_path, options)
    request = _FakeRequest(config, "test::t")
    fixture = SnapshotFixture(request)
    with pytest.warns(UserWarning):
        fixture([{"tool": "a", "args": {}}])

    # With CI suppressed for the call, the snapshot IS created locally-style.
    store = SnapshotStore(tmp_path / ".toolscore/snapshots")
    assert store.exists("test::t")


def test_snapshot_fixture_records_accumulator_stats(tmp_path, monkeypatch):
    """The fixture records created counts into the config accumulator."""
    monkeypatch.delenv("CI", raising=False)
    from toolscore.pytest_plugin import SnapshotFixture, _SnapshotStats, _stats_for

    request = _make_request(tmp_path, "test::t")
    fixture = SnapshotFixture(request)
    with pytest.warns(UserWarning):
        fixture([{"tool": "a", "args": {}}])

    stats = _stats_for(request.config)
    assert isinstance(stats, _SnapshotStats)
    assert stats.created == 1


def test_snapshot_stats_summary_line_only_when_active():
    """_SnapshotStats.summary_line() returns None when no activity occurred."""
    from toolscore.pytest_plugin import _SnapshotStats

    stats = _SnapshotStats()
    assert stats.summary_line() is None
    stats.created = 2
    stats.updated = 1
    stats.passed = 5
    line = stats.summary_line()
    assert line is not None
    assert "2" in line and "created" in line
    assert "1" in line and "updated" in line
    assert "5" in line and "passed" in line


# ---------------------------------------------------------------------------
# Full Jest loop via pytester (pytest-in-pytest)
# ---------------------------------------------------------------------------

_AGENT_TEST = """
def agent():
    return [{"tool": "search", "args": {"q": "weather"}}]

def test_agent(toolscore_snapshot):
    toolscore_snapshot(agent())
"""

_MUTATED_AGENT_TEST = """
def agent():
    return [{"tool": "delete_everything", "args": {}}]

def test_agent(toolscore_snapshot):
    toolscore_snapshot(agent())
"""

# The plugin is installed via the ``pytest11`` entrypoint (see pyproject.toml),
# so pytester's inner runs auto-load it — no ``-p`` needed (and passing one would
# double-register it).  We only disable the cache provider for hermetic runs.
_PLUGIN_ARGS = ("-p", "no:cacheprovider")


def _approve_all(pytester, snapshot_dir=".toolscore/snapshots"):
    from toolscore.snapshots import SnapshotStore

    store = SnapshotStore(pytester.path / snapshot_dir)
    for snap in store.list():
        store.approve(snap.name)


def test_pytester_first_run_creates_and_summary(pytester, monkeypatch):
    """(1) First run creates a snapshot, passes with a warning, and the summary
    line reports the creation."""
    monkeypatch.delenv("CI", raising=False)
    pytester.makepyfile(test_agent=_AGENT_TEST)
    result = pytester.runpytest(*_PLUGIN_ARGS, "-W", "ignore")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*toolscore:*snapshot*created*"])
    snaps = list((pytester.path / ".toolscore" / "snapshots").glob("*.json"))
    assert len(snaps) == 1


def test_pytester_approved_replay_clean(pytester, monkeypatch):
    """(2) After manual approval, a matching replay passes cleanly."""
    monkeypatch.delenv("CI", raising=False)
    pytester.makepyfile(test_agent=_AGENT_TEST)
    pytester.runpytest(*_PLUGIN_ARGS, "-W", "ignore")
    _approve_all(pytester)
    result = pytester.runpytest(*_PLUGIN_ARGS)
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*toolscore:*passed*"])


def test_pytester_drift_fails_with_diff(pytester, monkeypatch):
    """(3) Mutating the agent output makes the approved replay fail with a diff."""
    monkeypatch.delenv("CI", raising=False)
    pytester.makepyfile(test_agent=_AGENT_TEST)
    pytester.runpytest(*_PLUGIN_ARGS, "-W", "ignore")
    _approve_all(pytester)
    pytester.makepyfile(test_agent=_MUTATED_AGENT_TEST)
    result = pytester.runpytest(*_PLUGIN_ARGS)
    result.assert_outcomes(failed=1)
    # The rich diff mentions the expected baseline tool name.
    result.stdout.fnmatch_lines(["*search*"])


def test_pytester_update_flag_rerecords(pytester, monkeypatch):
    """(4) --toolscore-update re-records the snapshot and passes."""
    monkeypatch.delenv("CI", raising=False)
    pytester.makepyfile(test_agent=_AGENT_TEST)
    pytester.runpytest(*_PLUGIN_ARGS, "-W", "ignore")
    _approve_all(pytester)
    pytester.makepyfile(test_agent=_MUTATED_AGENT_TEST)
    result = pytester.runpytest(*_PLUGIN_ARGS, "--toolscore-update", "-W", "ignore")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*toolscore:*updated*"])
    from toolscore.snapshots import SnapshotStore

    store = SnapshotStore(pytester.path / ".toolscore" / "snapshots")
    snap = store.list()[0]
    assert snap.approved is True
    assert snap.calls[0]["tool"] == "delete_everything"


def test_pytester_ci_missing_fails(pytester, monkeypatch):
    """(5a) In CI, a missing snapshot fails the test."""
    monkeypatch.setenv("CI", "1")
    pytester.makepyfile(test_agent=_AGENT_TEST)
    result = pytester.runpytest(*_PLUGIN_ARGS)
    result.assert_outcomes(failed=1)


def test_pytester_ci_allow_pending_warns(pytester, monkeypatch):
    """(5b) --toolscore-allow-pending makes a missing snapshot warn (pass) in CI."""
    monkeypatch.setenv("CI", "1")
    pytester.makepyfile(test_agent=_AGENT_TEST)
    result = pytester.runpytest(*_PLUGIN_ARGS, "--toolscore-allow-pending", "-W", "ignore")
    result.assert_outcomes(passed=1)


def test_pytester_custom_snapshot_dir(pytester, monkeypatch):
    """(6) A custom --toolscore-snapshot-dir is respected."""
    monkeypatch.delenv("CI", raising=False)
    pytester.makepyfile(test_agent=_AGENT_TEST)
    result = pytester.runpytest(
        *_PLUGIN_ARGS, "--toolscore-snapshot-dir", "my_snaps", "-W", "ignore"
    )
    result.assert_outcomes(passed=1)
    snaps = list((pytester.path / "my_snaps").glob("*.json"))
    assert len(snaps) == 1


def test_pytester_two_unnamed_calls_suffix(pytester, monkeypatch):
    """(7) Two unnamed calls in one test create two files with a -2 suffix."""
    monkeypatch.delenv("CI", raising=False)
    pytester.makepyfile(
        test_agent="""
        def test_multi(toolscore_snapshot):
            toolscore_snapshot([{"tool": "a", "args": {}}])
            toolscore_snapshot([{"tool": "b", "args": {}}])
        """
    )
    result = pytester.runpytest(*_PLUGIN_ARGS, "-W", "ignore")
    result.assert_outcomes(passed=1)
    from toolscore.snapshots import SnapshotStore

    store = SnapshotStore(pytester.path / ".toolscore" / "snapshots")
    names = {s.name for s in store.list()}
    assert any(n.endswith("test_multi") for n in names)
    assert any(n.endswith("test_multi-2") for n in names)


def test_pytester_explicit_name(pytester, monkeypatch):
    """(8) An explicit name= is used verbatim."""
    monkeypatch.delenv("CI", raising=False)
    pytester.makepyfile(
        test_agent="""
        def test_named(toolscore_snapshot):
            toolscore_snapshot([{"tool": "a", "args": {}}], name="explicit_name")
        """
    )
    result = pytester.runpytest(*_PLUGIN_ARGS, "-W", "ignore")
    result.assert_outcomes(passed=1)
    from toolscore.snapshots import SnapshotStore

    store = SnapshotStore(pytester.path / ".toolscore" / "snapshots")
    assert store.exists("explicit_name")


def test_pytester_env_var_update(pytester, monkeypatch):
    """(9) TOOLSCORE_RECORD_UPDATE=1 forces an update via the fixture."""
    monkeypatch.delenv("CI", raising=False)
    pytester.makepyfile(test_agent=_AGENT_TEST)
    pytester.runpytest(*_PLUGIN_ARGS, "-W", "ignore")
    _approve_all(pytester)
    pytester.makepyfile(test_agent=_MUTATED_AGENT_TEST)
    monkeypatch.setenv("TOOLSCORE_RECORD_UPDATE", "1")
    result = pytester.runpytest(*_PLUGIN_ARGS, "-W", "ignore")
    result.assert_outcomes(passed=1)
    from toolscore.snapshots import SnapshotStore

    store = SnapshotStore(pytester.path / ".toolscore" / "snapshots")
    snap = store.list()[0]
    assert snap.calls[0]["tool"] == "delete_everything"
    assert snap.approved is True
