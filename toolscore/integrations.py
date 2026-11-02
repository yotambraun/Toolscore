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


#: Responses API item types that are calls of a named tool.
_RESPONSES_CALL_TYPES = frozenset({"function_call", "mcp_call", "custom_tool_call"})
#: Responses API item types that carry a tool's output back to the model.
_RESPONSES_OUTPUT_TYPES = frozenset({"function_call_output", "custom_tool_call_output"})

# The OpenAI Agents SDK's default tool error handler returns this text as the
# function_call_output when a tool raises.
_AGENTS_SDK_TOOL_ERROR = "An error occurred while running the tool"


def _item_dict(item: Any) -> dict[str, Any]:
    """A Responses item (SDK model or dict) as a plain dict."""
    if isinstance(item, dict):
        return item
    try:
        if hasattr(item, "model_dump"):
            dumped = item.model_dump()
            return dumped if isinstance(dumped, dict) else {}
        if hasattr(item, "__dict__"):
            return _object_to_dict(item)
    except Exception:  # an object we cannot convert is simply not a Responses item
        return {}
    return {}


def _responses_items(response: Any) -> list[dict[str, Any]]:
    """The item list of a Response object/dict, its ``output``, or an input list."""
    if isinstance(response, list):
        return [_item_dict(i) for i in response]
    data = _item_dict(response)
    output = data.get("output")
    return [_item_dict(i) for i in output] if isinstance(output, list) else []


def _is_responses_payload(data: Any) -> bool:
    """Whether ``data`` looks like a Responses API response or item list."""
    if isinstance(data, dict):
        if data.get("object") == "response":
            return True
        items = data.get("output")
    else:
        items = data
    if not isinstance(items, list) or not items:
        return False
    return any(
        isinstance(i, dict) and i.get("type") in (_RESPONSES_CALL_TYPES | _RESPONSES_OUTPUT_TYPES)
        for i in items
    )


def _output_error(output: Any) -> str | None:
    """An error message carried by a tool output, if it clearly is one."""
    text = output if isinstance(output, str) else None
    if text is not None:
        if text.startswith(_AGENTS_SDK_TOOL_ERROR):
            return text
        try:
            output = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(output, dict):
        if output.get("is_error") is True or output.get("isError") is True:
            return str(output.get("error") or output.get("message") or "tool reported an error")
        error = output.get("error")
        if error:
            return error if isinstance(error, str) else json.dumps(error)
    return None


def _error_text(error: Any) -> str:
    """Readable text for an ``mcp_call`` error (a string, or a typed error object)."""
    if isinstance(error, dict):
        if error.get("message"):
            return str(error["message"])
        content = error.get("content")
        if isinstance(content, list):
            texts = [c.get("text", "") for c in content if isinstance(c, dict)]
            if any(texts):
                return " ".join(t for t in texts if t)
        return json.dumps(error)
    return str(error)


def from_openai_responses(response: Any) -> list[dict[str, Any]]:
    """Extract tool calls from an OpenAI Responses API response or item list.

    Accepts an ``openai.types.responses.Response`` (or its dict form), its
    ``output`` list, or the input item list of a multi-turn conversation.

    Handles:

    - ``function_call`` items (``name`` + JSON ``arguments``),
    - ``mcp_call`` items (remote MCP tools; their ``output`` and ``error`` are kept),
    - ``custom_tool_call`` items (free-form ``input``, kept as ``{"input": ...}``).

    When the list also holds ``function_call_output`` /
    ``custom_tool_call_output`` items, each output is attached to its call (by
    ``call_id``) as ``result``. An output is recorded as an ``error`` only when
    it clearly is one: a JSON object with ``error`` or ``is_error: true``, or the
    OpenAI Agents SDK's "An error occurred while running the tool" message.
    Built-in tool items (web search, file search, code interpreter, ...) have no
    tool name and arguments and are skipped.

    Args:
        response: A Responses API response (object or dict) or a list of items.

    Returns:
        List of dicts with ``tool``, ``args`` and, when known, ``id``,
        ``result`` and ``error``.
    """
    items = _responses_items(response)
    outputs: dict[str, Any] = {}
    for item in items:
        if item.get("type") in _RESPONSES_OUTPUT_TYPES and item.get("call_id"):
            outputs[str(item["call_id"])] = item.get("output")

    calls: list[dict[str, Any]] = []
    for item in items:
        kind = item.get("type")
        name = item.get("name")
        if kind not in _RESPONSES_CALL_TYPES or not name:
            continue
        if kind == "custom_tool_call":
            args: Any = {"input": item.get("input", "")}
        else:
            args = item.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except (json.JSONDecodeError, TypeError):
                    args = {"raw": args}
        call: dict[str, Any] = {"tool": str(name), "args": args if args is not None else {}}
        call_id = item.get("call_id") or item.get("id")
        if call_id:
            call["id"] = str(call_id)
        if kind == "mcp_call":
            if item.get("output") is not None:
                call["result"] = item["output"]
            if item.get("error"):
                call["error"] = _error_text(item["error"])
        elif call_id and str(call_id) in outputs:
            output = outputs[str(call_id)]
            call["result"] = output
            error = _output_error(output)
            if error:
                call["error"] = error
        calls.append(call)
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


