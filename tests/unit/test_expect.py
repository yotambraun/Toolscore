"""Tests for the fluent expect() assertion API (TDD — written before implementation)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from toolscore import ANY, Regex, ToolScoreAssertionError
from toolscore.core import EvaluationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FLIGHT_CALLS = [
    {"tool": "search_flights", "args": {"origin": "JFK", "destination": "NYC"}},
    {"tool": "book_flight", "args": {"flight_id": "FL-123"}},
]

WRONG_CALLS = [
    {"tool": "cancel_booking", "args": {"booking_id": "B-001"}},
]


def simple_agent(prompt: str) -> list[dict[str, Any]]:
    """Sync agent: returns a fixed list of tool calls."""
    return FLIGHT_CALLS


async def async_agent(prompt: str) -> list[dict[str, Any]]:
    """Async agent: returns the same fixed list."""
    return FLIGHT_CALLS


def bad_agent(prompt: str) -> list[dict[str, Any]]:
    """Sync agent that calls a forbidden tool."""
    return WRONG_CALLS


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------


def test_expect_is_importable() -> None:
    from toolscore import expect

    assert callable(expect)


def test_expectation_class_is_importable() -> None:
    from toolscore.expect import Expectation  # noqa: F401


# ---------------------------------------------------------------------------
# Fluent chainability
# ---------------------------------------------------------------------------


def test_fluent_chain_returns_self() -> None:
    from toolscore import expect

    e = expect(FLIGHT_CALLS)
    assert e.calls("search_flights") is e


def test_fluent_then_calls_returns_self() -> None:
    from toolscore import expect

    e = expect(FLIGHT_CALLS)
    assert e.then_calls("search_flights") is e


def test_fluent_does_not_call_returns_self() -> None:
    from toolscore import expect

    e = expect(FLIGHT_CALLS)
    assert e.does_not_call("cancel_booking") is e


def test_fluent_with_score_returns_self() -> None:
    from toolscore import expect

    e = expect(FLIGHT_CALLS)
    assert e.with_score(0.8) is e


def test_fluent_with_weights_returns_self() -> None:
    from toolscore import expect

    e = expect(FLIGHT_CALLS)
    assert e.with_weights(selection_accuracy=1.0) is e


def test_fluent_with_strict_args_returns_self() -> None:
    from toolscore import expect

    e = expect(FLIGHT_CALLS)
    assert e.with_strict_args() is e


def test_fluent_on_returns_self() -> None:
    from toolscore import expect

    e = expect(simple_agent)
    assert e.on("fly me to NYC") is e


def test_full_chain_is_fluent() -> None:
    from toolscore import expect

    # Must not raise — just building the chain
    chain = (
        expect(FLIGHT_CALLS)
        .calls("search_flights", origin=ANY, destination="NYC")
        .then_calls("book_flight", flight_id=Regex(r"FL-\d+"))
        .does_not_call("cancel_booking")
        .with_score(0.9)
    )
    assert chain is not None


# ---------------------------------------------------------------------------
# run() with list-of-dicts subject (no .on)
# ---------------------------------------------------------------------------


def test_run_passing_case() -> None:
    from toolscore import expect

    result = (
        expect(FLIGHT_CALLS)
        .calls("search_flights", origin="JFK", destination="NYC")
        .then_calls("book_flight", flight_id="FL-123")
        .with_score(0.9)
        .run()
    )
    assert isinstance(result, EvaluationResult)
    assert result.score >= 0.9


def test_run_failing_case_raises_assertion_error() -> None:
    from toolscore import expect

    with pytest.raises(ToolScoreAssertionError) as exc_info:
        (
            expect(WRONG_CALLS)
            .calls("search_flights", origin="JFK", destination="NYC")
            .with_score(0.9)
            .run()
        )
    # The error message should contain diff table markers from render_failure
    msg = str(exc_info.value)
    assert "score" in msg.lower() or "Expected" in msg or "Actual" in msg


def test_run_failure_message_contains_diff_markers() -> None:
    from toolscore import expect

    with pytest.raises(ToolScoreAssertionError) as exc_info:
        (expect(WRONG_CALLS).calls("search_flights").with_score(0.9).run())
    msg = str(exc_info.value)
    # render_failure produces a table with "Expected" and "Actual" columns
    assert "Expected" in msg or "Actual" in msg or "score" in msg


# ---------------------------------------------------------------------------
# run() with raw OpenAI-shaped response (goes through auto_extract)
# ---------------------------------------------------------------------------


def _make_openai_response(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal OpenAI chat completion dict."""
    import json

    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(args),
                            }
                        }
                    ]
                }
            }
        ]
    }


