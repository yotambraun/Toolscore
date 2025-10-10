"""Tool call sequence metrics."""

from Levenshtein import distance as levenshtein_distance

from toolscore.adapters.base import ToolCall


def calculate_edit_distance(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
) -> dict[str, float]:
    """Calculate edit distance metrics for tool call sequences.

    Computes Levenshtein edit distance between the sequence of tool names
    in the gold standard and the actual trace.

    Args:
        gold_calls: Expected tool calls from gold standard.
        trace_calls: Actual tool calls from agent trace.

    Returns:
        Dictionary containing:
        - edit_distance: Raw Levenshtein distance (lower is better)
        - normalized_distance: Distance normalized by max sequence length (0-1)
        - sequence_accuracy: 1 - normalized_distance (higher is better, 0-1)
    """
    gold_sequence = [call.tool for call in gold_calls]
    trace_sequence = [call.tool for call in trace_calls]

    # Calculate raw edit distance
    raw_distance = levenshtein_distance(gold_sequence, trace_sequence)

    # Normalize by the maximum possible distance (longer sequence length)
    max_length = max(len(gold_sequence), len(trace_sequence), 1)
    normalized_distance = raw_distance / max_length

    # Convert to accuracy metric (1 = perfect match, 0 = completely different)
    sequence_accuracy = 1.0 - normalized_distance

    return {
        "edit_distance": float(raw_distance),
        "normalized_distance": normalized_distance,
        "sequence_accuracy": sequence_accuracy,
    }
