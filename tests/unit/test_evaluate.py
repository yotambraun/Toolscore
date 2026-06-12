"""Tests for the in-memory evaluate() API and EvaluationResult properties."""

import asyncio

import pytest

from toolscore.core import (
    EvaluationResult,
    ToolScoreAssertionError,
    assert_tools,
    evaluate,
    test_agent_async,
)
from toolscore.core import test_agent as run_test_agent


class TestEvaluate:
    """Tests for the evaluate() function."""

    def test_perfect_match(self):
        """Perfect match should score ~1.0."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[{"tool": "search", "args": {"q": "test"}}],
        )
        assert result.score >= 0.99
        assert result.selection_accuracy == 1.0
        assert result.argument_f1 == 1.0
        assert result.sequence_accuracy == 1.0

    def test_tool_name_mismatch(self):
        """Different tool names should lower selection accuracy."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[{"tool": "lookup", "args": {"q": "test"}}],
        )
        assert result.selection_accuracy == 0.0
        assert result.score < 1.0

    def test_argument_mismatch(self):
        """Different args should lower argument F1."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "hello"}}],
            actual=[{"tool": "search", "args": {"q": "world"}}],
        )
        assert result.selection_accuracy == 1.0
        assert result.argument_f1 < 1.0

    def test_multiple_calls(self):
        """Multiple calls should be evaluated correctly."""
        result = evaluate(
            expected=[
                {"tool": "get_weather", "args": {"city": "NYC"}},
                {"tool": "send_email", "args": {"to": "user@example.com"}},
            ],
            actual=[
                {"tool": "get_weather", "args": {"city": "NYC"}},
                {"tool": "send_email", "args": {"to": "user@example.com"}},
            ],
        )
        assert result.score >= 0.99

    def test_empty_calls(self):
        """Empty lists should work."""
        result = evaluate(expected=[], actual=[])
        assert result.selection_accuracy == 1.0

    def test_no_args_omitted_means_dont_check(self):
        """Omitting ``args`` means "do not check arguments" (tool-name-only).

        Under the v1.7 contract a gold call with ``args`` omitted no longer
        scores argument F1 as 0; it is treated as a perfect (vacuous) arg
        match, so a correct tool name yields a perfect composite score.
        """
        result = evaluate(
            expected=[{"tool": "ping"}],
            actual=[{"tool": "ping"}],
        )
        assert result.selection_accuracy == 1.0
        assert result.sequence_accuracy == 1.0
        assert result.argument_f1 == 1.0
        assert result.score == pytest.approx(1.0)

    def test_extra_calls_lower_score(self):
        """Extra actual calls should impact score."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[
                {"tool": "search", "args": {"q": "test"}},
                {"tool": "search", "args": {"q": "test"}},
            ],
        )
        assert result.score < 1.0

    def test_missing_calls_lower_score(self):
        """Missing actual calls should impact score."""
        result = evaluate(
            expected=[
                {"tool": "a", "args": {}},
                {"tool": "b", "args": {}},
            ],
            actual=[{"tool": "a", "args": {}}],
        )
        assert result.score < 1.0

    def test_evaluate_expected_not_list(self):
        """Non-list expected should raise TypeError."""
        with pytest.raises(TypeError, match="expected must be a list"):
            evaluate(expected="not a list", actual=[])  # type: ignore[arg-type]

    def test_evaluate_actual_not_list(self):
        """Non-list actual with unrecognized format should raise TypeError."""
        with pytest.raises(TypeError, match="Cannot auto-detect"):
            evaluate(expected=[], actual="not a list")  # type: ignore[arg-type]

    def test_evaluate_invalid_weight_key(self):
        """Unknown weight key should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown weight keys"):
            evaluate(
                expected=[{"tool": "a"}],
                actual=[{"tool": "a"}],
                weights={"bad_key": 0.5},
            )

    def test_evaluate_negative_weight(self):
        """Negative weight value should raise ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            evaluate(
                expected=[{"tool": "a"}],
                actual=[{"tool": "a"}],
                weights={"selection_accuracy": -0.1},
            )

    def test_invalid_item_missing_tool(self):
        """Item without tool key should raise ValueError."""
        with pytest.raises(ValueError, match="missing 'tool' key"):
            evaluate(expected=[{"args": {"q": "test"}}], actual=[])

    def test_invalid_item_not_dict(self):
        """Non-dict item should raise ValueError."""
        with pytest.raises(ValueError, match="not a dict"):
            evaluate(expected=["not a dict"], actual=[])  # type: ignore[list-item]

    def test_custom_weights(self):
        """Custom weights should affect the composite score.

        Uses a real argument mismatch (argument_f1 < 1.0) so that re-weighting
        argument_f1 to zero is what raises the composite to a perfect score.
        (Under the v1.7 contract, *omitted* args no longer zero out argument_f1,
        so a populated-but-wrong arg is used to create the gap deliberately.)
        """
        # Wrong argument value → argument_f1 < 1.0, so default weights give < 1.0.
        result_default = evaluate(
            expected=[{"tool": "a", "args": {"x": 1}}],
            actual=[{"tool": "a", "args": {"x": 2}}],
        )
        # Weight only selection_accuracy, which is 1.0
        result_custom = evaluate(
            expected=[{"tool": "a", "args": {"x": 1}}],
            actual=[{"tool": "a", "args": {"x": 2}}],
            weights={
                "selection_accuracy": 1.0,
                "argument_f1": 0.0,
                "sequence_accuracy": 0.0,
                "redundant_rate": 0.0,
            },
        )
        assert result_default.score < result_custom.score
        assert result_custom.score == 1.0

    def test_partial_weights_renormalize(self):
        """Partial weights dict is merged with defaults then renormalized."""
        # Provide only selection_accuracy=2.0 — after merging with defaults the
        # total is 2.0+0.3+0.2+0.1=2.6, so selection_accuracy fraction ~0.769.
        # With a perfect match (sel=1, arg=1, seq=1, red=0) the score must be 1.0
        # regardless of the raw weight magnitudes.
        result = evaluate(
            expected=[{"tool": "a", "args": {"x": 1}}],
            actual=[{"tool": "a", "args": {"x": 1}}],
            weights={"selection_accuracy": 2.0},
        )
        assert result.score == pytest.approx(1.0, abs=1e-6)

    def test_all_zero_weights_raise_valueerror(self):
        """Weights that sum to zero after merging should raise ValueError."""
        with pytest.raises(ValueError, match="sum to zero"):
            evaluate(
                expected=[{"tool": "a"}],
                actual=[{"tool": "a"}],
                weights={
                    "selection_accuracy": 0.0,
                    "argument_f1": 0.0,
                    "sequence_accuracy": 0.0,
                    "redundant_rate": 0.0,
                },
            )

    def test_default_weights_unchanged(self):
        """evaluate() without weights uses the default weights unmodified."""
        result_a = evaluate(
            expected=[{"tool": "a"}],
            actual=[{"tool": "a"}],
        )
        result_b = evaluate(
            expected=[{"tool": "a"}],
            actual=[{"tool": "a"}],
            weights={
                "selection_accuracy": 0.4,
                "argument_f1": 0.3,
                "sequence_accuracy": 0.2,
                "redundant_rate": 0.1,
            },
        )
        assert result_a.score == pytest.approx(result_b.score, abs=1e-9)

    def test_metrics_populated(self):
        """evaluate() should populate all core metrics."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[{"tool": "search", "args": {"q": "test"}}],
        )
        assert "invocation_accuracy" in result.metrics
        assert "selection_accuracy" in result.metrics
        assert "argument_metrics" in result.metrics
        assert "sequence_metrics" in result.metrics
        assert "efficiency_metrics" in result.metrics
        assert "tool_correctness_metrics" in result.metrics
        assert "trajectory_metrics" in result.metrics


class TestEvaluationResultProperties:
    """Tests for EvaluationResult convenience properties."""

    def test_score_with_empty_metrics(self):
        """Score with no metrics defaults to 0.1 (redundant_rate inverted)."""
        result = EvaluationResult()
        # With all zeros except redundant_rate weight * (1 - 0) = 0.1
        assert result.score == pytest.approx(0.1)

    def test_selection_accuracy_property(self):
        """selection_accuracy property should read from metrics."""
        result = EvaluationResult()
        result.metrics["selection_accuracy"] = 0.75
        assert result.selection_accuracy == 0.75

    def test_argument_f1_property(self):
        """argument_f1 property should read from nested metrics."""
        result = EvaluationResult()
        result.metrics["argument_metrics"] = {"f1": 0.8, "precision": 0.9, "recall": 0.7}
        assert result.argument_f1 == 0.8

    def test_sequence_accuracy_property(self):
        """sequence_accuracy property should read from nested metrics."""
        result = EvaluationResult()
        result.metrics["sequence_metrics"] = {"sequence_accuracy": 0.6, "edit_distance": 2}
        assert result.sequence_accuracy == 0.6

    def test_to_dict_includes_score(self):
        """to_dict should include the composite score."""
        result = EvaluationResult()
        d = result.to_dict()
        assert "score" in d


class TestAssertTools:
    """Tests for the assert_tools helper."""

    def test_passing_assertion(self):
        """Passing assertion should return result."""
        result = assert_tools(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[{"tool": "search", "args": {"q": "test"}}],
            min_score=0.9,
        )
        assert result.score >= 0.9

    def test_perfect_match_passes_min_score_1(self):
        """A perfect match must satisfy min_score=1.0 despite float noise.

        The composite score sums float-weighted metrics and lands at
        ~0.9999999999999999 for an exact match, so a raw ``< 1.0`` comparison
        would spuriously fail; the threshold tolerates that float noise.
        """
        result = assert_tools(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[{"tool": "search", "args": {"q": "test"}}],
            min_score=1.0,
        )
        assert result.score == pytest.approx(1.0)

    def test_genuine_drift_still_fails_at_min_score_1(self):
        """Float tolerance must not let real drift slip past min_score=1.0."""
        with pytest.raises(ToolScoreAssertionError, match="score"):
            assert_tools(
                expected=[{"tool": "search", "args": {"q": "test"}}],
                actual=[{"tool": "wrong_tool", "args": {"q": "other"}}],
                min_score=1.0,
            )

    def test_failing_assertion(self):
        """Failing assertion should raise ToolScoreAssertionError."""
        with pytest.raises(ToolScoreAssertionError, match="score"):
            assert_tools(
                expected=[{"tool": "search", "args": {"q": "test"}}],
                actual=[{"tool": "wrong_tool", "args": {"q": "other"}}],
                min_score=0.9,
            )

    def test_assert_tools_min_score_too_high(self):
        """min_score above 1.0 should raise ValueError."""
        with pytest.raises(ValueError, match=r"between 0\.0 and 1\.0"):
            assert_tools(
                expected=[{"tool": "a"}],
                actual=[{"tool": "a"}],
                min_score=1.5,
            )

    def test_assert_tools_min_score_negative(self):
        """Negative min_score should raise ValueError."""
        with pytest.raises(ValueError, match=r"between 0\.0 and 1\.0"):
            assert_tools(
                expected=[{"tool": "a"}],
                actual=[{"tool": "a"}],
                min_score=-0.1,
            )

    def test_custom_weights(self):
        """assert_tools should pass weights through to evaluate."""
        # This should pass since we weight only selection_accuracy
        result = assert_tools(
            expected=[{"tool": "search"}],
            actual=[{"tool": "search"}],
            min_score=0.9,
            weights={
                "selection_accuracy": 1.0,
                "argument_f1": 0.0,
                "sequence_accuracy": 0.0,
                "redundant_rate": 0.0,
            },
        )
        assert result.score >= 0.9


class TestEvaluateAutoDetect:
    """Tests for auto-detection in evaluate()."""

    def test_evaluate_auto_detect_openai(self):
        """Raw OpenAI response as actual should auto-detect."""
        openai_response = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"city": "NYC"}',
                                }
                            }
                        ]
                    }
                }
            ]
        }
        result = evaluate(
            expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
            actual=openai_response,
        )
        assert result.score >= 0.99

    def test_evaluate_auto_detect_anthropic(self):
        """Raw Anthropic response as actual should auto-detect."""
        anthropic_response = {
            "content": [
                {
                    "type": "tool_use",
                    "name": "web_search",
                    "input": {"query": "python"},
                }
            ]
        }
        result = evaluate(
            expected=[{"tool": "web_search", "args": {"query": "python"}}],
            actual=anthropic_response,
        )
        assert result.score >= 0.99

    def test_evaluate_auto_detect_claude_agent_sdk_list(self):
        """List-shaped Claude Agent SDK messages auto-detect through evaluate()."""
        messages = [
            {"role": "user", "content": "weather in NYC?"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "get_weather",
                        "input": {"city": "NYC"},
                    }
                ],
            },
        ]
        result = evaluate(
            expected=[{"tool": "get_weather", "args": {"city": "NYC"}}],
            actual=messages,
        )
        assert result.score >= 0.99

    def test_evaluate_auto_detect_bare_langgraph_list(self):
        """A bare [human_msg, ai_msg_with_tool_calls] list auto-detects."""
        messages = [
            {"role": "user", "content": "search please"},
            {
                "role": "assistant",
                "tool_calls": [{"name": "search", "args": {"q": "test"}}],
            },
        ]
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=messages,
        )
        assert result.score >= 0.99

    def test_evaluate_empty_list_passthrough(self):
        """An empty actual list still routes through auto_extract cleanly."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "test"}}],
            actual=[],
        )
        assert result.score < 0.5