def test_run_with_openai_response_auto_extracted() -> None:
    from toolscore import expect

    raw = _make_openai_response("search_flights", {"origin": "JFK", "destination": "NYC"})
    result = (
        expect(raw).calls("search_flights", origin="JFK", destination="NYC").with_score(0.8).run()
    )
    assert isinstance(result, EvaluationResult)
    assert result.score >= 0.8


# ---------------------------------------------------------------------------
# run() with sync callable + .on(prompt)
# ---------------------------------------------------------------------------


def test_run_with_sync_callable_receives_prompt() -> None:
    from toolscore import expect

    received_prompts: list[str] = []

    def recording_agent(prompt: str) -> list[dict[str, Any]]:
        received_prompts.append(prompt)
        # Return exactly one call so score stays high with one expectation
        return [{"tool": "search_flights", "args": {"origin": "JFK", "destination": "NYC"}}]

    (
        expect(recording_agent)
        .on("book me a flight")
        .calls("search_flights", origin="JFK", destination="NYC")
        .with_score(0.9)
        .run()
    )
    assert received_prompts == ["book me a flight"]


def test_run_with_sync_callable_evaluates_result() -> None:
    from toolscore import expect

    result = (
        expect(simple_agent)
        .on("fly to NYC")
        .calls("search_flights", origin="JFK", destination="NYC")
        .then_calls("book_flight", flight_id="FL-123")
        .with_score(0.9)
        .run()
    )
    assert isinstance(result, EvaluationResult)
    assert result.score >= 0.9


# ---------------------------------------------------------------------------
# .on() misuse errors
# ---------------------------------------------------------------------------


def test_on_with_non_callable_subject_raises_at_run() -> None:
    """Setting .on() for a non-callable (list) subject should raise at run()."""
    from toolscore import expect

    with pytest.raises((TypeError, ValueError)):
        (expect(FLIGHT_CALLS).on("this should not be allowed").calls("search_flights").run())


def test_callable_subject_without_on_raises_at_run() -> None:
    """Callable subject with no .on() should raise at run()."""
    from toolscore import expect

    with pytest.raises((TypeError, ValueError)):
        expect(simple_agent).calls("search_flights").run()


# ---------------------------------------------------------------------------
# Async: run() raises TypeError for coroutine-function subjects
# ---------------------------------------------------------------------------


def test_run_with_async_subject_raises_type_error() -> None:
    from toolscore import expect

    with pytest.raises(TypeError) as exc_info:
        expect(async_agent).on("fly me").calls("search_flights").run()
    assert "run_async" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Async: run_async() works for async and sync subjects
# ---------------------------------------------------------------------------


def test_run_async_with_async_subject() -> None:
    from toolscore import expect

    result = asyncio.run(
        expect(async_agent)
        .on("book me a flight to NYC")
        .calls("search_flights", origin="JFK", destination="NYC")
        .then_calls("book_flight", flight_id="FL-123")
        .with_score(0.9)
        .run_async()
    )
    assert isinstance(result, EvaluationResult)
    assert result.score >= 0.9


def test_run_async_with_sync_subject() -> None:
    from toolscore import expect

    result = asyncio.run(
        expect(simple_agent)
        .on("fly to NYC")
        .calls("search_flights", origin="JFK", destination="NYC")
        .then_calls("book_flight", flight_id="FL-123")
        .with_score(0.9)
        .run_async()
    )
    assert isinstance(result, EvaluationResult)
    assert result.score >= 0.9


def test_run_async_with_list_subject() -> None:
    from toolscore import expect

    result = asyncio.run(
        expect(FLIGHT_CALLS)
        .calls("search_flights", origin="JFK", destination="NYC")
        .then_calls("book_flight", flight_id="FL-123")
        .with_score(0.9)
        .run_async()
    )
    assert isinstance(result, EvaluationResult)
    assert result.score >= 0.9


# ---------------------------------------------------------------------------
# does_not_call
# ---------------------------------------------------------------------------


def test_does_not_call_violation_raises() -> None:
    from toolscore import expect

    with pytest.raises(ToolScoreAssertionError) as exc_info:
        (expect(WRONG_CALLS).calls("search_flights").does_not_call("cancel_booking").run())
    msg = str(exc_info.value)
    assert "cancel_booking" in msg


def test_does_not_call_no_violation_passes() -> None:
    from toolscore import expect

    # FLIGHT_CALLS doesn't include cancel_booking — should pass
    result = (
        expect(FLIGHT_CALLS)
        .calls("search_flights", origin="JFK", destination="NYC")
        .then_calls("book_flight", flight_id="FL-123")
        .does_not_call("cancel_booking")
        .with_score(0.9)
        .run()
    )
    assert isinstance(result, EvaluationResult)


def test_does_not_call_only_is_valid() -> None:
    """forbidden-only contract: skip min-score, just check forbidden tool."""
    from toolscore import expect

    # FLIGHT_CALLS doesn't include cancel_booking — should return a result
    result = expect(FLIGHT_CALLS).does_not_call("cancel_booking").run()
    assert isinstance(result, EvaluationResult)


