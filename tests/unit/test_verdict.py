"""Tests for the shared verdict primitives and the agent-side fix list.

Covers ``toolscore.verdict`` (letter grades + ``FixSuggestion``),
``EvaluationResult.grade``, and ``toolscore.diff.build_eval_fix_list`` -- the
agent-side equivalent of the MCP scorecard's "Top issues to fix" verdict.
"""

from __future__ import annotations

from toolscore import evaluate
from toolscore.diff import build_eval_fix_list
from toolscore.verdict import GRADE_ORDER, FixSuggestion, letter_grade

# -- letter_grade ---------------------------------------------------------


def test_letter_grade_bands() -> None:
    assert letter_grade(1.0) == "A"
    assert letter_grade(0.9) == "A"
    assert letter_grade(0.89) == "B"
    assert letter_grade(0.8) == "B"
    assert letter_grade(0.7) == "C"
    assert letter_grade(0.6) == "D"
    assert letter_grade(0.59) == "F"
    assert letter_grade(0.0) == "F"


def test_grade_order_constant() -> None:
    assert GRADE_ORDER == ("A", "B", "C", "D", "F")


def test_fix_suggestion_is_a_dataclass() -> None:
    suggestion = FixSuggestion(tool="t", problem="p", fix="f", priority=0)
    assert (suggestion.tool, suggestion.problem, suggestion.fix, suggestion.priority) == (
        "t",
        "p",
        "f",
        0,
    )


# -- EvaluationResult.grade ----------------------------------------------


def test_evaluation_result_grade_perfect_is_a() -> None:
    result = evaluate(
        expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
        actual=[{"tool": "get_weather", "args": {"city": "NYC"}}],
    )
    assert result.grade == "A"


def test_evaluation_result_grade_is_a_letter() -> None:
    result = evaluate(
        expected=[{"tool": "a", "args": {}}, {"tool": "b", "args": {}}],
        actual=[{"tool": "c", "args": {}}],
    )
    assert result.grade in GRADE_ORDER


# -- build_eval_fix_list --------------------------------------------------


def test_build_eval_fix_list_empty_on_perfect_match() -> None:
    result = evaluate(
        expected=[{"tool": "a", "args": {"x": 1}}],
        actual=[{"tool": "a", "args": {"x": 1}}],
    )
    assert build_eval_fix_list(result.gold_calls, result.trace_calls) == []


def test_build_eval_fix_list_flags_missing_call() -> None:
    result = evaluate(
        expected=[{"tool": "search", "args": {}}, {"tool": "book", "args": {}}],
        actual=[{"tool": "search", "args": {}}],
    )
    fixes = build_eval_fix_list(result.gold_calls, result.trace_calls)
    assert fixes
    assert all(isinstance(f, FixSuggestion) for f in fixes)
    assert all(f.fix.strip() for f in fixes)
    # The missing `book` call must be surfaced.
    assert any(f.tool == "book" for f in fixes)


def test_build_eval_fix_list_flags_arg_mismatch() -> None:
    result = evaluate(
        expected=[{"tool": "search", "args": {"q": "cats"}}],
        actual=[{"tool": "search", "args": {"q": "dogs"}}],
    )
    fixes = build_eval_fix_list(result.gold_calls, result.trace_calls)
    assert any(f.tool == "search" for f in fixes)
    assert all(f.fix.strip() for f in fixes)


def test_build_eval_fix_list_flags_extra_call() -> None:
    result = evaluate(
        expected=[{"tool": "search", "args": {}}],
        actual=[{"tool": "search", "args": {}}, {"tool": "cancel", "args": {}}],
    )
    fixes = build_eval_fix_list(result.gold_calls, result.trace_calls)
    assert any(f.tool == "cancel" for f in fixes)


def test_build_eval_fix_list_sorted_by_priority() -> None:
    result = evaluate(
        expected=[{"tool": "search", "args": {"q": "cats"}}, {"tool": "book", "args": {}}],
        actual=[{"tool": "search", "args": {"q": "dogs"}}],
    )
    fixes = build_eval_fix_list(result.gold_calls, result.trace_calls)
    priorities = [f.priority for f in fixes]
    assert priorities == sorted(priorities)
