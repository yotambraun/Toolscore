"""Shared verdict primitives: letter grades and ranked fix suggestions.

Both the MCP scorecard (:mod:`toolscore.mcp.scorecard`) and the agent-side
evaluation render the same kind of verdict -- an A--F grade plus a ranked
"Top issues to fix" list -- so the two surfaces stay consistent. The shared
building blocks live here to avoid duplication and keep the layering clean
(neither core nor reports should import from the ``mcp`` subpackage).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Grade thresholds, highest first. A score ``>= threshold`` earns ``letter``;
#: anything below the lowest band is an ``F``.
GRADE_BANDS: tuple[tuple[float, str], ...] = (
    (0.9, "A"),
    (0.8, "B"),
    (0.7, "C"),
    (0.6, "D"),
)

#: Grades from best to worst, used for ``--fail-under`` style comparisons.
GRADE_ORDER: tuple[str, ...] = ("A", "B", "C", "D", "F")


def letter_grade(score: float) -> str:
    """Map a ``[0, 1]`` score to an A--F letter grade.

    Args:
        score: The score to grade.

    Returns:
        ``"A"`` … ``"F"`` following :data:`GRADE_BANDS`.
    """
    for threshold, letter in GRADE_BANDS:
        if score >= threshold:
            return letter
    return "F"


@dataclass
class FixSuggestion:
    """A single ranked, actionable item in a "Top issues to fix" verdict.

    Attributes:
        tool: The tool the issue concerns.
        problem: A short statement of what is wrong.
        fix: A concrete suggestion for how to resolve it.
        priority: Ordering key; lower is more urgent.
    """

    tool: str
    problem: str
    fix: str
    priority: int
