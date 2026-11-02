"""README badges for an MCP Scorecard grade.

``toolscore mcp test SERVER --badge mcp-grade.svg`` writes a self-contained SVG
badge, and ``--badge-json mcp-grade.json`` a `shields.io endpoint`_ JSON file.
Both are produced from the scorecard of that run; there is no way to pass a
grade in by hand. A grade capped by a failed effect probe reads
``C (capped) · Toolscore``, and the SVG's title says why.

.. _shields.io endpoint: https://shields.io/badges/endpoint-badge
"""

from __future__ import annotations

from html import escape
from typing import Any

#: Badge label (left half).
LABEL = "MCP grade"

#: shields.io named color and hex value per grade.
GRADE_COLORS: dict[str, tuple[str, str]] = {
    "A": ("brightgreen", "#4c1"),
    "B": ("green", "#97ca00"),
    "C": ("yellow", "#dfb317"),
    "D": ("orange", "#fe7d37"),
    "F": ("red", "#e05d44"),
}

# Approximate advance widths (px) of Verdana 11px, the shields.io badge font.
_NARROW = set("fijlrt.,:;!'|I ·")
_WIDE = set("mwMW@%")


def _text_width(text: str) -> int:
    """Estimate the rendered width of ``text`` in Verdana 11px."""
    width = 0.0
    for char in text:
        if char in _NARROW:
            width += 4.0
        elif char in _WIDE:
            width += 10.0
        elif char.isupper() or char.isdigit():
            width += 7.5
        else:
            width += 6.5
    return round(width)


def badge_message(grade: str, capped: bool = False) -> str:
    """The right half of the badge, e.g. ``"A · Toolscore"`` or ``"C (capped) · Toolscore"``."""
    return f"{grade} (capped) · Toolscore" if capped else f"{grade} · Toolscore"


def badge_svg(grade: str, cap_note: str = "") -> str:
    """Render the grade as a flat, shields.io-style SVG badge.

    Args:
        grade: The scorecard grade (``A``-``F``).
        cap_note: :attr:`~toolscore.mcp.scorecard.MCPScorecard.grade_cap_note`
            when the grade is capped (``"capped because: ..."``); it marks the
            badge "(capped)" and goes in the SVG title.

    Returns:
        The SVG document.
    """
    _, color = GRADE_COLORS.get(grade.upper(), ("lightgrey", "#9f9f9f"))
    message = badge_message(grade.upper(), capped=bool(cap_note))
    label_text, message_text = escape(LABEL), escape(message)
    label_w = _text_width(LABEL) + 10
    message_w = _text_width(message) + 10
    total = label_w + message_w
    title = f"{label_text}: {message_text}" + (f" ({escape(cap_note)})" if cap_note else "")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" '
        f'aria-label="{title}">'
        f"<title>{title}</title>"
        '<linearGradient id="s" x2="0" y2="100%">'
        '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        '<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>'
        '<g clip-path="url(#r)">'
        f'<rect width="{label_w}" height="20" fill="#555"/>'
        f'<rect x="{label_w}" width="{message_w}" height="20" fill="{color}"/>'
        f'<rect width="{total}" height="20" fill="url(#s)"/></g>'
        '<g fill="#fff" text-anchor="middle" '
        'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        f'<text x="{label_w / 2}" y="15" fill="#010101" fill-opacity=".3" '
        f'textLength="{label_w - 10}">{label_text}</text>'
        f'<text x="{label_w / 2}" y="14" textLength="{label_w - 10}">{label_text}</text>'
        f'<text x="{label_w + message_w / 2}" y="15" fill="#010101" fill-opacity=".3" '
        f'textLength="{message_w - 10}">{message_text}</text>'
        f'<text x="{label_w + message_w / 2}" y="14" textLength="{message_w - 10}">'
        f"{message_text}</text></g></svg>\n"
    )


def badge_endpoint(grade: str, cap_note: str = "") -> dict[str, Any]:
    """The shields.io endpoint JSON for the grade.

    Args:
        grade: The scorecard grade (``A``-``F``).
        cap_note: The cap note when the grade is capped (see :func:`badge_svg`).

    Returns:
        ``{"schemaVersion": 1, "label": ..., "message": ..., "color": ...}``.
    """
    named, _ = GRADE_COLORS.get(grade.upper(), ("lightgrey", "#9f9f9f"))
    return {
        "schemaVersion": 1,
        "label": LABEL,
        "message": badge_message(grade.upper(), capped=bool(cap_note)),
        "color": named,
    }
