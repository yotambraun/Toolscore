"""Rich failure-diff rendering for Toolscore assertion errors.

Provides :func:`build_diff_table` and :func:`render_failure` which together
produce a human-readable expected-vs-actual diff when a score threshold is
not met.
"""

from __future__ import annotations

import difflib
import io
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from toolscore.verdict import FixSuggestion

if TYPE_CHECKING:
    from toolscore.adapters.base import ToolCall
    from toolscore.core import EvaluationResult

_MAX_VAL_LEN = 40


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(value: str, max_len: int = _MAX_VAL_LEN) -> str:
    """Truncate a string to *max_len* chars, appending ``…`` if needed."""
    if len(value) <= max_len:
        return value
    return value[:max_len] + "…"


def _fmt_value(v: Any) -> str:
    """Format a value compactly, truncated to :data:`_MAX_VAL_LEN` chars."""
    return _truncate(repr(v))


def _fmt_call(call: ToolCall, *, max_val: int = _MAX_VAL_LEN) -> str:
    """Render a ToolCall as ``tool(k=v, …)`` with truncated values.

    A gold call whose ``args is None`` ("do not check arguments") renders as
    ``tool(…any args…)`` to make the don't-check semantics visible.  An empty
    dict (``args == {}``) renders as ``tool()`` (expect zero arguments).
    """
    if call.args is None:
        return f"{call.tool}(…any args…)"
    args = call.args
    if not args:
        return f"{call.tool}()"
    parts = []
    for k, v in args.items():
        parts.append(f"{k}={_truncate(repr(v), max_val)}")
    return f"{call.tool}({', '.join(parts)})"


def _arg_diff_lines(gold_args: dict[str, Any], trace_args: dict[str, Any]) -> list[str]:
    """Return per-arg mismatch strings for two argument dicts.

    Only reports keys where values differ, are missing, or are unexpected.
    """
    gold_keys = set(gold_args)
    trace_keys = set(trace_args)
    lines: list[str] = []

    # Value mismatches on common keys
    for k in sorted(gold_keys & trace_keys):
        gv = gold_args[k]
        tv = trace_args[k]
        if gv != tv:
            lines.append(f"{k}: {_fmt_value(gv)} ≠ {_fmt_value(tv)}")

    # Missing keys (in gold but not in trace)
    for k in sorted(gold_keys - trace_keys):
        lines.append(f"missing: {k}")

    # Unexpected keys (in trace but not in gold)
    for k in sorted(trace_keys - gold_keys):
        lines.append(f"unexpected: {k}")

    return lines


# ---------------------------------------------------------------------------
# Table builder
# ---------------------------------------------------------------------------


