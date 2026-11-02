"""Pydantic AI 2 runs, with the real Agent, FunctionModel and message classes (1.11).

Skipped when ``pydantic_ai`` is not installed. ``FunctionModel`` plays the
model, so nothing is sent anywhere.
"""

from __future__ import annotations

from typing import Any

import pytest

pydantic_ai = pytest.importorskip("pydantic_ai")

from pydantic_ai import Agent, ModelRetry  # noqa: E402
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart  # noqa: E402
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402

from toolscore import evaluate  # noqa: E402
from toolscore.integrations import auto_extract, from_pydantic_ai  # noqa: E402


@pytest.fixture(autouse=True)
def _no_banner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYDANTIC_AI_NO_BANNER", "1")


def _run(answer: str) -> Any:
    step = {"n": 0}

    def model(messages: list[Any], info: AgentInfo) -> ModelResponse:
        step["n"] += 1
        if step["n"] == 1:
            return ModelResponse(
                parts=[ToolCallPart("place_order", {"item": "mug"}, tool_call_id="c1")]
            )
        if step["n"] == 2:
            return ModelResponse(
                parts=[ToolCallPart("get_stock", '{"item": "mug"}', tool_call_id="c2")]
            )
        return ModelResponse(parts=[TextPart(answer)])

    agent = Agent(FunctionModel(model))

    @agent.tool_plain
    def place_order(item: str) -> str:
        raise ModelRetry("payment declined")

    @agent.tool_plain
    def get_stock(item: str) -> str:
        return f"{item}: 3 in stock"

    return agent.run_sync("Buy a mug")


def test_tool_returns_and_retries_are_paired_with_their_calls() -> None:
    run = _run("Done! Your mug is ordered.")
    calls = from_pydantic_ai(run)
    assert calls == [
        {
            "tool": "place_order",
            "args": {"item": "mug"},
            "id": "c1",
            "error": "retried: payment declined",
        },
        {"tool": "get_stock", "args": {"item": "mug"}, "id": "c2", "result": "mug: 3 in stock"},
    ]
    assert auto_extract(run) == calls
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    as_dicts = ModelMessagesTypeAdapter.dump_python(run.all_messages(), mode="json")
    assert [(c["tool"], "error" in c) for c in from_pydantic_ai(as_dicts)] == [
        ("place_order", True),
        ("get_stock", False),
    ]


def test_evaluate_reads_the_output_as_the_final_answer() -> None:
    result = evaluate(expected=[{"tool": "place_order"}], actual=_run("Done! Your mug is ordered."))
    assert result.false_success["claimed_success"] == 1
    honest = evaluate(
        expected=[{"tool": "place_order"}], actual=_run("The order failed: payment declined.")
    )
    assert honest.false_success["claimed_success"] == 0