class TestTestAgent:
    """Tests for the test_agent() helper."""

    def test_test_agent_basic(self):
        """Agent callable is called, result is evaluated."""

        def mock_agent(prompt):  # type: ignore[no-untyped-def]
            return [{"tool": "search", "args": {"q": prompt}}]

        result = run_test_agent(
            agent=mock_agent,
            input="test",
            expected=[{"tool": "search", "args": {"q": "test"}}],
        )
        assert result.score >= 0.99

    def test_test_agent_min_score_fail(self):
        """Agent below min_score raises ToolScoreAssertionError."""

        def mock_agent(prompt):  # type: ignore[no-untyped-def]
            return [{"tool": "wrong_tool", "args": {}}]

        with pytest.raises(ToolScoreAssertionError, match="score"):
            run_test_agent(
                agent=mock_agent,
                input="test",
                expected=[{"tool": "search", "args": {"q": "test"}}],
                min_score=0.9,
            )

    def test_test_agent_with_auto_detect(self):
        """Agent returning raw OpenAI response works via auto-detect."""

        def mock_openai_agent(prompt):  # type: ignore[no-untyped-def]
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "search",
                                        "arguments": '{"q": "test"}',
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

        result = run_test_agent(
            agent=mock_openai_agent,
            input="test",
            expected=[{"tool": "search", "args": {"q": "test"}}],
        )
        assert result.score >= 0.99

    def test_test_agent_with_claude_agent_sdk_list(self):
        """Agent returning a list-shaped Claude Agent SDK response works."""

        def mock_claude_agent(prompt):  # type: ignore[no-untyped-def]
            return [
                {"role": "user", "content": prompt},
                {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "search", "input": {"q": "test"}}],
                },
            ]

        result = run_test_agent(
            agent=mock_claude_agent,
            input="test",
            expected=[{"tool": "search", "args": {"q": "test"}}],
        )
        assert result.score >= 0.99

    def test_test_agent_validates_min_score_before_invoking(self):
        """An out-of-range min_score is rejected before the agent runs."""
        calls: list[str] = []

        def tracking_agent(prompt):  # type: ignore[no-untyped-def]
            calls.append(prompt)
            return [{"tool": "search", "args": {"q": prompt}}]

        with pytest.raises(ValueError, match="min_score"):
            run_test_agent(
                agent=tracking_agent,
                input="test",
                expected=[{"tool": "search", "args": {"q": "test"}}],
                min_score=1.5,
            )
        assert calls == []

    def test_test_agent_raises_on_async_function(self):
        """test_agent raises TypeError when given an async agent function."""

        async def async_agent(prompt: str) -> list:
            return [{"tool": "search", "args": {"q": prompt}}]

        with pytest.raises(TypeError, match="async"):
            run_test_agent(
                agent=async_agent,
                input="test",
                expected=[{"tool": "search", "args": {"q": "test"}}],
            )

    def test_test_agent_raises_on_awaitable_return(self):
        """test_agent raises TypeError when the agent returns an awaitable."""

        # A function that is NOT a coroutine function but returns a coroutine
        # (edge case: wrapping an async call result manually).
        # We simulate this by having the function return a coroutine object.
        async def _inner(prompt: str) -> list:
            return [{"tool": "x", "args": {}}]

        def sneaky_sync_agent(prompt: str):  # type: ignore[no-untyped-def]
            # Returns a coroutine without being an async def itself
            return _inner(prompt)

        with pytest.raises(TypeError, match="async"):
            run_test_agent(
                agent=sneaky_sync_agent,
                input="test",
                expected=[{"tool": "x", "args": {}}],
            )


