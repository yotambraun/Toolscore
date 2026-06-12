"""Unit tests for metrics calculations."""

from toolscore.adapters.base import ToolCall
from toolscore.metrics import (
    calculate_argument_f1,
    calculate_edit_distance,
    calculate_invocation_accuracy,
    calculate_redundant_call_rate,
    calculate_selection_accuracy,
    calculate_trajectory_accuracy,
)
from toolscore.metrics.arguments import _compare_values
from toolscore.metrics.tool_correctness import calculate_tool_correctness_with_args


class TestInvocationAccuracy:
    """Tests for invocation accuracy metric."""

    def test_perfect_match(self) -> None:
        """Test perfect invocation accuracy."""
        gold = [ToolCall(tool="tool1"), ToolCall(tool="tool2")]
        trace = [ToolCall(tool="tool1"), ToolCall(tool="tool2")]

        accuracy = calculate_invocation_accuracy(gold, trace)
        assert accuracy == 1.0

    def test_no_tools_used(self) -> None:
        """Test when no tools are expected or used."""
        accuracy = calculate_invocation_accuracy([], [])
        assert accuracy == 1.0

    def test_missing_invocations(self) -> None:
        """Test when expected tools are missing."""
        gold = [ToolCall(tool="tool1"), ToolCall(tool="tool2")]
        trace = [ToolCall(tool="tool1")]

        accuracy = calculate_invocation_accuracy(gold, trace)
        assert accuracy < 1.0


class TestSelectionAccuracy:
    """Tests for selection accuracy metric."""

    def test_perfect_selection(self) -> None:
        """Test perfect tool selection."""
        gold = [ToolCall(tool="tool1")]
        trace = [ToolCall(tool="tool1")]

        accuracy = calculate_selection_accuracy(gold, trace)
        assert accuracy == 1.0

    def test_wrong_tools(self) -> None:
        """Test when wrong tools are selected."""
        gold = [ToolCall(tool="tool1")]
        trace = [ToolCall(tool="tool2")]

        accuracy = calculate_selection_accuracy(gold, trace)
        assert accuracy == 0.0


class TestEditDistance:
    """Tests for sequence edit distance metric."""

    def test_perfect_sequence(self) -> None:
        """Test perfect sequence match."""
        gold = [ToolCall(tool="A"), ToolCall(tool="B"), ToolCall(tool="C")]
        trace = [ToolCall(tool="A"), ToolCall(tool="B"), ToolCall(tool="C")]

        result = calculate_edit_distance(gold, trace)
        assert result["edit_distance"] == 0
        assert result["sequence_accuracy"] == 1.0

    def test_different_order(self) -> None:
        """Test different order."""
        gold = [ToolCall(tool="A"), ToolCall(tool="B"), ToolCall(tool="C")]
        trace = [ToolCall(tool="B"), ToolCall(tool="A"), ToolCall(tool="C")]

        result = calculate_edit_distance(gold, trace)
        assert result["edit_distance"] > 0
        assert result["sequence_accuracy"] < 1.0


class TestArgumentF1:
    """Tests for argument F1 score metric."""

    def test_perfect_arguments(self) -> None:
        """Test perfect argument match."""
        gold = [ToolCall(tool="tool1", args={"x": 1, "y": 2})]
        trace = [ToolCall(tool="tool1", args={"x": 1, "y": 2})]

        result = calculate_argument_f1(gold, trace)
        assert result["f1"] == 1.0

    def test_missing_arguments(self) -> None:
        """Test missing arguments."""
        gold = [ToolCall(tool="tool1", args={"x": 1, "y": 2})]
        trace = [ToolCall(tool="tool1", args={"x": 1})]

        result = calculate_argument_f1(gold, trace)
        assert result["f1"] < 1.0