#: Claude Agent SDK block and message classes (dataclasses without a ``type`` field).
_CLAUDE_SDK_BLOCK_KINDS = {
    "ToolUseBlock": "tool_use",
    "ToolResultBlock": "tool_result",
    "TextBlock": "text",
    "ThinkingBlock": "thinking",
    "ServerToolUseBlock": "server_tool_use",
    "ServerToolResultBlock": "server_tool_result",
}
_CLAUDE_SDK_MESSAGES = {"AssistantMessage": "assistant", "UserMessage": "user"}


def _claude_sdk_block(block: Any) -> dict[str, Any] | None:
    """A content block (dict or Claude Agent SDK dataclass) as an Anthropic-style dict."""
    if isinstance(block, dict):
        return block
    kind = getattr(block, "type", None) or _CLAUDE_SDK_BLOCK_KINDS.get(type(block).__name__)
    if not isinstance(kind, str):
        return None
    data = {k: v for k, v in vars(block).items() if not k.startswith("_")}
    data["type"] = kind
    return data


def claude_agent_sdk_messages(result: Any) -> list[dict[str, Any]]:
    """Claude Agent SDK messages (dataclasses or dicts) as Anthropic-style message dicts.

    ``AssistantMessage`` and ``UserMessage`` become ``{"role", "content"}`` dicts
    with typed blocks; a ``ResultMessage`` becomes ``{"type": "result",
    "result", "is_error", "session_id"}``, where the final answer is. Other
    messages (system, task progress, stream events) are dropped.

    Args:
        result: The messages ``query()`` or ``ClaudeSDKClient.receive_response()`` yielded.

    Returns:
        The message dicts, in order.
    """
    if not isinstance(result, list):
        return []
    messages: list[dict[str, Any]] = []
    for msg in result:
        if isinstance(msg, dict):
            messages.append(msg)
            continue
        name = type(msg).__name__
        if name == "ResultMessage":
            messages.append(
                {
                    "type": "result",
                    "result": getattr(msg, "result", None),
                    "is_error": getattr(msg, "is_error", None),
                    "session_id": getattr(msg, "session_id", None),
                }
            )
            continue
        role = getattr(msg, "role", None) or _CLAUDE_SDK_MESSAGES.get(name)
        content = getattr(msg, "content", None)
        if role is None or content is None:
            continue
        if isinstance(content, list):
            blocks = [b for b in (_claude_sdk_block(x) for x in content) if b is not None]
            messages.append({"role": role, "content": blocks})
        else:
            messages.append({"role": role, "content": content})
    return messages