def build_diff_table(gold: list[ToolCall], trace: list[ToolCall]) -> Table:
    """Build a Rich :class:`~rich.table.Table` comparing two call sequences.

    Uses :class:`difflib.SequenceMatcher` over tool-name lists to align the
    two sequences.  Each aligned position becomes one row with columns:

    * ``#`` — position index
    * ``Expected`` — gold call rendered as ``tool(k=v, …)``
    * ``Actual`` — trace call rendered as ``tool(k=v, …)``
    * ``Status`` — ``✓`` / arg mismatches / ``MISSING`` / ``EXTRA``

    Args:
        gold: Expected tool calls.
        trace: Actual tool calls.

    Returns:
        A :class:`rich.table.Table` ready for rendering.
    """
    table = Table(
        title="Expected vs Actual Tool Calls",
        show_header=True,
        header_style="bold",
        show_lines=True,
        expand=False,
    )
    table.add_column("#", justify="right", no_wrap=True, min_width=3)
    table.add_column("Expected", no_wrap=False, min_width=20)
    table.add_column("Actual", no_wrap=False, min_width=20)
    table.add_column("Status", no_wrap=False, min_width=12)

    gold_names = [c.tool for c in gold]
    trace_names = [c.tool for c in trace]

    matcher = difflib.SequenceMatcher(None, gold_names, trace_names, autojunk=False)
    row_idx = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Aligned equal-name pairs — check args
            for gi, ti in zip(range(i1, i2), range(j1, j2), strict=False):
                row_idx += 1
                g = gold[gi]
                t = trace[ti]
                gold_cell = Text(_fmt_call(g))
                trace_cell = Text(_fmt_call(t))

                # Gold args is None → "do not check arguments": never a mismatch.
                diffs = [] if g.args is None else _arg_diff_lines(g.args, t.args or {})

                if not diffs:
                    status = Text("✓", style="green")
                    table.add_row(
                        str(row_idx),
                        gold_cell,
                        trace_cell,
                        status,
                        style="green",
                    )
                else:
                    status = Text("\n".join(diffs), style="yellow")
                    table.add_row(
                        str(row_idx),
                        gold_cell,
                        trace_cell,
                        status,
                        style="yellow",
                    )

        elif tag == "replace":
            # Align as many as we can, then handle leftovers
            g_block = list(range(i1, i2))
            t_block = list(range(j1, j2))
            paired = min(len(g_block), len(t_block))

            for k in range(paired):
                row_idx += 1
                g = gold[g_block[k]]
                t = trace[t_block[k]]
                gold_cell = Text(_fmt_call(g))
                trace_cell = Text(_fmt_call(t))

                # Different tool names — always a mismatch
                if g.tool != t.tool:
                    status = Text(f"tool: {g.tool!r} ≠ {t.tool!r}", style="yellow")
                    table.add_row(
                        str(row_idx),
                        gold_cell,
                        trace_cell,
                        status,
                        style="yellow",
                    )
                else:
                    # Same tool, arg mismatches.  Gold args None → no check.
                    diffs = [] if g.args is None else _arg_diff_lines(g.args, t.args or {})
                    status = Text(
                        "\n".join(diffs) if diffs else "✓", style="yellow" if diffs else "green"
                    )
                    table.add_row(
                        str(row_idx),
                        gold_cell,
                        trace_cell,
                        status,
                        style="yellow" if diffs else "green",
                    )

            # Extra gold (missing in trace)
            for k in range(paired, len(g_block)):
                row_idx += 1
                g = gold[g_block[k]]
                table.add_row(
                    str(row_idx),
                    Text(_fmt_call(g)),
                    Text("— MISSING —", style="red"),
                    Text("MISSING", style="red"),
                    style="red",
                )

            # Extra trace (not in gold)
            for k in range(paired, len(t_block)):
                row_idx += 1
                t = trace[t_block[k]]
                table.add_row(
                    str(row_idx),
                    Text("— EXTRA —", style="red"),
                    Text(_fmt_call(t)),
                    Text("EXTRA", style="red"),
                    style="red",
                )

        elif tag == "delete":
            # Gold-only rows — missing from trace
            for gi in range(i1, i2):
                row_idx += 1
                g = gold[gi]
                table.add_row(
                    str(row_idx),
                    Text(_fmt_call(g)),
                    Text("— MISSING —", style="red"),
                    Text("MISSING", style="red"),
                    style="red",
                )

        elif tag == "insert":
            # Trace-only rows — extra
            for ti in range(j1, j2):
                row_idx += 1
                t = trace[ti]
                table.add_row(
                    str(row_idx),
                    Text("— EXTRA —", style="red"),
                    Text(_fmt_call(t)),
                    Text("EXTRA", style="red"),
                    style="red",
                )

    return table


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def render_failure(
    result: EvaluationResult,
    min_score: float,
    *,
    color: bool = False,
    width: int = 100,
) -> str:
    """Render a human-readable failure report for a score that fell below threshold.

    Produces:
    * An expected-vs-actual diff table (via :func:`build_diff_table`).
    * A score breakdown footer line.
    * Actionable tips from :mod:`toolscore.explainer`.

    Args:
        result: Evaluation result that failed the threshold check.
        min_score: The minimum score that was required.
        color: When ``True``, include ANSI escape sequences (for terminal output).
            When ``False`` (default), produce clean plain text suitable for
            embedding inside a pytest failure message.
        width: Console width for wrapping.

    Returns:
        Rendered string (with or without ANSI escapes depending on *color*).
    """
    from toolscore.explainer import generate_explanations, get_all_tips

    console = Console(
        file=io.StringIO(),
        record=True,
        width=width,
        force_terminal=color,
        color_system="standard" if color else None,
        highlight=False,
    )

    # Diff table
    table = build_diff_table(result.gold_calls, result.trace_calls)
    console.print(table)

    # Score breakdown line
    sel = result.selection_accuracy
    arg = result.argument_f1
    seq = result.sequence_accuracy
    score_line = (
        f"score {result.score:.2f} < {min_score:.2f} required"
        f"  ·  selection {sel:.2f}"
        f"  ·  args {arg:.2f}"
        f"  ·  sequence {seq:.2f}"
    )
    console.print(score_line)

    # Tips from explainer
    explanations = generate_explanations(result)
    tips = get_all_tips(explanations)
    if tips:
        console.print("")
        console.print("Tips:")
        for tip in tips:
            console.print(f"  • {tip}")

    return console.export_text(styles=color)


