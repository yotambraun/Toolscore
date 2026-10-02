"""Tests for rendering MCP tool-result content the way an MCP client shows it to a model."""

from __future__ import annotations

from toolscore.mcp.content import content_to_text


def test_text_items_are_joined_with_newlines() -> None:
    content = [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]

    assert content_to_text(content) == "first\nsecond"


def test_embedded_text_resource_keeps_its_body_and_uri() -> None:
    """Servers such as GitHub's return file contents as an embedded resource, not as text."""
    content = [
        {"type": "text", "text": "successfully downloaded text file"},
        {
            "type": "resource",
            "resource": {"uri": "repo://o/r/contents/notes.md", "text": "# Notes\nStatus: draft\n"},
        },
    ]

    assert content_to_text(content) == (
        "successfully downloaded text file\n[resource repo://o/r/contents/notes.md]\n# Notes\nStatus: draft\n"
    )


def test_binary_resource_image_and_audio_get_placeholders() -> None:
    content = [
        {
            "type": "resource",
            "resource": {"uri": "file:///logo.png", "blob": "aGVsbG8=", "mimeType": "image/png"},
        },
        {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"},
        {"type": "audio", "data": "aGVsbG8=", "mimeType": "audio/wav"},
    ]

    assert content_to_text(content) == (
        "[binary resource file:///logo.png (image/png)]\n[image (image/png)]\n[audio (audio/wav)]"
    )


def test_resource_link_is_rendered_with_uri_and_name() -> None:
    content = [{"type": "resource_link", "uri": "file:///report.pdf", "name": "report.pdf"}]

    assert content_to_text(content) == "[resource link file:///report.pdf report.pdf]"


def test_unknown_items_and_non_lists_are_tolerated() -> None:
    assert content_to_text([{"type": "future_type", "x": 1}, "not a dict", None]) == ""
    assert content_to_text(None) == ""
    assert content_to_text("plain string") == "plain string"
    assert content_to_text({"code": -32602, "message": "Unknown tool"}) == "Unknown tool"
