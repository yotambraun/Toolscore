"""Integration helpers for extracting tool calls from LLM provider responses.

These functions convert raw API response objects (or dicts) into the simple
list-of-dicts format expected by ``toolscore.evaluate()``, so you never have
to manually construct JSON.

Example::

    from openai import OpenAI
    from toolscore import evaluate
    from toolscore.integrations import from_openai

    client = OpenAI()
    response = client.chat.completions.create(...)
    actual = from_openai(response)
    result = evaluate(expected=[...], actual=actual)
"""

from __future__ import annotations

import json
from typing import Any


def from_openai(response: Any) -> list[dict[str, Any]]:
    """Extract tool calls from an OpenAI chat completion response.

    Supports both the response object (``openai.types.chat.ChatCompletion``)
    and a plain dict with the same shape.

    Handles:
    - ``response.choices[0].message.tool_calls`` (modern function calling)
    - ``response.choices[0].message.function_call`` (legacy)

    Args:
        response: An OpenAI ChatCompletion response (object or dict).

    Returns:
        List of dicts with 'tool' and 'args' keys.
    """
    calls: list[dict[str, Any]] = []

    # Normalise to dict if it's a pydantic model / object
    if hasattr(response, "model_dump"):
        data = response.model_dump()
    elif hasattr(response, "__dict__") and not isinstance(response, dict):
        data = _object_to_dict(response)
    else:
        data = response

    choices = data.get("choices", [])
    for choice in choices:
        message = choice.get("message", {})

        # Modern tool_calls
        tool_calls = message.get("tool_calls") or []
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            arguments = func.get("arguments", "{}")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
            if name:
                calls.append({"tool": name, "args": arguments})

        # Legacy function_call
        if not tool_calls:
            fc = message.get("function_call")
            if fc:
                name = fc.get("name", "")
                arguments = fc.get("arguments", "{}")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except (json.JSONDecodeError, TypeError):
                        arguments = {}
                if name:
                    calls.append({"tool": name, "args": arguments})

    return calls


def from_anthropic(response: Any) -> list[dict[str, Any]]:
    """Extract tool calls from an Anthropic message response.

    Supports both the response object (``anthropic.types.Message``)
    and a plain dict with the same shape.

    Args:
        response: An Anthropic Message response (object or dict).

    Returns:
        List of dicts with 'tool' and 'args' keys.
    """
    calls: list[dict[str, Any]] = []

    if hasattr(response, "model_dump"):
        data = response.model_dump()
    elif hasattr(response, "__dict__") and not isinstance(response, dict):
        data = _object_to_dict(response)
    else:
        data = response

    content = data.get("content", [])
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name", "")
            args = block.get("input", {})
            if name:
                calls.append({"tool": name, "args": args if args else {}})

    return calls


def from_gemini(response: Any) -> list[dict[str, Any]]:
    """Extract tool calls from a Google Gemini response.

    Supports both the response object and a plain dict.

    Args:
        response: A Gemini GenerateContentResponse (object or dict).

    Returns:
        List of dicts with 'tool' and 'args' keys.
    """
    calls: list[dict[str, Any]] = []

    if hasattr(response, "model_dump"):
        data = response.model_dump()
    elif hasattr(response, "__dict__") and not isinstance(response, dict):
        data = _object_to_dict(response)
    else:
        data = response

    candidates = data.get("candidates", [])
    for candidate in candidates:
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        for part in parts:
            fc = part.get("functionCall") or part.get("function_call", {})
            if fc:
                name = fc.get("name", "")
                args = fc.get("args", {})
                if name:
                    calls.append({"tool": name, "args": args if args else {}})

    return calls


