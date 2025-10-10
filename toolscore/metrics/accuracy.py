"""Tool invocation and selection accuracy metrics."""

from toolscore.adapters.base import ToolCall


def calculate_invocation_accuracy(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
) -> float:
    """Calculate tool invocation accuracy.

    Measures whether the agent invoked tools when it was supposed to,
    and refrained from invoking when not needed.

    Args:
        gold_calls: Expected tool calls from gold standard.
        trace_calls: Actual tool calls from agent trace.

    Returns:
        Accuracy score between 0.0 and 1.0.
        - 1.0: Perfect invocation behavior
        - 0.0: Completely incorrect invocation behavior
    """
    # If no tools are expected and none were used
    if not gold_calls and not trace_calls:
        return 1.0

    # If tools were expected but none were used
    if gold_calls and not trace_calls:
        return 0.0

    # If tools were used but none were expected
    if not gold_calls and trace_calls:
        return 0.0

    # Calculate what proportion of expected tools were invoked
    gold_tool_names = {call.tool for call in gold_calls}
    trace_tool_names = {call.tool for call in trace_calls}

    correctly_invoked = gold_tool_names & trace_tool_names
    incorrectly_invoked = trace_tool_names - gold_tool_names
    missed_invocations = gold_tool_names - trace_tool_names

    total_expected = len(gold_tool_names)
    correct_count = len(correctly_invoked)
    penalty = len(incorrectly_invoked) + len(missed_invocations)

    # Calculate accuracy with penalty for incorrect invocations
    accuracy = max(0.0, (correct_count - penalty * 0.5) / total_expected)

    return min(1.0, accuracy)


def calculate_selection_accuracy(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
) -> float:
    """Calculate tool selection accuracy.

    Measures whether the agent selected the correct tools to use,
    given that it decided to use tools.

    Args:
        gold_calls: Expected tool calls from gold standard.
        trace_calls: Actual tool calls from agent trace.

    Returns:
        Accuracy score between 0.0 and 1.0.
        - 1.0: All selected tools were correct
        - 0.0: No selected tools were correct
    """
    if not trace_calls:
        # No tools selected - accuracy is 0 if tools were expected, 1 otherwise
        return 1.0 if not gold_calls else 0.0

    if not gold_calls:
        # Tools were selected but none expected
        return 0.0

    gold_tool_names = {call.tool for call in gold_calls}
    correct_selections = sum(1 for call in trace_calls if call.tool in gold_tool_names)

    accuracy = correct_selections / len(trace_calls)
    return accuracy