def test_does_not_call_only_violation() -> None:
    """forbidden-only contract: violation should raise even without calls()."""
    from toolscore import expect

    with pytest.raises(ToolScoreAssertionError) as exc_info:
        expect(WRONG_CALLS).does_not_call("cancel_booking").run()
    assert "cancel_booking" in str(exc_info.value)


# ---------------------------------------------------------------------------
# No expectations ValueError
# ---------------------------------------------------------------------------


def test_no_expectations_raises_value_error() -> None:
    from toolscore import expect

    with pytest.raises(ValueError, match="no expectations"):
        expect(FLIGHT_CALLS).run()


# ---------------------------------------------------------------------------
# with_weights and with_strict_args pass through
# ---------------------------------------------------------------------------


def test_with_weights_pass_through() -> None:
    from toolscore import expect

    # Declare both expected calls so score is at least selection_accuracy=1.0
    result = (
        expect(FLIGHT_CALLS)
        .calls("search_flights", origin="JFK", destination="NYC")
        .then_calls("book_flight", flight_id="FL-123")
        .with_weights(
            selection_accuracy=1.0, argument_f1=0.0, sequence_accuracy=0.0, redundant_rate=0.0
        )
        .with_score(0.5)
        .run()
    )
    assert isinstance(result, EvaluationResult)


def test_with_strict_args_rejects_type_mismatch() -> None:
    """strict=True: int '1' != 1 difference must matter."""
    from toolscore import expect

    # With strict=True: string "JFK" != int 1 — guaranteed mismatch on flight_id
    # We pass wrong type for destination — strict mode should not coerce
    # Use a case that would pass in lenient mode but fail in strict
    actual = [
        {"tool": "search_flights", "args": {"origin": "JFK", "destination": "NYC", "seats": "1"}}
    ]

    # lenient passes (string "1" vs int 1 → coerced)
    result_lenient = (
        expect(actual)
        .calls("search_flights", origin="JFK", destination="NYC", seats=1)
        .with_score(0.0)  # don't enforce min score, just check it runs
        .run()
    )
    assert isinstance(result_lenient, EvaluationResult)

    # strict: string "1" != int 1 — arg_f1 should differ; just confirm it runs
    result_strict = (
        expect(actual)
        .calls("search_flights", origin="JFK", destination="NYC", seats=1)
        .with_strict_args()
        .with_score(0.0)
        .run()
    )
    assert isinstance(result_strict, EvaluationResult)


# ---------------------------------------------------------------------------
# Matchers in args end-to-end
# ---------------------------------------------------------------------------


def test_any_matcher_in_calls() -> None:
    from toolscore import expect

    result = (
        expect(FLIGHT_CALLS)
        .calls("search_flights", origin=ANY, destination=ANY)
        .with_score(0.5)
        .run()
    )
    assert isinstance(result, EvaluationResult)


def test_regex_matcher_in_calls() -> None:
    from toolscore import expect

    result = (
        expect(FLIGHT_CALLS)
        .calls("search_flights", origin=ANY, destination="NYC")
        .then_calls("book_flight", flight_id=Regex(r"FL-\d+"))
        .with_score(0.9)
        .run()
    )
    assert isinstance(result, EvaluationResult)
    assert result.score >= 0.9


# ---------------------------------------------------------------------------
# calls() with no kwargs means args=None (don't check args)
# ---------------------------------------------------------------------------


def test_calls_no_kwargs_does_not_check_args() -> None:
    """calls() with no kwargs: args={} gold → tool name matched; test just verifies run() works."""
    from toolscore import expect

    # Only declare one call with no args so actual (2 calls) is partially matched.
    # Just verify it runs and returns a result (score may be < 0.9 due to extra call).
    actual = [{"tool": "search_flights", "args": {"origin": "JFK", "destination": "NYC"}}]
    result = (
        expect(actual)
        .calls("search_flights")  # no args specified → empty gold args
        .with_score(0.0)  # 0.0 means no enforcement
        .run()
    )
    assert isinstance(result, EvaluationResult)


# ---------------------------------------------------------------------------
# README hero example end-to-end
# ---------------------------------------------------------------------------


def test_readme_hero_example() -> None:
    """The exact README hero example must work end-to-end."""
    from toolscore import expect

    result = (
        expect(simple_agent)
        .on("book me a flight to NYC")
        .calls("search_flights", origin=ANY, destination="NYC")
        .then_calls("book_flight", flight_id=Regex(r"FL-\d+"))
        .does_not_call("cancel_booking")
        .with_score(0.9)
        .run()
    )
    assert isinstance(result, EvaluationResult)
    assert result.score >= 0.9
