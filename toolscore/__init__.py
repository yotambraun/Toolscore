"""Toolscore: LLM Tool Usage Evaluation Package.

A Python package for evaluating the tool-using behavior of LLM-based agents
by comparing traces against gold-standard specifications.
"""

__version__ = "1.4.0"

from toolscore.capture import TraceCapture, capture_trace
from toolscore.core import evaluate_trace

__all__ = ["TraceCapture", "__version__", "capture_trace", "evaluate_trace"]
