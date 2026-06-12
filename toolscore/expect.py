"""Fluent ``expect()`` assertion API for Toolscore.

Provides a readable, chainable interface for asserting on tool-call behavior::

    from toolscore import expect, ANY, Regex

    expect(agent).on("book me a flight to NYC") \\
        .calls("search_flights", origin=ANY, destination="NYC") \\
        .then_calls("book_flight", flight_id=Regex(r"FL-\\d+")) \\
        .does_not_call("cancel_booking") \\
        .with_score(0.9) \\
        .run()

The subject passed to :func:`expect` may be:

* An **agent callable** (sync or async) — pair with ``.on(prompt)`` before calling
  ``.run()`` / ``.run_async()``.
* An **already-produced result** — a raw provider/framework response or a list of
  call dicts.  Do **not** call ``.on()`` in this case.
"""

from __future__ import annotations

import inspect
from typing import Any

from toolscore.core import EvaluationResult, ToolScoreAssertionError, _check_min_score, evaluate
from toolscore.integrations import auto_extract


class Expectation:
    """Fluent builder for tool-call assertions.

    Do not instantiate directly — use :func:`expect` instead.
    """

    def __init__(self, subject: Any) -> None:
        self._subject = subject
        self._prompt: str | None = None
        self._expected: list[dict[str, Any]] = []
        self._forbidden: list[str] = []
        self._min_score: float = 0.9
        self._weights: dict[str, float] | None = None
        self._strict: bool = False
        self._has_calls: bool = False
        self._has_forbidden: bool = False

    # ------------------------------------------------------------------
    # Chain builders
    # ------------------------------------------------------------------

    def on(self, prompt: str) -> Expectation:
        """Set the input prompt for a callable subject.

        Args:
            prompt: The string to pass to the agent callable.

        Returns:
            ``self`` for chaining.
        """
        self._prompt = prompt
        return self

    def calls(self, tool: str, **args: Any) -> Expectation:
        """Append an expected tool call.

        Calling with **no keyword arguments** — ``calls("tool")`` — means *do
        not check arguments*: the tool name must be called, but whatever
        arguments the agent passed are accepted (equivalent to using
        :data:`toolscore.ANY` for every argument).  This is the common case and
        keeps casual assertions from failing just because the agent supplied
        arguments.

        Calling **with** keyword arguments — ``calls("tool", q="x")`` — checks
        those arguments.  Use :data:`toolscore.ANY`, :class:`toolscore.Regex`,
        etc. as values for individual arguments when you want flexible matching.

        Note:
            There is intentionally no fluent way to assert "the tool was called
            with *exactly zero* arguments", because ``calls("tool", **{})`` is
            indistinguishable in Python from ``calls("tool")``.  For that rare
            expectation, use :func:`toolscore.evaluate` directly with an
            explicit empty dict::

                evaluate([{"tool": "t", "args": {}}], actual)

        Args:
            tool: Expected tool name.
            **args: Expected argument key/value pairs (may contain
                :class:`~toolscore.matchers.Matcher` instances).  Omit entirely
                to skip argument checking.

        Returns:
            ``self`` for chaining.
        """
        entry: dict[str, Any] = {"tool": tool}
        # No kwargs → omit "args" so the gold ToolCall keeps args=None ("do not
        # check arguments").  With kwargs → store them for checking.
        if args:
            entry["args"] = dict(args)
        self._expected.append(entry)
        self._has_calls = True
        return self

    def then_calls(self, tool: str, **args: Any) -> Expectation:
        """Alias for :meth:`calls`; reads naturally in sequences.

        Args:
            tool: Expected tool name.
            **args: Expected argument key/value pairs.

        Returns:
            ``self`` for chaining.
        """
        return self.calls(tool, **args)

    def does_not_call(self, tool: str) -> Expectation:
        """Assert that the agent must NOT call *tool*.

        Args:
            tool: Tool name that must not appear in the actual calls.

        Returns:
            ``self`` for chaining.
        """
        self._forbidden.append(tool)
        self._has_forbidden = True
        return self

    def with_score(self, min_score: float) -> Expectation:
        """Set the minimum composite score required (default: 0.9).

        Args:
            min_score: Float in ``[0.0, 1.0]``.

        Returns:
            ``self`` for chaining.
        """
        self._min_score = min_score
        return self

    def with_weights(self, **weights: float) -> Expectation:
        """Override composite-score weights.

        Valid keys: ``selection_accuracy``, ``argument_f1``,
        ``sequence_accuracy``, ``redundant_rate``.

        Args:
            **weights: Weight key/value pairs.

        Returns:
            ``self`` for chaining.
        """
        self._weights = weights
        return self

    def with_strict_args(self) -> Expectation:
        """Enable strict argument comparison (no int/float coercion, no string strip).

        Returns:
            ``self`` for chaining.
        """
        self._strict = True
        return self

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_actual(self) -> list[dict[str, Any]]:
        """Call subject with prompt (if callable) and return call dicts."""
        subject = self._subject
        is_callable = callable(subject) and not isinstance(subject, (list, dict))

        if is_callable:
            if self._prompt is None:
                raise ValueError(
                    "expect() was given a callable subject but no prompt was set. "
                    "Call .on(prompt) before .run()."
                )
            # Guard against async callables in the sync path
            if inspect.iscoroutinefunction(subject):
                raise TypeError(
                    "subject is an async function — use `expect(...).run_async()` instead."
                )
            response = subject(self._prompt)
            if inspect.isawaitable(response):
                # Close the coroutine to avoid "unawaited coroutine" warning
                if inspect.iscoroutine(response):
                    response.close()
                raise TypeError("subject is async — use `expect(...).run_async()` instead.")
            return auto_extract(response)
        else:
            if self._prompt is not None:
                raise TypeError(
                    "expect() was given a non-callable subject (a raw result or list), "
                    "but .on(prompt) was also called.  "
                    "Use .on() only when the subject is an agent callable."
                )
            return auto_extract(subject)

    async def _resolve_actual_async(self) -> list[dict[str, Any]]:
        """Async version: awaits callable response if needed."""
        subject = self._subject
        is_callable = callable(subject) and not isinstance(subject, (list, dict))

        if is_callable:
            if self._prompt is None:
                raise ValueError(
                    "expect() was given a callable subject but no prompt was set. "
                    "Call .on(prompt) before .run_async()."
                )
            response = subject(self._prompt)
            if inspect.isawaitable(response):
                response = await response
            return auto_extract(response)
        else:
            if self._prompt is not None:
                raise TypeError(
                    "expect() was given a non-callable subject (a raw result or list), "
                    "but .on(prompt) was also called.  "
                    "Use .on() only when the subject is an agent callable."
                )
            return auto_extract(subject)

    def _check_forbidden(self, actual_calls: list[dict[str, Any]]) -> None:
        """Raise ToolScoreAssertionError if any forbidden tool appears in actual_calls."""
        if not self._forbidden:
            return
        actual_tools = {c.get("tool") for c in actual_calls}
        violations = [tool for tool in self._forbidden if tool in actual_tools]
        if violations:
            names = ", ".join(repr(t) for t in violations)
            raise ToolScoreAssertionError(
                f"Forbidden tool(s) were called: {names}\n"
                f"Actual calls: {[c.get('tool') for c in actual_calls]}"
            )

    def _run_evaluate(self, actual_calls: list[dict[str, Any]]) -> EvaluationResult:
        """Core evaluate + min-score check (skipped for forbidden-only)."""
        result = evaluate(self._expected, actual_calls, weights=self._weights, strict=self._strict)
        _check_min_score(result, self._min_score)
        return result

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self) -> EvaluationResult:
        """Execute the assertion synchronously.

        Raises:
            ValueError: If no expectations are declared, or prompt is missing
                for a callable subject, or prompt is set for a non-callable subject.
            TypeError: If the subject is an async function (use :meth:`run_async`).
            ToolScoreAssertionError: If a forbidden tool was called, or the
                composite score is below :meth:`with_score`.

        Returns:
            :class:`~toolscore.core.EvaluationResult` on success.
        """
        if not self._has_calls and not self._has_forbidden:
            raise ValueError(
                "no expectations declared — call .calls(), .then_calls(), "
                "or .does_not_call() before .run()."
            )

        actual_calls = self._resolve_actual()
        self._check_forbidden(actual_calls)

        if not self._has_calls:
            # forbidden-only: run evaluate with empty expected, skip min-score check
            return evaluate([], actual_calls)

        return self._run_evaluate(actual_calls)

    async def run_async(self) -> EvaluationResult:
        """Execute the assertion asynchronously.

        Works for both sync and async agent callables, as well as
        already-produced results.

        Raises:
            ValueError: If no expectations are declared, or prompt is missing
                for a callable subject, or prompt is set for a non-callable subject.
            ToolScoreAssertionError: If a forbidden tool was called, or the
                composite score is below :meth:`with_score`.

        Returns:
            :class:`~toolscore.core.EvaluationResult` on success.
        """
        if not self._has_calls and not self._has_forbidden:
            raise ValueError(
                "no expectations declared — call .calls(), .then_calls(), "
                "or .does_not_call() before .run_async()."
            )

        actual_calls = await self._resolve_actual_async()
        self._check_forbidden(actual_calls)

        if not self._has_calls:
            # forbidden-only: run evaluate with empty expected, skip min-score check
            return evaluate([], actual_calls)

        return self._run_evaluate(actual_calls)


def expect(subject: Any) -> Expectation:
    """Create a fluent :class:`Expectation` for *subject*.

    *subject* may be:

    * An **agent callable** (sync or async) — pair with ``.on(prompt)`` then
      call ``.run()`` or ``.run_async()``.
    * An **already-produced result** — a raw OpenAI/Anthropic/Gemini response,
      a LangGraph state, or a list of call dicts.  Do **not** call ``.on()``.

    Args:
        subject: An agent callable or a raw LLM response / list of call dicts.

    Returns:
        An :class:`Expectation` builder.

    Example::

        from toolscore import expect, ANY, Regex

        expect(agent).on("book me a flight to NYC") \\
            .calls("search_flights", origin=ANY, destination="NYC") \\
            .then_calls("book_flight", flight_id=Regex(r"FL-\\d+")) \\
            .does_not_call("cancel_booking") \\
            .with_score(0.9) \\
            .run()
    """
    return Expectation(subject)


__all__ = ["Expectation", "expect"]
