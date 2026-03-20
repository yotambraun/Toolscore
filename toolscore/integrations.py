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


def auto_extract(actual: Any) -> list[dict[str, Any]]:
    """Auto-detect the provider format of a response and extract tool calls.

    This allows passing raw OpenAI, Anthropic, or Gemini responses directly
    to ``evaluate()`` without manually calling ``from_openai()`` etc.

    Detection order:
    1. Already a list of dicts with ``"tool"`` keys → pass through
    2. Object with ``model_dump()`` → convert to dict, then re-detect
    3. Dict with ``"choices"`` → OpenAI format
    4. Dict with ``"content"`` list containing ``"type"`` keys → Anthropic format
    5. Dict with ``"candidates"`` → Gemini format

    Args:
        actual: A raw LLM provider response (object or dict), or an
            already-formatted list of tool-call dicts.

    Returns:
        List of dicts with 'tool' and 'args' keys.

    Raises:
        TypeError: If the format cannot be detected.
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
        actual = _object_to_dict(actual)

    if isinstance(actual, dict):
        # 3. OpenAI
        if "choices" in actual:
            return from_openai(actual)

        # 4. Anthropic
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

    raise TypeError(
        f"Cannot auto-detect provider format from {type(actual).__name__}. "
        "Pass a raw OpenAI/Anthropic/Gemini response, or a list of "
        "dicts with 'tool' and 'args' keys."
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
