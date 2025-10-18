"""Toolscore: LLM Tool Usage Evaluation Package.

A Python package for evaluating the tool-using behavior of LLM-based agents
by comparing traces against gold-standard specifications.
"""

__version__ = "1.1.1"

from toolscore.core import evaluate_trace

__all__ = ["__version__", "evaluate_trace"]
