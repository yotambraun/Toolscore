"""Render MCP tool-result content the way an MCP client presents it to a model.

A ``tools/call`` result carries a list of content items, not a string. Servers
use several item types: plain ``text``, an embedded ``resource`` (text or binary
file contents, which is how servers such as GitHub's return a file), a
``resource_link``, ``image`` and ``audio``. Code that keeps only the ``text``
items silently drops everything else, so a model (or an evaluator) never sees a
file the server did return.

:func:`content_to_text` is the single place in Toolscore that turns a content
list into text. It is used by :attr:`toolscore.mcp.client.MCPToolResult.text`
and by :class:`toolscore.adapters.mcp.MCPAdapter`.
"""

from __future__ import annotations

from typing import Any


def _describe(kind: str, item: dict[str, Any]) -> str:
    """Return a ``[kind (mime)]`` placeholder for content that is not text."""
    mime = item.get("mimeType")
    return f"[{kind} ({mime})]" if mime else f"[{kind}]"


def _render_item(item: Any) -> str | None:
    """Render one content item, or return ``None`` for items with no text form."""
    if not isinstance(item, dict):
        return None
    kind = item.get("type")
    if kind == "text":
        return str(item.get("text", ""))
    if kind == "resource":
        resource = item.get("resource")
        if not isinstance(resource, dict):
            return None
        uri = resource.get("uri", "")
        if resource.get("text") is not None:
            return f"[resource {uri}]\n{resource['text']}"
        mime = resource.get("mimeType")
        return f"[binary resource {uri} ({mime})]" if mime else f"[binary resource {uri}]"
    if kind == "resource_link":
        return f"[resource link {item.get('uri', '')} {item.get('name', '')}]".replace(" ]", "]")
    if kind in ("image", "audio"):
        return _describe(kind, item)
    return None


def content_to_text(content: Any) -> str:
    """Render MCP ``content`` as the text an MCP client would give to a model.

    Args:
        content: The ``content`` value of a ``tools/call`` result (normally a
            list of content items). A plain string is returned unchanged, and a
            JSON-RPC error object yields its ``message``.

    Returns:
        One string. Items are joined with newlines in their original order:
        ``text`` as-is; an embedded text ``resource`` as ``[resource <uri>]``
        followed by its body; a binary resource, ``image`` or ``audio`` as a
        bracketed placeholder with its MIME type; a ``resource_link`` as
        ``[resource link <uri> <name>]``. Unknown item types are skipped.

    Example:
        >>> content_to_text([{"type": "text", "text": "ok"},
        ...                  {"type": "resource", "resource": {"uri": "file:///a.md", "text": "# A"}}])
        'ok\\n[resource file:///a.md]\\n# A'
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        message = content.get("message")
        return str(message) if message is not None else ""
    if not isinstance(content, list):
        return ""
    parts = [
        rendered for rendered in (_render_item(item) for item in content) if rendered is not None
    ]
    return "\n".join(parts)