def from_langgraph(result: Any) -> list[dict[str, Any]]:
    """Extract tool calls from a LangGraph agent result.

    Accepts a LangGraph final state (dict or object with ``"messages"``) or a
    plain list of messages.  For each message that has non-empty ``tool_calls``
    (attribute or dict key), collects each entry's ``name`` / ``args``.

    This mirrors the LangChain AIMessage.tool_calls format::

        {"name": ..., "args": {...}, "id": ...}

    It also accepts the OpenAI wire format used in raw conversation histories,
    where each tool call nests under ``function``::

        {"function": {"name": ..., "arguments": "<json string>"}, "id": ...}

    Order across messages is preserved.

    Args:
        result: A LangGraph final state dict/object or a list of messages.

    Returns:
        List of dicts with 'tool' and 'args' keys.
    """
    calls: list[dict[str, Any]] = []

    # Resolve messages list
    if isinstance(result, list):
        messages = result
    else:
        # dict or object with "messages"
        if isinstance(result, dict):
            messages = result.get("messages", [])
        else:
            messages = getattr(result, "messages", []) or []

    for msg in messages:
        # Support both attribute and dict access
        if isinstance(msg, dict):
            tool_calls = msg.get("tool_calls") or []
        else:
            tool_calls = getattr(msg, "tool_calls", None) or []

        for tc in tool_calls:
            if isinstance(tc, dict):
                name = tc.get("name", "")
                args = tc.get("args", {})
                # OpenAI wire format nests under tc["function"]:
                #   {"function": {"name": ..., "arguments": "<json>"}}
                if not name:
                    func = tc.get("function")
                    if isinstance(func, dict):
                        name = func.get("name", "")
                        if not args:
                            args = func.get("arguments", {})
            else:
                name = getattr(tc, "name", "")
                args = getattr(tc, "args", {})
                if not name:
                    func = getattr(tc, "function", None)
                    if func is not None:
                        name = getattr(func, "name", "")
                        if not args:
                            args = getattr(func, "arguments", {})

            # Parse JSON-string args
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}

            if name:
                calls.append({"tool": name, "args": args if args is not None else {}})

    return calls


def from_pydantic_ai(result: Any) -> list[dict[str, Any]]:
    """Extract tool calls from a Pydantic AI agent result.

    Accepts an ``AgentRunResult`` (duck: has callable ``all_messages``) or a
    list of messages.  Walks each message's ``parts``; takes parts with
    ``part_kind == "tool-call"`` (attribute or key; also accepts class name
    ``ToolCallPart``).  Tool name from ``tool_name``; args from
    ``args_as_dict()`` if present, else ``args`` (JSON-string → json.loads,
    dict → as-is).

    Args:
        result: A Pydantic AI AgentRunResult or a list of messages.

    Returns:
        List of dicts with 'tool' and 'args' keys.
    """
    calls: list[dict[str, Any]] = []

    # Resolve messages list
    if isinstance(result, list):
        messages = result
    elif callable(getattr(result, "all_messages", None)):
        messages = result.all_messages()
    else:
        messages = []

    for msg in messages:
        # Support both attribute and dict access for parts
        parts = msg.get("parts", []) if isinstance(msg, dict) else getattr(msg, "parts", []) or []

        for part in parts:
            # Detect tool-call parts
            if isinstance(part, dict):
                part_kind = part.get("part_kind", "")
                is_tool_call = part_kind == "tool-call"
                tool_name = part.get("tool_name", "")
                raw_args = part.get("args", {})
            else:
                part_kind = getattr(part, "part_kind", "")
                class_name = type(part).__name__
                is_tool_call = part_kind == "tool-call" or class_name == "ToolCallPart"
                tool_name = getattr(part, "tool_name", "")
                # Prefer args_as_dict() if available
                if callable(getattr(part, "args_as_dict", None)):
                    raw_args = part.args_as_dict()
                else:
                    raw_args = getattr(part, "args", {})

            if not is_tool_call:
                continue

            # Normalise args
            if isinstance(raw_args, str):
                try:
                    args: dict[str, Any] = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}

            if tool_name:
                calls.append({"tool": tool_name, "args": args})

    return calls


def from_openai_agents(result: Any) -> list[dict[str, Any]]:
    """Extract tool calls from an OpenAI Agents SDK RunResult.

    Accepts an ``RunResult`` (duck: has ``new_items``) or a list of items.
    Takes items with ``type == "tool_call_item"`` (attribute or key); for each,
    the underlying ``raw_item`` has ``name`` and ``arguments`` (JSON string →
    parsed).

    Args:
        result: An OpenAI Agents SDK RunResult or a list of items.

    Returns:
        List of dicts with 'tool' and 'args' keys.
    """
    calls: list[dict[str, Any]] = []

    # Resolve items list
    if isinstance(result, list):
        items = result
    else:
        if isinstance(result, dict):
            items = result.get("new_items", [])
        else:
            items = getattr(result, "new_items", []) or []

    for item in items:
        if isinstance(item, dict):
            item_type = item.get("type", "")
            raw_item = item.get("raw_item", {})
        else:
            item_type = getattr(item, "type", "")
            raw_item = getattr(item, "raw_item", {})

        if item_type != "tool_call_item":
            continue

        if isinstance(raw_item, dict):
            name = raw_item.get("name", "")
            arguments = raw_item.get("arguments", "{}")
        else:
            name = getattr(raw_item, "name", "")
            arguments = getattr(raw_item, "arguments", "{}")

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                arguments = {}

        if name:
            calls.append({"tool": name, "args": arguments if arguments is not None else {}})

    return calls


