"""Toolscore: Lightweight tool-call testing for LLM agents.

Deterministic, local, zero API cost evaluation of LLM tool-calling behavior.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from toolscore.capture import TraceCapture, capture_trace
from toolscore.core import (
    ToolScoreAssertionError,
    assert_tools,
    evaluate,
    evaluate_trace,
    test_agent,
)
from toolscore.integrations import auto_extract, from_anthropic, from_gemini, from_openai

try:
    __version__ = _version("tool-scorer")
except PackageNotFoundError:
    __version__ = _version("toolscore")


def cases(
    test_cases: list[dict[str, object]],
    id_key: str = "input",
) -> object:
    """Parametrize a pytest test function with a list of test-case dicts.

    Thin wrapper around :func:`pytest.mark.parametrize` that extracts keys
    from the first test case dict and uses them as parameter names.

    Args:
        test_cases: List of dicts, each representing one test case.
        id_key: Key whose value is used as the pytest test-ID (default: ``"input"``).

    Returns:
        A ``pytest.mark.parametrize`` decorator.

    Example::

        @toolscore.cases([
            {"input": "weather NYC", "expected": [{"tool": "get_weather", "args": {"city": "NYC"}}]},
        ])
        def test_my_agent(input, expected):
            toolscore.assert_tools(expected=expected, actual=my_agent(input), min_score=0.9)
    """
    import pytest

    keys = list(test_cases[0].keys())
    ids = [str(tc.get(id_key, i)) for i, tc in enumerate(test_cases)]
    return pytest.mark.parametrize(
        keys,
        [tuple(tc[k] for k in keys) for tc in test_cases],
        ids=ids,
    )


__all__ = [
    "ToolScoreAssertionError",
    "TraceCapture",
    "__version__",
    "assert_tools",
    "auto_extract",
    "capture_trace",
    "cases",
    "evaluate",
    "evaluate_trace",
    "from_anthropic",
    "from_gemini",
    "from_openai",
    "test_agent",
]
