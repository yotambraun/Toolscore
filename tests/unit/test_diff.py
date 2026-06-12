"""Tests for toolscore.diff — rich failure-diff rendering."""

from __future__ import annotations

import re

import pytest

from toolscore.adapters.base import ToolCall
from toolscore.core import (
    EvaluationResult,
    ToolScoreAssertionError,
    _check_min_score,
    assert_tools,
    evaluate,
)
from toolscore.diff import render_failure
from toolscore.matchers import Regex

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _has_ansi(text: str) -> bool:
    return bool(_ANSI_RE.search(text))


def _make_result(
    gold: list[ToolCall],
    trace: list[ToolCall],
    *,
    selection: float = 1.0,
    arg_f1: float = 1.0,
    seq: float = 1.0,
    redundant_rate: float = 0.0,
) -> EvaluationResult:
    """Build a minimal EvaluationResult with provided metrics."""
    r = EvaluationResult()
    r.gold_calls = gold
    r.trace_calls = trace
    r.metrics["selection_accuracy"] = selection
    r.metrics["argument_metrics"] = {"f1": arg_f1, "precision": arg_f1, "recall": arg_f1}
    r.metrics["sequence_metrics"] = {"sequence_accuracy": seq, "edit_distance": 0}
    r.metrics["efficiency_metrics"] = {
        "redundant_rate": redundant_rate,
        "redundant_count": 0,
        "total_calls": len(trace),
    }
    r.metrics["tool_correctness_metrics"] = {
        "tool_correctness": 1.0,
        "correct_count": len(gold),
        "total_expected": len(gold),
        "missing_tools": [],
        "extra_tools": [],
    }
    return r


# ---------------------------------------------------------------------------
# build_diff_table
# ---------------------------------------------------------------------------


class TestBuildDiffTable:
    """Tests for build_diff_table."""

    def test_perfect_match_produces_check_marks(self) -> None:
        """All-equal sequences render with ✓ status."""
        gold = [ToolCall(tool="search", args={"q": "test"})]
        trace = [ToolCall(tool="search", args={"q": "test"})]
        result = _make_result(gold, trace)
        text = render_failure(result, min_score=0.9, color=False)
        assert "✓" in text

    def test_arg_mismatch_shows_diff(self) -> None:
        """Arg value mismatch row shows ``key: expected ≠ actual`` notation."""
        gold = [ToolCall(tool="fly", args={"origin": "NYC", "dest": "LAX"})]
        trace = [ToolCall(tool="fly", args={"origin": "JFK", "dest": "LAX"})]
        result = _make_result(gold, trace, arg_f1=0.5)
        text = render_failure(result, min_score=0.9, color=False)
        assert "origin:" in text
        assert "NYC" in text
        assert "JFK" in text
        assert "≠" in text

    def test_missing_call_shows_missing(self) -> None:
        """A gold-only call renders MISSING on the actual side."""
        gold = [
            ToolCall(tool="search", args={}),
            ToolCall(tool="book", args={}),
        ]
        trace = [ToolCall(tool="search", args={})]
        result = _make_result(gold, trace, selection=0.5, seq=0.5)
        text = render_failure(result, min_score=0.9, color=False)
        assert "MISSING" in text

    def test_extra_call_shows_extra(self) -> None:
        """A trace-only call renders EXTRA on the expected side."""
        gold = [ToolCall(tool="search", args={})]
        trace = [
            ToolCall(tool="search", args={}),
            ToolCall(tool="extra_call", args={}),
        ]
        result = _make_result(gold, trace, seq=0.5)
        text = render_failure(result, min_score=0.9, color=False)
        assert "EXTRA" in text

    def test_matcher_repr_appears(self) -> None:
        """Matcher repr (e.g. Regex(...)) should appear in the diff output."""
        gold = [ToolCall(tool="fly", args={"dest": Regex(r"NY.*")})]
        trace = [ToolCall(tool="fly", args={"dest": "Boston"})]
        result = _make_result(gold, trace, arg_f1=0.0)
        text = render_failure(result, min_score=0.9, color=False)
        assert "Regex(" in text

    def test_long_values_truncated(self) -> None:
        """Values longer than 40 chars are truncated with an ellipsis."""
        long_val = "x" * 80
        gold = [ToolCall(tool="call", args={"key": long_val})]
        trace = [ToolCall(tool="call", args={"key": long_val})]
        result = _make_result(gold, trace)
        text = render_failure(result, min_score=0.9, color=False)
        assert "…" in text
        # The full 80-char value should not appear
        assert long_val not in text

    def test_missing_key_shows_missing_label(self) -> None:
        """Arg missing from trace shows ``missing: key`` in status."""
        gold = [ToolCall(tool="call", args={"required_arg": "value"})]
        trace = [ToolCall(tool="call", args={})]
        result = _make_result(gold, trace, arg_f1=0.0)
        text = render_failure(result, min_score=0.9, color=False)
        assert "missing:" in text

    def test_unexpected_key_shows_unexpected_label(self) -> None:
        """Extra arg in trace shows ``unexpected: key`` in status."""
        gold = [ToolCall(tool="call", args={})]
        trace = [ToolCall(tool="call", args={"extra_arg": "value"})]
        result = _make_result(gold, trace, arg_f1=0.0)
        text = render_failure(result, min_score=0.9, color=False)
        assert "unexpected:" in text


# ---------------------------------------------------------------------------
# render_failure
# ---------------------------------------------------------------------------


