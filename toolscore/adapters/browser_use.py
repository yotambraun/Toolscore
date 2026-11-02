"""browser-use agent history adapter.

`browser-use <https://github.com/browser-use/browser-use>`_ records a run as an
``AgentHistoryList``. ``history.save_to_file(path)`` and
``history.model_dump()`` write ``{"history": [step, ...]}``; each step
(``AgentHistory``) is::

    {
      "model_output": {"evaluation_previous_goal": ..., "memory": ..., "next_goal": ...,
                       "thinking": ..., "action": [{"click": {"index": 12}}, ...]},
      "result": [{"is_done": false, "extracted_content": "...", "error": "...", ...}, ...],
      "state": {"url": ..., "title": ..., "tabs": [...], "interacted_element": [...],
                "screenshot_path": ...},
      "metadata": {"step_start_time": ..., "step_end_time": ..., "step_number": ...,
                   "step_interval": ...},
      "state_message": ...
    }

Verified against ``browser_use/agent/views.py`` and ``browser_use/tools`` of
browser-use 0.13.14. Older releases nest the brain fields under
``model_output.current_state``; the actions and results have the same shape,
so they are read the same way.

Each executed action is one call: the tool is the action name (``click``,
``input``, ``navigate``, ``evaluate``, ``done``...; older releases used
``click_element_by_index``, ``input_text``, ``go_to_url``), the arguments are
its parameters, the result is the action result's ``extracted_content`` and
the error its ``error``. browser-use runs a step's actions in order and stops
at the first error, at ``done``, or after an action that changes the page, so
a step returns one result per *executed* action: results are paired with
actions by position, and actions without a result were never run and are not
calls. A step without ``model_output`` (the model's output could not be used)
has no actions.

The model's notes on each step (``thinking``, ``evaluation_previous_goal``,
``memory``, ``next_goal``) are kept on the step's calls as
``metadata["agent_note"]``: the honesty checks read a refusal there when the
page, not a tool result, showed it (a click on a disabled button "succeeds"
in browser-use and does nothing; the model sees ``disabled`` in the page
state and says so).

The final answer is the text of the ``done`` action, which browser-use stores
as the ``extracted_content`` of the last result with ``is_done: true``; that
result's ``success`` is the agent's own verdict.
"""

from __future__ import annotations

from typing import Any

from toolscore.adapters.base import BaseAdapter, ToolCall


def _steps(data: Any) -> list[dict[str, Any]] | None:
    """The step dicts of a browser-use history, or ``None`` when ``data`` is not one."""
    items = data.get("history") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        return None
    steps = [s for s in items if isinstance(s, dict)]
    if not steps or len(steps) != len(items):
        return None
    if not all("result" in s and "model_output" in s for s in steps):
        return None
    if not all(isinstance(s.get("result"), list) for s in steps):
        return None
    return steps


def looks_like_browser_use(data: Any) -> bool:
    """Whether ``data`` is a browser-use history: ``{"history": [steps]}`` or a step list."""
    return _steps(data) is not None


def _actions(step: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """``(action name, params)`` for each action the model asked for in a step."""
    output = step.get("model_output")
    actions = output.get("action") if isinstance(output, dict) else None
    if not isinstance(actions, list):
        return []
    found: list[tuple[str, dict[str, Any]]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        # model_actions() adds "interacted_element" next to the action name.
        names = [k for k in action if k != "interacted_element"]
        if not names:
            continue
        params = action[names[0]]
        found.append((str(names[0]), params if isinstance(params, dict) else {}))
    return found


#: The model's notes on a step (top level in 0.13, under ``current_state`` before).
_NOTE_FIELDS = ("thinking", "evaluation_previous_goal", "memory", "next_goal")


def _note(step: dict[str, Any]) -> str:
    """What the model wrote about a step: its thinking, evaluation, memory and next goal."""
    output = step.get("model_output")
    if not isinstance(output, dict):
        return ""
    brain = output.get("current_state")
    source = brain if isinstance(brain, dict) else output
    return "\n".join(
        str(source[k]) for k in _NOTE_FIELDS if isinstance(source.get(k), str) and source[k]
    )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def browser_use_calls(data: Any) -> list[ToolCall]:
    """The executed actions of a browser-use history as tool calls (see the module docstring).

    Raises:
        ValueError: If ``data`` is not a browser-use history.
    """
    steps = _steps(data)
    if steps is None:
        raise ValueError(
            "Expected a browser-use history: {'history': [...]} with model_output and result"
        )
    calls: list[ToolCall] = []
    for position, step in enumerate(steps, start=1):
        results = [r if isinstance(r, dict) else {} for r in step.get("result") or []]
        actions = _actions(step)
        state = _mapping(step.get("state"))
        meta = _mapping(step.get("metadata"))
        start = _number(meta.get("step_start_time"))
        end = _number(meta.get("step_end_time"))
        number = meta.get("step_number")
        note = _note(step)
        executed = list(zip(actions, results, strict=False))
        for index, ((name, params), result) in enumerate(executed):
            metadata: dict[str, Any] = {
                "format": "browser-use",
                "id": f"step{number if isinstance(number, int) else position}.{index + 1}",
                "step": number if isinstance(number, int) else position,
            }
            if isinstance(state.get("url"), str):
                metadata["url"] = state["url"]
            if note:
                metadata["agent_note"] = note
            error = result.get("error")
            if isinstance(error, str) and error:
                metadata["error"] = error
                metadata["is_error"] = True
            elif result:
                metadata["is_error"] = False
            if result.get("is_done") is True:
                metadata["is_done"] = True
                if isinstance(result.get("success"), bool):
                    metadata["success"] = result["success"]
            if isinstance(result.get("long_term_memory"), str):
                metadata["long_term_memory"] = result["long_term_memory"]
            content = result.get("extracted_content")
            # A step's timing covers all of its actions: a duration only when it ran one.
            duration = (
                end - start
                if start is not None and end is not None and end >= start and len(executed) == 1
                else None
            )
            calls.append(
                ToolCall(
                    tool=name,
                    args=dict(params),
                    result=content if isinstance(content, str) else None,
                    timestamp=start,
                    duration=duration,
                    metadata=metadata,
                )
            )
    return calls


def browser_use_final(data: Any) -> tuple[str | None, bool | None]:
    """The ``done`` text and the agent's own ``success`` flag, as ``final_result()`` reads them.

    Returns:
        ``(text, success)``: the ``extracted_content`` of the last result of
        the last step when it has ``is_done: true``, and its ``success``
        (``None`` when absent); ``(None, None)`` when the run did not finish.
    """
    steps = _steps(data)
    if not steps:
        return None, None
    results = steps[-1].get("result") or []
    last = results[-1] if results and isinstance(results[-1], dict) else None
    if last is None or last.get("is_done") is not True:
        return None, None
    text = last.get("extracted_content")
    success = last.get("success")
    return (
        text.strip() if isinstance(text, str) and text.strip() else None,
        success if isinstance(success, bool) else None,
    )


class BrowserUseAdapter(BaseAdapter):
    """Adapter for browser-use ``AgentHistoryList`` dumps (``save_to_file`` / ``model_dump``)."""

    def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
        """Parse a browser-use history into tool calls, one per executed action.

        Args:
            trace_data: ``{"history": [...]}`` or the list of steps.

        Returns:
            The calls in order, with results and errors attached.

        Raises:
            ValueError: If the data is not a browser-use history.
        """
        self._validate_trace_data(trace_data)
        return browser_use_calls(trace_data)
