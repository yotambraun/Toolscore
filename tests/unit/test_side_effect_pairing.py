"""Side-effect checks find the actual call with the same one-to-one pairing as
argument scoring, so a missing earlier call cannot hide a later one."""

from toolscore.adapters.base import ToolCall
from toolscore.metrics.side_effects import calculate_side_effect_success_rate


def test_missing_earlier_call_does_not_hide_the_call_being_checked():
    gold = [
        ToolCall(tool="search", args={"q": "x"}),
        ToolCall(
            tool="write", args={"path": "a.txt"}, metadata={"side_effects": {"file_written": True}}
        ),
    ]
    trace = [ToolCall(tool="write", args={"path": "a.txt"}, result={"ok": True})]
    validators = {"file_written": lambda call, expected: call.args.get("path") == "a.txt"}
    result = calculate_side_effect_success_rate(gold, trace, validators)
    assert result["passed_checks"] == 1 and result["total_checks"] == 1