class TestRenderFailure:
    """Tests for render_failure."""

    def _failing_result(self) -> EvaluationResult:
        gold = [
            ToolCall(tool="search", args={"q": "flights"}),
            ToolCall(tool="book_flight", args={"origin": "NYC", "dest": "LAX"}),
        ]
        trace = [
            ToolCall(tool="search", args={"q": "cheap flights"}),
            ToolCall(tool="book_train", args={"origin": "NYC", "dest": "BOS"}),
        ]
        return _make_result(gold, trace, selection=0.5, arg_f1=0.5, seq=0.5)

    def test_footer_contains_score_breakdown(self) -> None:
        """Footer line includes score and all three sub-scores."""
        result = self._failing_result()
        text = render_failure(result, min_score=0.9, color=False)
        assert "score" in text
        assert "required" in text
        assert "selection" in text
        assert "args" in text
        assert "sequence" in text

    def test_footer_contains_at_least_one_tip(self) -> None:
        """At least one actionable tip appears in the output."""
        result = self._failing_result()
        text = render_failure(result, min_score=0.9, color=False)
        assert "Tips:" in text or "tip" in text.lower() or "•" in text

    def test_color_false_no_ansi(self) -> None:
        """color=False must produce no ANSI escape sequences."""
        result = self._failing_result()
        text = render_failure(result, min_score=0.9, color=False)
        assert not _has_ansi(text), "ANSI escapes found in plain-text output"

    def test_color_true_has_ansi(self) -> None:
        """color=True must include ANSI escape sequences."""
        result = self._failing_result()
        text = render_failure(result, min_score=0.9, color=True)
        assert _has_ansi(text), "No ANSI escapes found in color output"

    def test_empty_sequences(self) -> None:
        """Empty gold and trace should render without error."""
        result = _make_result([], [])
        text = render_failure(result, min_score=0.9, color=False)
        assert isinstance(text, str)

    def test_score_values_in_footer(self) -> None:
        """The exact score and min_score values appear in the footer."""
        gold = [ToolCall(tool="t", args={})]
        trace = [ToolCall(tool="wrong", args={})]
        result = _make_result(gold, trace, selection=0.0, arg_f1=0.0, seq=0.0)
        text = render_failure(result, min_score=0.75, color=False)
        assert "0.75" in text


# ---------------------------------------------------------------------------
# Integration: assert_tools and _check_min_score
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests wiring assert_tools / _check_min_score to render_failure."""

    def test_assert_tools_failure_message_contains_table_markers(self) -> None:
        """assert_tools failure message contains table structure markers."""
        with pytest.raises(ToolScoreAssertionError) as exc_info:
            assert_tools(
                expected=[{"tool": "search", "args": {"q": "test"}}],
                actual=[{"tool": "wrong_tool", "args": {"q": "other"}}],
                min_score=0.99,
            )
        msg = str(exc_info.value)
        # Table borders or column headers
        assert "Expected" in msg or "#" in msg or "Actual" in msg

    def test_assert_tools_failure_message_contains_score_breakdown(self) -> None:
        """assert_tools failure message contains the score breakdown line."""
        with pytest.raises(ToolScoreAssertionError) as exc_info:
            assert_tools(
                expected=[{"tool": "search", "args": {"q": "test"}}],
                actual=[{"tool": "wrong_tool", "args": {}}],
                min_score=0.99,
            )
        msg = str(exc_info.value)
        assert "score" in msg
        assert "required" in msg

    def test_assert_tools_failure_message_has_no_ansi(self) -> None:
        """assert_tools embeds plain text (no ANSI) in the exception message."""
        with pytest.raises(ToolScoreAssertionError) as exc_info:
            assert_tools(
                expected=[{"tool": "a"}],
                actual=[{"tool": "b"}],
                min_score=0.99,
            )
        msg = str(exc_info.value)
        assert not _has_ansi(msg)

    def test_check_min_score_path_via_evaluate(self) -> None:
        """_check_min_score called directly raises with rendered diff."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "hello"}}],
            actual=[{"tool": "lookup", "args": {"q": "world"}}],
        )
        with pytest.raises(ToolScoreAssertionError) as exc_info:
            _check_min_score(result, 0.99)
        msg = str(exc_info.value)
        assert "score" in msg
        assert "required" in msg

    def test_assert_tools_missing_call_message(self) -> None:
        """Missing call in actual causes MISSING to appear in the error message."""
        with pytest.raises(ToolScoreAssertionError) as exc_info:
            assert_tools(
                expected=[
                    {"tool": "step1", "args": {}},
                    {"tool": "step2", "args": {}},
                ],
                actual=[{"tool": "step1", "args": {}}],
                min_score=0.99,
            )
        msg = str(exc_info.value)
        assert "MISSING" in msg

    def test_assert_tools_extra_call_message(self) -> None:
        """Extra call in actual causes EXTRA to appear in the error message."""
        with pytest.raises(ToolScoreAssertionError) as exc_info:
            assert_tools(
                expected=[{"tool": "step1", "args": {}}],
                actual=[
                    {"tool": "step1", "args": {}},
                    {"tool": "step2", "args": {}},
                ],
                min_score=0.99,
            )
        msg = str(exc_info.value)
        assert "EXTRA" in msg

    def test_passing_assert_tools_no_exception(self) -> None:
        """Passing assert_tools returns the result without raising."""
        result = assert_tools(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[{"tool": "search", "args": {"q": "test"}}],
            min_score=0.9,
        )
        assert result.score >= 0.9