# ---------------------------------------------------------------------------
# Agent-side "Top issues to fix" verdict
# ---------------------------------------------------------------------------

#: Priority bands for agent-side fix suggestions (lower is more urgent).
_PRIORITY_MISSING = 0
_PRIORITY_WRONG_TOOL = 1
_PRIORITY_ARG_MISMATCH = 2
_PRIORITY_EXTRA = 3


def _missing_fix(call: ToolCall) -> FixSuggestion:
    """Build a fix suggestion for an expected call that never happened."""
    return FixSuggestion(
        tool=call.tool,
        problem=f"expected call to `{call.tool}` never happened",
        fix="Ensure the agent has this tool available and is prompted to use it for this task.",
        priority=_PRIORITY_MISSING,
    )


def _extra_fix(call: ToolCall) -> FixSuggestion:
    """Build a fix suggestion for an unexpected extra call."""
    return FixSuggestion(
        tool=call.tool,
        problem=f"unexpected extra call to `{call.tool}`",
        fix="Remove the redundant call, or add it to the expected spec if it is intended.",
        priority=_PRIORITY_EXTRA,
    )


def build_eval_fix_list(gold: list[ToolCall], trace: list[ToolCall]) -> list[FixSuggestion]:
    """Turn an expected-vs-actual tool-call diff into a ranked fix list.

    Aligns the two sequences by tool name (like :func:`build_diff_table`) and
    surfaces, worst first: **missing** expected calls, **wrong tool** at a
    position, **argument mismatches** on otherwise-correct calls, and
    **extra/unexpected** calls. Gold calls whose ``args is None`` ("don't check
    arguments") never raise an argument mismatch.

    Args:
        gold: Expected tool calls.
        trace: Actual tool calls.

    Returns:
        Ranked :class:`~toolscore.verdict.FixSuggestion` items (empty when the
        sequences match).
    """
    matcher = difflib.SequenceMatcher(
        a=[c.tool for c in gold], b=[c.tool for c in trace], autojunk=False
    )
    suggestions: list[FixSuggestion] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for gi, tj in zip(range(i1, i2), range(j1, j2), strict=True):
                gold_call = gold[gi]
                trace_call = trace[tj]
                if gold_call.args is None:
                    continue
                diff_lines = _arg_diff_lines(gold_call.args or {}, trace_call.args or {})
                if diff_lines:
                    detail = "; ".join(diff_lines)
                    suggestions.append(
                        FixSuggestion(
                            tool=gold_call.tool,
                            problem=f"`{gold_call.tool}` called with unexpected arguments ({detail})",
                            fix=(
                                "Align the arguments with what's expected, or relax the spec "
                                "with a matcher like ANY/Regex if the value may vary."
                            ),
                            priority=_PRIORITY_ARG_MISMATCH,
                        )
                    )
        elif tag == "replace":
            paired = min(i2 - i1, j2 - j1)
            for offset in range(paired):
                gold_call = gold[i1 + offset]
                trace_call = trace[j1 + offset]
                suggestions.append(
                    FixSuggestion(
                        tool=trace_call.tool,
                        problem=f"called `{trace_call.tool}` where `{gold_call.tool}` was expected",
                        fix=(
                            "Adjust the prompt or tool descriptions so the agent picks "
                            f"`{gold_call.tool}` here."
                        ),
                        priority=_PRIORITY_WRONG_TOOL,
                    )
                )
            suggestions.extend(_missing_fix(gold[gi]) for gi in range(i1 + paired, i2))
            suggestions.extend(_extra_fix(trace[tj]) for tj in range(j1 + paired, j2))
        elif tag == "delete":
            suggestions.extend(_missing_fix(gold[gi]) for gi in range(i1, i2))
        elif tag == "insert":
            suggestions.extend(_extra_fix(trace[tj]) for tj in range(j1, j2))

    suggestions.sort(key=lambda s: s.priority)
    return suggestions
