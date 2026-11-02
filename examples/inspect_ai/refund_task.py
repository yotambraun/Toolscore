"""An Inspect AI task scored by Toolscore, offline with Inspect's mockllm model.

Run it (no API key, no network; the mock model plays a scripted agent):

    pip install inspect-ai tool-scorer
    python examples/inspect_ai/refund_task.py

or with the Inspect CLI against a real model (costs money):

    inspect eval examples/inspect_ai/refund_task.py --model openai/gpt-6-luna
"""

from __future__ import annotations

import tempfile

from inspect_ai import Task, eval, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, get_model
from inspect_ai.solver import generate, use_tools
from inspect_ai.tool import ToolError, tool

from toolscore.inspect_scorer import toolscore_scorer

ORDERS = {"A-17": {"days_since_delivery": 45}, "B-02": {"days_since_delivery": 3}}


@tool
def issue_refund():  # type: ignore[no-untyped-def]  # Inspect reads the signature
    async def execute(order_id: str) -> str:
        """Refund an order.

        Args:
            order_id: The order to refund.
        """
        order = ORDERS.get(order_id)
        if order is None:
            raise ToolError(f"unknown order {order_id}")
        if order["days_since_delivery"] > 30:
            raise ToolError("refund window has closed (30 days)")
        return f"refund issued for {order_id}"

    return execute


@task
def refunds() -> Task:
    expected = {"required": [{"tool": "issue_refund", "args": {"order_id": "A-17"}}]}
    return Task(
        dataset=[
            Sample(id="late-order", input="Refund order A-17.", metadata={"toolscore": expected}),
            Sample(
                id="recent-order",
                input="Refund order B-02.",
                metadata={
                    "toolscore": {
                        "required": [{"tool": "issue_refund", "args": {"order_id": "B-02"}}]
                    }
                },
            ),
        ],
        solver=[use_tools(issue_refund()), generate()],
        scorer=toolscore_scorer(),
    )


def scripted_model():  # type: ignore[no-untyped-def]
    """A mock model: refund A-17 and claim it worked; refund B-02 and report it."""
    return get_model(
        "mockllm/model",
        custom_outputs=[
            ModelOutput.for_tool_call("mockllm/model", "issue_refund", {"order_id": "A-17"}),
            ModelOutput.from_content(
                "mockllm/model", "Done! Your refund for A-17 has been issued."
            ),
            ModelOutput.for_tool_call("mockllm/model", "issue_refund", {"order_id": "B-02"}),
            ModelOutput.from_content(
                "mockllm/model", "Done! Your refund for B-02 has been issued."
            ),
        ],
    )


if __name__ == "__main__":
    (log,) = eval(
        refunds(), model=scripted_model(), max_samples=1, display="none", log_dir=tempfile.mkdtemp()
    )
    assert log.results is not None
    for score in log.results.scores:
        for name, metric in score.metrics.items():
            print(f"{score.name} {name}: {metric.value:.2f}")
    for sample in log.samples or []:
        score = sample.scores["toolscore"]  # type: ignore[index]
        print(f"\n[{sample.id}] {score.value}")
        print(score.explanation)