def from_claude_agent_sdk(result: Any) -> list[dict[str, Any]]:
    """Extract tool calls from a Claude Agent SDK message list.

    Accepts the messages ``query()`` yields (``AssistantMessage``,
    ``UserMessage``, ``ResultMessage`` dataclasses, whose blocks carry no
    ``type`` field) or their dict form. Each ``tool_use`` block (``ToolUseBlock``)
    is a call; the ``tool_result`` block (``ToolResultBlock``) with the same ID
    gives its ``result``, and ``is_error: true`` makes it failed.

    Args:
        result: A list of Claude Agent SDK messages (dataclasses or dicts).

    Returns:
        List of dicts with ``tool``, ``args`` and, when known, ``id``,
        ``result`` and ``error``.
    """
    from toolscore.adapters.anthropic import block_text

    calls: list[dict[str, Any]] = []
    by_id: dict[Any, dict[str, Any]] = {}
    for msg in claude_agent_sdk_messages(result):
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            block = _claude_sdk_block(block)
            if block is None:
                continue
            if block.get("type") == "tool_use" and block.get("name"):
                args = block.get("input")
                call: dict[str, Any] = {
                    "tool": block["name"],
                    "args": args if isinstance(args, dict) else {},
                }
                if block.get("id") is not None:
                    call["id"] = block["id"]
                    by_id[block["id"]] = call
                calls.append(call)
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in by_id:
                target = by_id[block["tool_use_id"]]
                output = block.get("content")
                if block.get("is_error") is True:
                    text = block_text(output) if isinstance(output, list) else output
                    target["error"] = str(text) if text else True
                else:
                    target["result"] = output
    return calls


def from_otel(spans: Any) -> list[dict[str, Any]]:
    """Extract tool calls from OpenTelemetry GenAI tool spans.

    Works with any framework or platform that records tool executions with the
    OpenTelemetry semantic conventions for generative AI (``execute_tool`` spans)
    or for MCP (``tools/call`` spans). Pass an OTLP JSON export
    (``{"resourceSpans": [...]}``), a list of span dicts, or a list of
    OpenTelemetry SDK span objects (for example from an ``InMemorySpanExporter``).

    Args:
        spans: The exported spans.

    Returns:
        One dict per tool span, in start-time order, with ``tool``, ``args``,
        ``result``, ``is_error``, ``error``, ``duration`` and ``id``. Failures
        come from ``error.type`` or an ERROR span status.

    Example:
        >>> from toolscore import evaluate, from_otel
        >>> result = evaluate(expected=[{"tool": "search_orders"}], actual=from_otel(otlp_export))
    """
    from toolscore.adapters.otel import tool_calls_from_otel

    return tool_calls_from_otel(spans)


def _browser_use_data(history: Any) -> Any:
    """A browser-use history as plain data: ``model_dump()`` objects, step objects, or as is."""
    if isinstance(history, (dict, str)):
        return json.loads(history) if isinstance(history, str) else history
    if hasattr(history, "model_dump") and not isinstance(history, list):
        return history.model_dump()
    if isinstance(history, list):
        return [h.model_dump() if hasattr(h, "model_dump") else h for h in history]
    return history


def from_browser_use(history: Any) -> list[dict[str, Any]]:
    """Extract the executed actions of a browser-use agent run as tool calls.

    Accepts an ``AgentHistoryList`` (what ``await agent.run()`` returns), its
    ``model_dump()`` dict, the JSON text ``history.save_to_file()`` writes, or
    a list of ``AgentHistory`` steps (objects or dicts). Each executed action
    is one call: ``tool`` is the action name (``click``, ``input``,
    ``evaluate``, ``done``...), ``args`` its parameters, ``result`` the action
    result's ``extracted_content`` and ``error`` its ``error``; actions that
    browser-use skipped after an error or a page change have no result and are
    left out. See :mod:`toolscore.adapters.browser_use`.

    Args:
        history: The browser-use history.

    Returns:
        List of dicts with ``tool``, ``args``, ``result``, ``id``, ``timestamp``,
        ``duration``, failure fields and ``metadata`` (step, url, and
        ``is_done`` / ``success`` on the ``done`` call).

    Raises:
        ValueError: If ``history`` is not a browser-use history.

    Example:
        >>> history = await agent.run()
        >>> result = evaluate(expected=[...], actual=from_browser_use(history))
    """
    from toolscore.adapters.browser_use import browser_use_calls
    from toolscore.core import _tool_call_dict

    calls = []
    for call in browser_use_calls(_browser_use_data(history)):
        item = _tool_call_dict(call)
        item["id"] = call.id
        if call.is_error:
            item["error"] = call.metadata.get("error")
        calls.append(item)
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


