"""Identical repeats (same tool, same arguments) are a loop signal distinct from
redundant_rate, which counts calls beyond the gold's per-tool expectation."""

from toolscore import evaluate
from toolscore.adapters.base import ToolCall
from toolscore.metrics.efficiency import calculate_redundant_call_rate


def _calls(*pairs):
    return [ToolCall(tool=t, args=a) for t, a in pairs]


def test_distinct_searches_are_redundant_by_count_but_not_identical():
    gold = _calls(("web_search", None))
    trace = _calls(
        ("web_search", {"q": "a"}), ("web_search", {"q": "b"}), ("web_search", {"q": "c"})
    )
    m = calculate_redundant_call_rate(gold, trace)
    assert m["redundant_count"] == 2  # existing semantics unchanged
    assert m["identical_count"] == 0 and m["identical_rate"] == 0.0


def test_exact_repeats_are_counted_once_per_extra_occurrence():
    trace = _calls(
        ("web_search", {"q": "a", "n": 5}),
        ("web_search", {"n": 5, "q": "a"}),
        ("web_fetch", {"url": "u"}),
        ("web_search", {"q": "a", "n": 5}),
    )
    m = calculate_redundant_call_rate([], trace)
    assert m["identical_count"] == 2  # key order does not matter
    assert m["identical_rate"] == 0.5


def test_empty_and_argumentless_traces():
    assert calculate_redundant_call_rate([], [])["identical_count"] == 0
    m = calculate_redundant_call_rate([], _calls(("ping", None), ("ping", {})))
    assert m["identical_count"] == 1  # None and {} both mean "no arguments" for actual calls


def test_evaluate_exposes_identical_metrics_without_changing_the_score():
    expected = [{"tool": "web_search"}]
    actual = [
        {"tool": "web_search", "args": {"q": "a"}},
        {"tool": "web_search", "args": {"q": "a"}},
    ]
    result = evaluate(expected=expected, actual=actual)
    eff = result.metrics["efficiency_metrics"]
    assert eff["identical_count"] == 1 and eff["identical_rate"] == 0.5
    assert eff["redundant_rate"] == 0.5
