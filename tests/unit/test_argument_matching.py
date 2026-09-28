"""Argument F1 pairs each expected call with the best-matching actual call of the
same tool, using each actual call at most once. Order is the sequence metric's
concern and extra calls are the redundancy metric's concern, so neither should
zero out the argument credit of calls the agent got right."""

import pytest

from toolscore import evaluate


def f1(expected, actual):
    return evaluate(expected=expected, actual=actual).argument_f1


def test_missing_earlier_call_does_not_hide_a_correct_later_call():
    expected = [
        {"tool": "web_search", "args": {"q": "x"}},
        {"tool": "web_fetch", "args": {"url": "u"}},
    ]
    actual = [{"tool": "web_fetch", "args": {"url": "u"}}]
    assert f1(expected, actual) == pytest.approx(2 / 3)  # precision 1/1, recall 1/2


def test_reordered_calls_to_the_same_tool_keep_full_argument_credit():
    expected = [{"tool": "search", "args": {"q": "a"}}, {"tool": "search", "args": {"q": "b"}}]
    actual = [{"tool": "search", "args": {"q": "b"}}, {"tool": "search", "args": {"q": "a"}}]
    assert f1(expected, actual) == 1.0


def test_a_wrong_attempt_before_the_right_call_is_not_matched_instead_of_it():
    expected = [{"tool": "get_weather", "args": {"city": "Paris"}}]
    actual = [
        {"tool": "get_weather", "args": {"city": "Pari"}},
        {"tool": "get_weather", "args": {"city": "Paris"}},
    ]
    assert f1(expected, actual) == 1.0


def test_each_actual_call_is_used_at_most_once():
    expected = [{"tool": "search", "args": {"q": "a"}}, {"tool": "search", "args": {"q": "a"}}]
    actual = [{"tool": "search", "args": {"q": "a"}}]
    assert f1(expected, actual) == pytest.approx(2 / 3)  # one of two expected calls matched


def test_best_assignment_not_greedy_first_fit():
    expected = [{"tool": "t", "args": {"a": 1, "b": 2}}, {"tool": "t", "args": {"a": 1, "b": 9}}]
    actual = [{"tool": "t", "args": {"a": 1, "b": 9}}, {"tool": "t", "args": {"a": 1, "b": 2}}]
    assert f1(expected, actual) == 1.0


def test_correctly_calling_no_tools_is_a_perfect_argument_score():
    result = evaluate(expected=[], actual=[])
    assert result.argument_f1 == 1.0 and result.score == pytest.approx(1.0)


def test_unexpected_calls_when_none_expected_still_score_zero_arguments():
    assert f1([], [{"tool": "delete", "args": {"id": 1}}]) == 0.0