def from_claude_agent_sdk(result: Any) -> list[dict[str, Any]]:
    """Extract tool calls from a Claude Agent SDK message list.

    Accepts a list of messages (dicts or objects); for each, walks ``content``
    blocks; blocks with ``type == "tool_use"`` give ``name`` + ``input`` dict.

    Args:
        result: A list of Claude Agent SDK messages (dicts or objects).

    Returns:
        List of dicts with 'tool' and 'args' keys.
    """
    calls: list[dict[str, Any]] = []

    if not isinstance(result, list):
        return calls

    for msg in result:
        if isinstance(msg, dict):
            content = msg.get("content", [])
        else:
            content = getattr(msg, "content", []) or []

        if isinstance(content, str):
            # Plain text content — no tool calls
            continue

        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                name = block.get("name", "")
                args = block.get("input", {})
            else:
                block_type = getattr(block, "type", "")
                name = getattr(block, "name", "")
                args = getattr(block, "input", {})

            if block_type == "tool_use" and name:
                calls.append({"tool": name, "args": args if args is not None else {}})

    return calls


def from_crewai(result: Any) -> list[dict[str, Any]]:
    """Extract tool calls from a CrewAI result (experimental).

    Best-effort extraction. Accepts objects/dicts exposing ``tool_name`` +
    ``tool_args`` entries (e.g. a list like agent ``tools_results``), or an
    object with a ``tools_results`` list.

    .. note::
        This extractor is **experimental** — CrewAI does not expose a stable
        structured trace API.  The extraction is best-effort and may not cover
        all CrewAI versions or configurations.

    Args:
        result: A list of tool-result entries, or an object/dict with a
            ``tools_results`` attribute/key.

    Returns:
        List of dicts with 'tool' and 'args' keys.
    """
    calls: list[dict[str, Any]] = []

    # Resolve to a list of entries
    if isinstance(result, list):
        entries = result
    elif isinstance(result, dict):
        entries = result.get("tools_results", [])
    else:
        entries = getattr(result, "tools_results", []) or []

    for entry in entries:
        if isinstance(entry, dict):
            name = entry.get("tool_name", "")
            args = entry.get("tool_args", {})
        else:
            name = getattr(entry, "tool_name", "")
            args = getattr(entry, "tool_args", {})

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                args = {}

        if name:
            calls.append({"tool": name, "args": args if args is not None else {}})

    return calls


def _is_langgraph_result(actual: Any) -> bool:
    """Return True if *actual* looks like a LangGraph state with tool_calls."""
    # Must be a dict/object with "messages", not an Anthropic raw message
    if isinstance(actual, dict):
        messages = actual.get("messages")
    else:
        messages = getattr(actual, "messages", None)

    if not isinstance(messages, list) or not messages:
        return False

    # Check that at least one message has non-empty tool_calls
    for msg in messages:
        tc = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
        if tc:
            return True
    return False


def _extract_langgraph_or_raise(actual: Any) -> list[dict[str, Any]]:
    """Extract LangGraph tool calls, raising if detection matched but yielded none.

    The LangGraph branch is only entered when at least one message carries a
    non-empty ``tool_calls``. If :func:`from_langgraph` still extracts zero
    calls, the messages use a shape we do not understand (rather than genuinely
    having no calls), which would otherwise produce a silent score near zero.
    Raise a clear error instead.
    """
    calls = from_langgraph(actual)
    if not calls:
        raise ValueError(
            "Detected a LangGraph/message-list response with tool_calls, but could "
            "not extract any tool calls from it. The tool_calls entries use an "
            "unrecognized shape (expected top-level 'name'/'args' or OpenAI-style "
            "'function.name'/'function.arguments'). Convert the response manually "
            "with toolscore.integrations.from_langgraph or pass a list of dicts "
            "with 'tool' and 'args' keys."
        )
    return calls


def _is_langgraph_message_list(actual: Any) -> bool:
    """Return True if *actual* is a bare list of messages with tool_calls.

    Mirrors :func:`_is_langgraph_result` but for a plain message list (no
    surrounding ``{"messages": [...]}`` wrapper). Scans *all* items, so a
    ``[human_msg, ai_msg_with_tool_calls]`` list is detected even though the
    tool calls live on the second message.
    """
    if not isinstance(actual, list) or not actual:
        return False
    for msg in actual:
        tc = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
        if tc:
            return True
    return False


def _is_claude_agent_sdk_list(actual: Any) -> bool:
    """Return True if *actual* looks like a list of Claude Agent SDK messages."""
    if not isinstance(actual, list) or not actual:
        return False
    for item in actual:
        content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        return True
                else:
                    if getattr(block, "type", None) == "tool_use":
                        return True
    return False