class TestTestAgentAsync:
    """Tests for test_agent_async()."""

    def test_async_agent_basic(self):
        """Async agent is awaited and evaluated."""

        async def async_agent(prompt: str) -> list:
            return [{"tool": "search", "args": {"q": prompt}}]

        result = asyncio.run(
            test_agent_async(
                agent=async_agent,
                input="test",
                expected=[{"tool": "search", "args": {"q": "test"}}],
            )
        )
        assert result.score >= 0.99

    def test_sync_agent_through_async(self):
        """Sync agent also works via test_agent_async."""

        def sync_agent(prompt: str) -> list:
            return [{"tool": "search", "args": {"q": prompt}}]

        result = asyncio.run(
            test_agent_async(
                agent=sync_agent,
                input="hello",
                expected=[{"tool": "search", "args": {"q": "hello"}}],
            )
        )
        assert result.score >= 0.99

    def test_async_agent_min_score_fail(self):
        """test_agent_async raises ToolScoreAssertionError when score too low."""

        async def bad_agent(prompt: str) -> list:
            return [{"tool": "wrong_tool", "args": {}}]

        with pytest.raises(ToolScoreAssertionError, match="score"):
            asyncio.run(
                test_agent_async(
                    agent=bad_agent,
                    input="test",
                    expected=[{"tool": "search", "args": {"q": "test"}}],
                    min_score=0.9,
                )
            )

    def test_async_agent_returns_openai_response(self):
        """Async agent returning raw OpenAI response works via auto-detect."""

        async def agent(prompt: str) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "search",
                                        "arguments": '{"q": "test"}',
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

        result = asyncio.run(
            test_agent_async(
                agent=agent,
                input="test",
                expected=[{"tool": "search", "args": {"q": "test"}}],
            )
        )
        assert result.score >= 0.99

    def test_async_agent_validates_min_score_before_invoking(self):
        """An out-of-range min_score is rejected before the async agent runs."""
        calls: list[str] = []

        async def tracking_agent(prompt: str) -> list:
            calls.append(prompt)
            return [{"tool": "search", "args": {"q": prompt}}]

        with pytest.raises(ValueError, match="min_score"):
            asyncio.run(
                test_agent_async(
                    agent=tracking_agent,
                    input="test",
                    expected=[{"tool": "search", "args": {"q": "test"}}],
                    min_score=1.5,
                )
            )
        assert calls == []

    def test_test_agent_async_not_collected_by_pytest(self):
        """test_agent_async has __test__ = False."""
        assert test_agent_async.__test__ is False  # type: ignore[attr-defined]

    def test_test_agent_not_collected_by_pytest(self):
        """test_agent has __test__ = False."""
        assert run_test_agent.__test__ is False  # type: ignore[attr-defined]