def _field(item: Any, name: str) -> Any:
    """``item[name]`` for a dict, ``item.name`` otherwise (``None`` when absent)."""
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


def _is_pydantic_ai_message_list(actual: list[Any]) -> bool:
    """Whether a list holds Pydantic AI messages with at least one tool-call part."""
    for msg in actual:
        parts = msg.get("parts") if isinstance(msg, dict) else getattr(msg, "parts", None)
        if not isinstance(parts, list):
            continue
        for part in parts:
            kind = (
                part.get("part_kind")
                if isinstance(part, dict)
                else getattr(part, "part_kind", None)
            )
            if kind == "tool-call" or type(part).__name__ == "ToolCallPart":
                return True
    return False


def _is_claude_agent_sdk_list(actual: Any) -> bool:
    """Return True if *actual* looks like a list of Claude Agent SDK messages."""
    if not isinstance(actual, list) or not actual:
        return False
    if any(
        type(item).__name__ in _CLAUDE_SDK_MESSAGES
        and any(type(b).__name__ == "ToolUseBlock" for b in (getattr(item, "content", None) or []))
        for item in actual
    ):
        return True
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
    3. Dict with ``"choices"`` → OpenAI Chat Completions; a Responses API response (``object == "response"`` or ``function_call`` / ``mcp_call`` items in ``output``) or item list → :func:`from_openai_responses`
    4. Dict with ``"content"`` list containing ``"type"`` keys → Anthropic format
    5. Dict with ``"candidates"`` → Gemini format
    6. Dict/object with ``"messages"`` where some message has ``tool_calls`` → LangGraph
    7. Object with callable ``all_messages`` → Pydantic AI
    8. Object/dict with ``new_items`` → OpenAI Agents SDK
    9. List whose items have content blocks with ``type == "tool_use"`` → Claude Agent SDK; a list of Pydantic AI messages, OpenAI Agents SDK ``tool_call_item`` items, or CrewAI ``tool_name``/``tool_args`` entries → that framework's extractor
    10. Bare list of messages where some message has ``tool_calls`` → LangGraph

    OpenTelemetry GenAI tool spans (an OTLP export with ``resourceSpans``, or a
    span list containing ``execute_tool`` / MCP ``tools/call`` spans) and
    browser-use histories (an ``AgentHistoryList``, its dump or its step list)
    are detected before step 2 and converted with :func:`from_otel` and
    :func:`from_browser_use`.

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

    # OpenTelemetry GenAI spans (OTLP export, span dicts or SDK span objects)
    from toolscore.adapters.otel import looks_like_otel

    if looks_like_otel(actual):
        return from_otel(actual)

    # browser-use histories (AgentHistoryList, its dump, or its step list)
    from toolscore.adapters.browser_use import looks_like_browser_use

    if looks_like_browser_use(actual) or (
        hasattr(actual, "history")
        and hasattr(actual, "model_dump")
        and looks_like_browser_use(_browser_use_data(actual))
    ):
        return from_browser_use(actual)

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
        # 3. OpenAI (Chat Completions, then the Responses API)
        if "choices" in actual:
            return from_openai(actual)
        if _is_responses_payload(actual):
            return from_openai_responses(actual)

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
        # 3b. OpenAI Responses API item list (function_call / mcp_call items)
        if any(
            _field(i, "type") in _RESPONSES_CALL_TYPES | _RESPONSES_OUTPUT_TYPES for i in actual
        ):
            items = [_item_dict(i) for i in actual]
            if _is_responses_payload(items):
                return from_openai_responses(items)

        # 7b. Pydantic AI message list (messages whose parts include tool calls)
        if _is_pydantic_ai_message_list(actual):
            return from_pydantic_ai(actual)

        # 8b. OpenAI Agents SDK item list, CrewAI tool-result list
        if any(_field(i, "type") == "tool_call_item" for i in actual):
            return from_openai_agents(actual)
        if all(isinstance(_field(i, "tool_name"), str) for i in actual):
            return from_crewai(actual)

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
        "Pass a raw OpenAI (Chat Completions or Responses)/Anthropic/Gemini/LangGraph/"
        "PydanticAI/OpenAIAgents/ClaudeAgentSDK response, or a list of dicts with 'tool' "
        "and 'args' keys."
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