def auto_extract(actual: Any) -> list[dict[str, Any]]:
    """Auto-detect the provider format of a response and extract tool calls.

    This allows passing raw OpenAI, Anthropic, Gemini, LangGraph,
    Pydantic AI, OpenAI Agents SDK, or Claude Agent SDK responses directly
    to ``evaluate()`` without manually calling the framework-specific helper.

    Detection order:
    1. Already a list of dicts with ``"tool"`` keys → pass through
    2. Object with ``model_dump()`` → convert to dict, then re-detect
    3. Dict with ``"choices"`` → OpenAI format
    4. Dict with ``"content"`` list containing ``"type"`` keys → Anthropic format
    5. Dict with ``"candidates"`` → Gemini format
    6. Dict/object with ``"messages"`` where some message has ``tool_calls`` → LangGraph
    7. Object with callable ``all_messages`` → Pydantic AI
    8. Object/dict with ``new_items`` → OpenAI Agents SDK
    9. List whose items have content blocks with ``type == "tool_use"`` → Claude Agent SDK
    10. Bare list of messages where some message has ``tool_calls`` → LangGraph

    Args:
        actual: A raw LLM provider response (object or dict), or an
            already-formatted list of tool-call dicts.

    Returns:
        List of dicts with 'tool' and 'args' keys.

    Raises:
        TypeError: If the format cannot be detected.
        ValueError: If a LangGraph/message-list shape with ``tool_calls`` is
            detected but no tool calls can be extracted from it.
    """
    # 1. Already formatted
    if isinstance(actual, list) and (
        not actual or (isinstance(actual[0], dict) and "tool" in actual[0])
    ):
        return actual

    # 2. Pydantic / SDK object → convert to dict first
    if hasattr(actual, "model_dump"):
        actual = actual.model_dump()
    elif hasattr(actual, "__dict__") and not isinstance(actual, dict):
        # Before converting, check for framework-specific duck-typed objects
        # that would lose their callable methods after _object_to_dict().

        # 7. Pydantic AI: callable all_messages
        if callable(getattr(actual, "all_messages", None)):
            return from_pydantic_ai(actual)

        # 8. OpenAI Agents SDK: new_items attribute
        if hasattr(actual, "new_items"):
            return from_openai_agents(actual)

        # 6. LangGraph: messages attribute with tool_calls
        if _is_langgraph_result(actual):
            return _extract_langgraph_or_raise(actual)

        actual = _object_to_dict(actual)

    if isinstance(actual, dict):
        # 3. OpenAI
        if "choices" in actual:
            return from_openai(actual)

        # 4. Anthropic (single message — NOT a list of Claude Agent SDK messages)
        content = actual.get("content")
        if (
            isinstance(content, list)
            and content
            and any(isinstance(b, dict) and "type" in b for b in content)
        ):
            return from_anthropic(actual)

        # 5. Gemini
        if "candidates" in actual:
            return from_gemini(actual)

        # 6. LangGraph state dict
        if _is_langgraph_result(actual):
            return _extract_langgraph_or_raise(actual)

        # 8. OpenAI Agents SDK dict
        if "new_items" in actual:
            return from_openai_agents(actual)

    # Handle list inputs that aren't already-formatted tool dicts
    if isinstance(actual, list) and actual:
        # 9. Claude Agent SDK: list of messages with tool_use content blocks
        if _is_claude_agent_sdk_list(actual):
            return from_claude_agent_sdk(actual)

        # 6. LangGraph: list of messages with tool_calls (scan all items, so a
        #    [human_msg, ai_msg_with_tool_calls] list is handled too).
        if _is_langgraph_message_list(actual):
            return _extract_langgraph_or_raise(actual)

    # 7. Pydantic AI on a plain object (after __dict__ path above, but dict
    #    conversion might have happened — check the original)
    if callable(getattr(actual, "all_messages", None)):
        return from_pydantic_ai(actual)

    raise TypeError(
        f"Cannot auto-detect provider format from {type(actual).__name__}. "
        "Pass a raw OpenAI/Anthropic/Gemini/LangGraph/PydanticAI/OpenAIAgents/"
        "ClaudeAgentSDK response, or a list of dicts with 'tool' and 'args' keys."
    )


def _object_to_dict(obj: Any) -> dict[str, Any]:
    """Recursively convert an object to a dict.

    Args:
        obj: Object to convert.

    Returns:
        Dict representation.
    """
    if isinstance(obj, dict):
        return {k: _object_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_object_to_dict(item) for item in obj]  # type: ignore[return-value]
    if hasattr(obj, "__dict__"):
        return {k: _object_to_dict(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    return obj  # type: ignore[no-any-return]