class TestNoneArgsContractEvaluate:
    """End-to-end contract matrix for the "omitted gold args = don't check" rule.

    Matrix axes: gold args (omitted / explicit null / {} / populated) by
    actual args (empty / populated).  Verified at the evaluate() level across
    argument_f1, tool_correctness, trajectory and the composite score.
    """

    def test_omitted_gold_args_perfect_against_arg_bearing_actual(self):
        """Gold args omitted → argument_f1 and score perfect despite actual args."""
        result = evaluate(
            expected=[{"tool": "search_flights"}],
            actual=[{"tool": "search_flights", "args": {"origin": "SFO", "dest": "NYC"}}],
        )
        assert result.argument_f1 == 1.0
        assert result.score == pytest.approx(1.0)

    def test_explicit_null_gold_args_behaves_like_omitted(self):
        """Gold "args": null is identical to omitting args (do not check)."""
        result = evaluate(
            expected=[{"tool": "search", "args": None}],
            actual=[{"tool": "search", "args": {"q": "x"}}],
        )
        assert result.argument_f1 == 1.0
        assert result.score == pytest.approx(1.0)

    def test_explicit_empty_gold_args_fails_against_arg_bearing_actual(self):
        """Explicit {} keeps strict "expect zero args" — fails on extra args."""
        result = evaluate(
            expected=[{"tool": "search", "args": {}}],
            actual=[{"tool": "search", "args": {"q": "x"}}],
        )
        assert result.argument_f1 == 0.0

    def test_populated_gold_args_mismatch_still_penalized(self):
        """Populated gold args still checked normally."""
        result = evaluate(
            expected=[{"tool": "search", "args": {"q": "right"}}],
            actual=[{"tool": "search", "args": {"q": "wrong"}}],
        )
        assert result.argument_f1 == 0.0

    def test_omitted_gold_args_against_empty_actual(self):
        """Omitted gold args + empty actual → still a perfect arg match."""
        result = evaluate(
            expected=[{"tool": "ping"}],
            actual=[{"tool": "ping", "args": {}}],
        )
        assert result.argument_f1 == 1.0
        assert result.score == pytest.approx(1.0)

    def test_fluent_hero_case_all_none_args_scores_perfect(self):
        """The fluent-API hero case: `.calls("a").then_calls("b")` against
        arg-bearing actual scores ~1.0."""
        from toolscore import expect

        result = (
            expect(
                [
                    {"tool": "a", "args": {"x": 1}},
                    {"tool": "b", "args": {"y": 2}},
                ]
            )
            .calls("a")
            .then_calls("b")
            .with_score(0.9)
            .run()
        )
        assert result.score >= 0.9

    def test_diff_renders_none_args_as_any_args(self):
        """Diff rendering shows None-args gold as do-not-check and as a match."""
        from toolscore.adapters.base import ToolCall
        from toolscore.diff import build_diff_table

        gold = [ToolCall(tool="search", args=None)]
        trace = [ToolCall(tool="search", args={"q": "x"})]
        table = build_diff_table(gold, trace)

        import io

        from rich.console import Console

        console = Console(file=io.StringIO(), width=120, record=True)
        console.print(table)
        text = console.export_text()
        assert "any args" in text
        # The aligned row is a match (✓), never a mismatch.
        assert "unexpected" not in text

    def test_load_gold_standard_without_args_is_dont_check(self, tmp_path):
        """A gold file omitting "args" loads as do-not-check and scores perfect."""
        import json

        from toolscore.core import load_gold_standard

        gold_file = tmp_path / "gold.json"
        gold_file.write_text(json.dumps([{"tool": "search"}]))

        gold_calls = load_gold_standard(gold_file)
        assert gold_calls[0].args is None

        result = evaluate(
            expected=[
                {"tool": c.tool, **({"args": c.args} if c.args is not None else {})}
                for c in gold_calls
            ],
            actual=[{"tool": "search", "args": {"q": "anything"}}],
        )
        assert result.argument_f1 == 1.0
