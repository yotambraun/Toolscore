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