class TestStrictArgumentComparison:
    """Tests for strict=True in _compare_values and calculate_argument_f1."""

    # --- _compare_values unit tests ---

    def test_int_float_lenient_by_default(self) -> None:
        """Default (strict=False) treats int 1 == float 1.0."""
        assert _compare_values(1, 1.0) is True

    def test_int_float_strict_not_equal(self) -> None:
        """strict=True: int 1 != float 1.0 (different types)."""
        assert _compare_values(1, 1.0, strict=True) is False

    def test_string_strip_lenient_by_default(self) -> None:
        """Default (strict=False) strips whitespace from strings."""
        assert _compare_values("a ", "a") is True

    def test_string_strip_strict_not_equal(self) -> None:
        """strict=True: 'a ' != 'a' (no stripping)."""
        assert _compare_values("a ", "a", strict=True) is False

    def test_equal_values_always_match(self) -> None:
        """Identical values match in both modes."""
        assert _compare_values("hello", "hello", strict=True) is True
        assert _compare_values(42, 42, strict=True) is True

    # --- calculate_argument_f1 with strict ---

    def test_argument_f1_strict_int_float_mismatch(self) -> None:
        """calculate_argument_f1 strict=True: int vs float counts as wrong."""
        gold = [ToolCall(tool="t", args={"x": 1})]
        trace = [ToolCall(tool="t", args={"x": 1.0})]

        lenient = calculate_argument_f1(gold, trace, strict=False)
        strict = calculate_argument_f1(gold, trace, strict=True)

        assert lenient["f1"] == 1.0
        assert strict["f1"] < 1.0

    def test_argument_f1_strict_string_strip_mismatch(self) -> None:
        """calculate_argument_f1 strict=True: trailing space counts as wrong."""
        gold = [ToolCall(tool="t", args={"q": "hello "})]
        trace = [ToolCall(tool="t", args={"q": "hello"})]

        lenient = calculate_argument_f1(gold, trace, strict=False)
        strict = calculate_argument_f1(gold, trace, strict=True)

        assert lenient["f1"] == 1.0
        assert strict["f1"] < 1.0

    # --- evaluate() with strict ---

    def test_evaluate_strict_via_core(self) -> None:
        """evaluate(strict=True) propagates to argument comparison."""
        from toolscore.core import evaluate

        result_lenient = evaluate(
            expected=[{"tool": "t", "args": {"x": 1}}],
            actual=[{"tool": "t", "args": {"x": 1.0}}],
            strict=False,
        )
        result_strict = evaluate(
            expected=[{"tool": "t", "args": {"x": 1}}],
            actual=[{"tool": "t", "args": {"x": 1.0}}],
            strict=True,
        )
        assert result_lenient.argument_f1 == 1.0
        assert result_strict.argument_f1 < 1.0


