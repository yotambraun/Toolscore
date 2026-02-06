"""Toolscore: Lightweight tool-call testing for LLM agents.

Deterministic, local, zero API cost evaluation of LLM tool-calling behavior.
"""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("tool-scorer")
except PackageNotFoundError:
    __version__ = _version("toolscore")

from toolscore.capture import TraceCapture, capture_trace
from toolscore.core import (
    ToolScoreAssertionError,
    assert_tools,
    evaluate,
    evaluate_trace,
)
from toolscore.integrations import from_anthropic, from_gemini, from_openai

__all__ = [
    "ToolScoreAssertionError",
    "TraceCapture",
    "__version__",
    "assert_tools",
    "capture_trace",
    "evaluate",
    "evaluate_trace",
    "from_anthropic",
    "from_gemini",
    "from_openai",
]