class TestStrictNestedComparison:
    """Tests for strict recursive comparison of nested structures."""

    # --- nested dict int vs float ---

    def test_nested_dict_int_float_strict_mismatch(self) -> None:
        """strict=True: nested dict {n: 1} vs {n: 1.0} must NOT match."""
        assert _compare_values({"n": 1}, {"n": 1.0}, strict=True) is False

    def test_nested_dict_int_float_lenient_match(self) -> None:
        """strict=False: nested dict {n: 1} vs {n: 1.0} MUST match."""
        assert _compare_values({"n": 1}, {"n": 1.0}, strict=False) is True

    # --- nested dict bool vs int ---

    def test_nested_dict_bool_int_strict_mismatch(self) -> None:
        """strict=True: nested {flag: True} vs {flag: 1} must NOT match (bool != int)."""
        assert _compare_values({"flag": True}, {"flag": 1}, strict=True) is False

    def test_nested_dict_bool_int_lenient_match(self) -> None:
        """strict=False: {flag: True} vs {flag: 1} matches because True == 1."""
        assert _compare_values({"flag": True}, {"flag": 1}, strict=False) is True

    # --- nested list int vs float ---

    def test_nested_list_int_float_strict_mismatch(self) -> None:
        """strict=True: [1, 2] vs [1.0, 2.0] must NOT match."""
        assert _compare_values([1, 2], [1.0, 2.0], strict=True) is False

    def test_nested_list_int_float_lenient_match(self) -> None:
        """strict=False: [1, 2] vs [1.0, 2.0] MUST match."""
        assert _compare_values([1, 2], [1.0, 2.0], strict=False) is True

    # --- deeply nested list ---

    def test_deeply_nested_list_strict_mismatch(self) -> None:
        """strict=True: deeply nested list with int vs float must NOT match."""
        assert _compare_values([[1, 2], [3]], [[1.0, 2.0], [3]], strict=True) is False

    def test_deeply_nested_list_lenient_match(self) -> None:
        """strict=False: deeply nested list with int vs float MUST match."""
        assert _compare_values([[1, 2], [3]], [[1.0, 2.0], [3]], strict=False) is True

    # --- type mismatch list vs tuple ---

    def test_list_vs_tuple_strict_mismatch(self) -> None:
        """strict=True: list [1, 2] vs tuple (1, 2) must NOT match."""
        assert _compare_values([1, 2], (1, 2), strict=True) is False

    def test_list_vs_tuple_lenient_no_match(self) -> None:
        """strict=False: list [1, 2] vs tuple (1, 2) — not equal by default (different containers)."""
        assert _compare_values([1, 2], (1, 2), strict=False) is False

    # --- dict key set mismatch ---

    def test_nested_dict_extra_key_strict_mismatch(self) -> None:
        """strict=True: dicts with different key sets must NOT match."""
        assert _compare_values({"a": 1}, {"a": 1, "b": 2}, strict=True) is False

    def test_nested_list_length_mismatch_strict(self) -> None:
        """strict=True: lists of different lengths must NOT match."""
        assert _compare_values([1, 2], [1, 2, 3], strict=True) is False


class TestRedundantCallRate:
    """Tests for redundant call rate metric."""

    def test_no_redundant_calls(self) -> None:
        """Test when no redundant calls are made."""
        gold = [ToolCall(tool="tool1")]
        trace = [ToolCall(tool="tool1")]

        result = calculate_redundant_call_rate(gold, trace)
        assert result["redundant_rate"] == 0.0

    def test_extra_calls(self) -> None:
        """Test when extra calls are made."""
        gold = [ToolCall(tool="tool1")]
        trace = [
            ToolCall(tool="tool1"),
            ToolCall(tool="tool2"),
            ToolCall(tool="tool3"),
        ]

        result = calculate_redundant_call_rate(gold, trace)
        assert result["redundant_count"] == 2
        assert result["redundant_rate"] > 0.0


class TestNoneArgsContract:
    """The v1.7 "omitted gold args = do not check arguments" contract.

    Gold ``args is None`` (args omitted) → skip argument checking for that call.
    Gold ``args == {}`` (explicit) → expect the tool called with zero arguments.
    Trace-side args are unaffected (their args are facts, not expectations).
    """

    def test_argument_f1_none_gold_against_arg_bearing_actual_is_perfect(self) -> None:
        """None gold args + arg-bearing actual → f1 == 1.0 (do not check)."""
        gold = [ToolCall(tool="t", args=None)]
        trace = [ToolCall(tool="t", args={"x": 1})]
        result = calculate_argument_f1(gold, trace)
        assert result["f1"] == 1.0
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0

    def test_argument_f1_all_none_gold_is_perfect(self) -> None:
        """An all-None gold set must yield f1 == 1.0, not 0/0 -> 0."""
        gold = [ToolCall(tool="a", args=None), ToolCall(tool="b", args=None)]
        trace = [ToolCall(tool="a", args={"q": 1}), ToolCall(tool="b")]
        result = calculate_argument_f1(gold, trace)
        assert result["f1"] == 1.0

    def test_argument_f1_explicit_empty_gold_still_strict(self) -> None:
        """Explicit {} gold against arg-bearing actual still fails (f1 == 0)."""
        gold = [ToolCall(tool="t", args={})]
        trace = [ToolCall(tool="t", args={"x": 1})]
        result = calculate_argument_f1(gold, trace)
        assert result["f1"] == 0.0

    def test_argument_f1_mixed_none_and_checked(self) -> None:
        """A None gold call must not drag down a sibling checked call."""
        gold = [
            ToolCall(tool="a", args=None),
            ToolCall(tool="b", args={"x": 1}),
        ]
        trace = [
            ToolCall(tool="a", args={"noise": 99}),
            ToolCall(tool="b", args={"x": 1}),
        ]
        result = calculate_argument_f1(gold, trace)
        # Only "b" is scored, and it matches perfectly.
        assert result["f1"] == 1.0

    def test_tool_correctness_with_args_none_gold_matches_on_name(self) -> None:
        """None gold args → tool-name match suffices for the strict variant."""
        gold = [ToolCall(tool="search", args=None)]
        trace = [ToolCall(tool="search", args={"q": "anything"})]
        result = calculate_tool_correctness_with_args(gold, trace)
        assert result["tool_correctness_strict"] == 1.0

    def test_tool_correctness_with_args_explicit_empty_still_strict(self) -> None:
        """Explicit {} gold still requires exact arg equality."""
        gold = [ToolCall(tool="search", args={})]
        trace = [ToolCall(tool="search", args={"q": "x"})]
        result = calculate_tool_correctness_with_args(gold, trace)
        assert result["tool_correctness_strict"] == 0.0

    def test_trajectory_none_gold_matches_on_name(self) -> None:
        """Trajectory step with None gold args matches on tool name only."""
        gold = [ToolCall(tool="a", args=None), ToolCall(tool="b", args=None)]
        trace = [ToolCall(tool="a", args={"x": 1}), ToolCall(tool="b", args={"y": 2})]
        result = calculate_trajectory_accuracy(gold, trace)
        assert result["trajectory_accuracy"] == 1.0
        assert result["step_match_rate"] == 1.0

    def test_matchers_in_populated_gold_still_work(self) -> None:
        """A populated gold dict containing matchers is unaffected by the
        None-check (which only short-circuits when args IS None)."""
        from toolscore.matchers import ANY

        gold = [ToolCall(tool="t", args={"x": ANY})]
        trace = [ToolCall(tool="t", args={"x": 12345})]
        result = calculate_argument_f1(gold, trace)
        assert result["f1"] == 1.0


class TestZeroArgsVacuousMatch:
    """'Expect zero args' met with zero args is a perfect match, not 0/0 -> 0."""

    def test_empty_vs_empty_is_perfect(self) -> None:
        gold = [ToolCall(tool="get_time", args={})]
        trace = [ToolCall(tool="get_time", args={})]
        result = calculate_argument_f1(gold, trace)
        assert result["f1"] == 1.0
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0

    def test_empty_vs_populated_still_fails(self) -> None:
        gold = [ToolCall(tool="get_time", args={})]
        trace = [ToolCall(tool="get_time", args={"tz": "UTC"})]
        result = calculate_argument_f1(gold, trace)
        assert result["f1"] == 0.0

    def test_composite_score_for_correct_no_arg_tool(self) -> None:
        from toolscore import evaluate

        result = evaluate(
            [{"tool": "get_time", "args": {}}],
            [{"tool": "get_time", "args": {}}],
        )
        assert result.argument_f1 == 1.0
        assert result.score > 0.99

    def test_mixed_empty_and_concrete_args(self) -> None:
        gold = [
            ToolCall(tool="get_time", args={}),
            ToolCall(tool="search", args={"q": "x"}),
        ]
        trace = [
            ToolCall(tool="get_time", args={}),
            ToolCall(tool="search", args={"q": "x"}),
        ]
        result = calculate_argument_f1(gold, trace)
        assert result["f1"] == 1.0
