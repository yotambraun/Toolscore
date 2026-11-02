"""Agent harness: run an LLM agent against an MCP server, and record what happened.

Toolscore checks tools and traces; to get traces from a real model, something
has to run the agent loop. This module is that loop, for MCP servers (stdio or
Streamable HTTP, through the existing clients) and two provider APIs: the
OpenAI Responses API and Anthropic Messages. A scripted provider replays fixed
model turns for offline tests and examples.

One **run** is one task, one arm (provider, model, system prompt) and one
repetition. :func:`run_agent` runs one on a started client; :func:`run_study`
runs every cell of a spec (tasks x arms x repetitions) in a shuffled order with
a fixed seed and appends one JSONL row per run, so an interrupted study resumes
where it stopped.

Safety and cost:

* **Guard.** ``guard(call) -> allow() | deny(reason)`` runs before every tool
  call. A denied call never reaches the server: the agent gets a tool error
  ("denied by the harness guard: ...") and the row lists it under
  ``guard_denials``. Declarative guards (``deny`` rules in the forbidden-call
  format, an ``allow_tools`` list) are built in.
* **Budget, checked before every model call.** The spent cost (the provider's
  reported token usage times the price from :mod:`toolscore.metrics.cost_estimator`
  or the spec) plus a worst case for the next call (the conversation so far,
  estimated, plus ``max_output_tokens``) must stay under ``max_usd``, or the
  run stops with ``budget_stopped`` and the study stops. A model without a known
  price is refused before any call unless ``allow_unknown_price`` is set; its
  cost is then ``null`` (unknown), never 0.
* **Limits.** ``max_turns`` model calls and ``max_calls`` tool calls per run.
* **Build verification.** Each row records the server's ``serverInfo`` name and
  version and the protocol; ``verify`` in the spec checks them (and can run a
  command whose output must match) and refuses the study on a mismatch, so a
  result is never attributed to the wrong build.

Each row carries the calls (id, arguments, result, error, duration, denied),
the final answer, token usage, cost, guard denials, server info, protocol and,
when the task declares expected or forbidden calls, the Toolscore evaluation
with the honesty checks and tri-state evidence. ``outcome`` is ``pass``,
``fail``, ``error`` or ``unknown`` (a task with nothing to check), ready for
``toolscore compare --runs``.

Provider SDKs are optional extras (``tool-scorer[llm]`` for OpenAI,
``tool-scorer[anthropic]``); tests pass fake clients and never call a model.
"""

from __future__ import annotations

import fnmatch
import importlib
import json
import os
import random
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from toolscore.mcp.content import content_to_text

if TYPE_CHECKING:
    from collections.abc import Callable

    from toolscore.mcp.client import MCPClient, MCPToolDef

#: Layout version of a run row.
RUN_RECORD_VERSION = "1"
#: Layout version of an agent spec.
SPEC_VERSION = 1

#: Characters of a tool result kept in a run row (results are also hashed in exports).
RESULT_CHARS = 20_000


# -- tool mapping --------------------------------------------------------------------


_PROVIDER_NAME = re.compile(r"[^A-Za-z0-9_-]")


@dataclass
class ProviderTool:
    """An MCP tool as offered to a model.

    Attributes:
        name: The name the model sees (provider-safe: letters, digits, ``_``,
            ``-``; at most 64 characters).
        mcp_name: The MCP tool name the call goes to.
        description: The tool description.
        parameters: The JSON Schema of the arguments.
    """

    name: str
    mcp_name: str
    description: str
    parameters: dict[str, Any]


def map_tools(tools: list[MCPToolDef], allow: list[str] | None = None) -> list[ProviderTool]:
    """MCP tools -> provider function tools, with safe, unique names.

    Args:
        tools: The server's tools.
        allow: Glob patterns of tools to offer (all when ``None``).

    Returns:
        The tools, in server order.
    """
    mapped: list[ProviderTool] = []
    used: set[str] = set()
    for tool in tools:
        if allow is not None and not any(fnmatch.fnmatchcase(tool.name, p) for p in allow):
            continue
        base = _PROVIDER_NAME.sub("_", tool.name)[:64] or "tool"
        name, suffix = base, 2
        while name in used:
            tail = f"_{suffix}"
            name = base[: 64 - len(tail)] + tail
            suffix += 1
        used.add(name)
        # Providers need an object schema; a server that declares none (or no
        # type) gets an empty object schema, keeping any properties it lists.
        schema = dict(tool.input_schema) if isinstance(tool.input_schema, dict) else {}
        schema["type"] = "object"
        schema.setdefault("properties", {})
        mapped.append(ProviderTool(name, tool.name, tool.description or "", schema))
    return mapped


# -- providers ------------------------------------------------------------------------


@dataclass
class ToolRequest:
    """A tool call the model asked for.

    Attributes:
        id: The provider's call ID (OpenAI ``call_id``, Anthropic ``tool_use`` ID).
        name: The provider-side tool name.
        arguments: The parsed arguments (``{}`` if they did not parse).
        argument_error: Why the arguments did not parse, or ``""``.
    """

    id: str
    name: str
    arguments: dict[str, Any]
    argument_error: str = ""


@dataclass
class ModelTurn:
    """One model response.

    Attributes:
        text: The text the model wrote (its answer, when it calls no tool).
        requests: The tool calls it asked for.
        input_tokens: Input tokens the provider reported, or ``None``.
        output_tokens: Output tokens the provider reported, or ``None``.
    """

    text: str
    requests: list[ToolRequest]
    input_tokens: int | None = None
    output_tokens: int | None = None


class ModelProvider(Protocol):
    """A conversation with one model. One instance per run.

    ``start`` sets up the conversation, ``complete`` asks the model for its
    next turn, ``add_results`` gives it the tool results, and
    ``estimated_input_tokens`` sizes the next request for the budget check.
    """

    provider: str
    model: str
    max_output_tokens: int

    def start(self, system: str | None, prompt: str, tools: list[ProviderTool]) -> None:
        """Begin the conversation."""

    def complete(self) -> ModelTurn:
        """Ask the model for its next turn."""

    def add_results(self, turn: ModelTurn, results: list[tuple[ToolRequest, str, bool]]) -> None:
        """Append the model's turn and the results of its tool calls."""

    def estimated_input_tokens(self) -> int:
        """An estimate of the next request's input tokens."""


def _parse_arguments(raw: Any) -> tuple[dict[str, Any], str]:
    if isinstance(raw, dict):
        return raw, ""
    if raw in (None, ""):
        return {}, ""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        return {}, f"arguments are not JSON: {exc}"
    return (value, "") if isinstance(value, dict) else ({}, "arguments are not a JSON object")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """``obj[key]`` for dicts, ``obj.key`` for SDK objects."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _plain(obj: Any) -> Any:
    """An SDK object as plain JSON data (``model_dump``), dicts and lists as they are."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    if isinstance(obj, list):
        return [_plain(item) for item in obj]
    return obj


def _estimate(value: Any) -> int:
    from toolscore.metrics.cost_estimator import estimate_tokens

    return estimate_tokens(json.dumps(value, default=str))


class OpenAIResponsesProvider:
    """The OpenAI Responses API (``client.responses.create``).

    Args:
        client: An ``openai.OpenAI()`` client (or anything with ``responses.create``).
        model: The model ID.
        max_output_tokens: ``max_output_tokens`` per request (also the budget's worst case).
        extra: Extra request parameters (``reasoning``, ``temperature``...).
    """

    provider = "openai"

    def __init__(
        self,
        client: Any,
        model: str,
        max_output_tokens: int = 1024,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.extra = dict(extra or {})
        self._input: list[Any] = []
        self._tools: list[dict[str, Any]] = []
        self._system: str | None = None

    def start(self, system: str | None, prompt: str, tools: list[ProviderTool]) -> None:
        self._system = system
        self._input = [{"role": "user", "content": prompt}]
        self._tools = [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "strict": False,
            }
            for t in tools
        ]

    def complete(self) -> ModelTurn:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": self._input,
            "max_output_tokens": self.max_output_tokens,
            **self.extra,
        }
        if self._tools:
            kwargs["tools"] = self._tools
        if self._system:
            kwargs["instructions"] = self._system
        response = self.client.responses.create(**kwargs)
        output = list(_get(response, "output", []) or [])
        texts: list[str] = []
        requests: list[ToolRequest] = []
        for item in output:
            kind = _get(item, "type")
            if kind == "function_call":
                arguments, error = _parse_arguments(_get(item, "arguments"))
                requests.append(
                    ToolRequest(
                        str(_get(item, "call_id") or _get(item, "id") or ""),
                        str(_get(item, "name", "")),
                        arguments,
                        error,
                    )
                )
            elif kind == "message":
                for part in _get(item, "content", []) or []:
                    if _get(part, "type") in ("output_text", "text"):
                        texts.append(str(_get(part, "text", "")))
        usage = _get(response, "usage")
        self._pending = [_plain(item) for item in output]
        return ModelTurn(
            "\n".join(t for t in texts if t),
            requests,
            _get(usage, "input_tokens") if usage is not None else None,
            _get(usage, "output_tokens") if usage is not None else None,
        )

    def add_results(self, turn: ModelTurn, results: list[tuple[ToolRequest, str, bool]]) -> None:
        del turn
        self._input.extend(getattr(self, "_pending", []))
        self._pending = []
        for request, text, _is_error in results:
            self._input.append(
                {"type": "function_call_output", "call_id": request.id, "output": text}
            )

    def estimated_input_tokens(self) -> int:
        return _estimate([self._system, self._input, self._tools])


class AnthropicMessagesProvider:
    """Anthropic Messages (``client.messages.create``).

    Args:
        client: An ``anthropic.Anthropic()`` client (or anything with ``messages.create``).
        model: The model ID.
        max_output_tokens: ``max_tokens`` per request (also the budget's worst case).
        extra: Extra request parameters.
    """

    provider = "anthropic"

    def __init__(
        self,
        client: Any,
        model: str,
        max_output_tokens: int = 1024,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.extra = dict(extra or {})
        self._messages: list[dict[str, Any]] = []
        self._tools: list[dict[str, Any]] = []
        self._system: str | None = None
        self._content: list[Any] = []

    def start(self, system: str | None, prompt: str, tools: list[ProviderTool]) -> None:
        self._system = system
        self._messages = [{"role": "user", "content": prompt}]
        self._tools = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]

    def complete(self) -> ModelTurn:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "messages": self._messages,
            **self.extra,
        }
        if self._tools:
            kwargs["tools"] = self._tools
        if self._system:
            kwargs["system"] = self._system
        response = self.client.messages.create(**kwargs)
        content = list(_get(response, "content", []) or [])
        texts: list[str] = []
        requests: list[ToolRequest] = []
        for block in content:
            kind = _get(block, "type")
            if kind == "text":
                texts.append(str(_get(block, "text", "")))
            elif kind == "tool_use":
                arguments, error = _parse_arguments(_get(block, "input"))
                requests.append(
                    ToolRequest(
                        str(_get(block, "id", "")), str(_get(block, "name", "")), arguments, error
                    )
                )
        self._content = [_plain(block) for block in content]
        usage = _get(response, "usage")
        return ModelTurn(
            "\n".join(t for t in texts if t),
            requests,
            _get(usage, "input_tokens") if usage is not None else None,
            _get(usage, "output_tokens") if usage is not None else None,
        )

    def add_results(self, turn: ModelTurn, results: list[tuple[ToolRequest, str, bool]]) -> None:
        del turn
        self._messages.append({"role": "assistant", "content": self._content})
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": request.id,
                        "content": text,
                        "is_error": is_error,
                    }
                    for request, text, is_error in results
                ],
            }
        )

    def estimated_input_tokens(self) -> int:
        return _estimate([self._system, self._messages, self._tools])


class ScriptedProvider:
    """Replays fixed model turns: for offline tests, examples and dry runs. Costs nothing.

    Each step is ``{"calls": [{"tool": MCP_NAME, "args": {...}}], "text": "..."}``
    (``calls`` optional). A step without calls ends the run with its ``text`` as
    the final answer. Usage is reported from ``input_tokens`` / ``output_tokens``
    in a step, else estimated.

    Args:
        script: The steps.
        model: A model label for the rows (``"scripted"``).
    """

    provider = "scripted"

    def __init__(self, script: list[dict[str, Any]], model: str = "scripted") -> None:
        self.script = list(script)
        self.model = model
        self.max_output_tokens = 0
        self._step = 0
        self._names: dict[str, str] = {}
        self._seen = 0

    def start(self, system: str | None, prompt: str, tools: list[ProviderTool]) -> None:
        del system, prompt
        self._names = {t.mcp_name: t.name for t in tools}
        self._step = 0

    def complete(self) -> ModelTurn:
        if self._step >= len(self.script):
            return ModelTurn("", [], 0, 0)
        step = self.script[self._step]
        self._step += 1
        requests = []
        for call in step.get("calls") or []:
            self._seen += 1
            tool = str(call.get("tool", ""))
            requests.append(
                ToolRequest(
                    str(call.get("id") or f"call_{self._seen}"),
                    self._names.get(tool, tool),
                    dict(call.get("args") or {}),
                )
            )
        return ModelTurn(
            str(step.get("text", "")),
            requests,
            step.get("input_tokens", 0),
            step.get("output_tokens", 0),
        )

    def add_results(self, turn: ModelTurn, results: list[tuple[ToolRequest, str, bool]]) -> None:
        del turn, results

    def estimated_input_tokens(self) -> int:
        return 0


# -- guard -------------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardCall:
    """A tool call about to be made, as a guard sees it."""

    tool: str
    arguments: dict[str, Any]
    task_id: str = ""
    arm_id: str = ""
    index: int = 0


@dataclass(frozen=True)
class GuardDecision:
    """What a guard decided: ``allowed``, and the ``reason`` for a denial."""

    allowed: bool
    reason: str = ""


def allow() -> GuardDecision:
    """Let the call through."""
    return GuardDecision(True)


def deny(reason: str) -> GuardDecision:
    """Block the call; the agent gets a tool error with ``reason``."""
    return GuardDecision(False, reason)


def rules_guard(
    deny_rules: list[dict[str, Any]] | None = None, allow_tools: list[str] | None = None
) -> Callable[[GuardCall], GuardDecision]:
    """A declarative guard.

    Args:
        deny_rules: Forbidden-call rules (``tool``, optional ``args`` with
            values or ``$regex`` / ``$contains`` / ``$one_of`` matchers,
            optional ``reason``), as for ``toolscore eval --forbidden``.
        allow_tools: Glob patterns of tools that may be called (all when ``None``).

    Returns:
        The guard.
    """
    from toolscore.metrics.policy import call_matches_rule, rules_from_json

    rules = rules_from_json(deny_rules or [])

    def guard(call: GuardCall) -> GuardDecision:
        if allow_tools is not None and not any(
            fnmatch.fnmatchcase(call.tool, p) for p in allow_tools
        ):
            return deny(f"{call.tool} is not in allow_tools")
        for rule in rules:
            if call_matches_rule(call.tool, call.arguments, rule):
                return deny(str(rule.get("reason") or f"forbidden call to {call.tool}"))
        return allow()

    return guard


def _decide(guard: Any, call: GuardCall) -> GuardDecision:
    if guard is None:
        return allow()
    decision = guard(call)
    if decision is None or decision is True:
        return allow()
    if decision is False:
        return deny("denied by guard")
    if isinstance(decision, GuardDecision):
        return decision
    raise TypeError(f"a guard must return allow(), deny(reason), a bool or None, got {decision!r}")


# -- budget --------------------------------------------------------------------------------


class UnknownPriceError(ValueError):
    """A model has no known price and ``allow_unknown_price`` is not set."""


@dataclass
class Price:
    """USD per 1M input and output tokens, and where the price came from."""

    input: float
    output: float
    source: str


def price_for(model: str, pricing: dict[str, Any] | None = None) -> Price | None:
    """The price of a model: ``pricing`` from the spec, else the built-in table, else ``None``."""
    from toolscore.metrics.cost_estimator import PRICES_VERIFIED_ON, lookup_pricing

    if pricing and "input" in pricing and "output" in pricing:
        return Price(float(pricing["input"]), float(pricing["output"]), "spec")
    found = lookup_pricing(model)
    if found is None:
        return None
    return Price(found[0], found[1], f"toolscore price table ({PRICES_VERIFIED_ON})")


@dataclass
class Budget:
    """A hard cost cap, shared by every run it is given to.

    Attributes:
        max_usd: The cap in USD (``None``: no cap, costs are still recorded).
        allow_unknown_price: Run models without a known price (their cost is
            unknown, and the cap cannot be enforced for them).
        spent_usd: Cost so far, from reported usage.
        unknown_cost_turns: Model calls whose cost is unknown.
    """

    max_usd: float | None = None
    allow_unknown_price: bool = False
    spent_usd: float = 0.0
    unknown_cost_turns: int = 0

    def turn_cost(self, price: Price | None, turn: ModelTurn) -> float | None:
        """The cost of one turn, or ``None`` when the price or the usage is unknown."""
        if price is None or turn.input_tokens is None or turn.output_tokens is None:
            return None
        return (turn.input_tokens * price.input + turn.output_tokens * price.output) / 1_000_000

    def projected(self, price: Price, provider: ModelProvider) -> float:
        """Spent so far plus the worst case of the next request."""
        worst = (
            provider.estimated_input_tokens() * price.input
            + provider.max_output_tokens * price.output
        ) / 1_000_000
        return self.spent_usd + worst

    def allows(self, price: Price | None, provider: ModelProvider) -> bool:
        """Whether the next model call fits under the cap."""
        if self.max_usd is None or price is None:
            return True
        return self.projected(price, provider) <= self.max_usd


@dataclass
class Limits:
    """Per-run limits: model calls (``max_turns``) and tool calls (``max_calls``)."""

    max_turns: int = 10
    max_calls: int = 20


# -- one run ---------------------------------------------------------------------------------


@dataclass
class CallRecord:
    """One tool call of a run: what was requested and what came back."""

    id: str
    tool: str
    provider_name: str
    args: dict[str, Any]
    result: str | None = None
    structured: Any = None
    is_error: bool = False
    error: str | None = None
    duration: float | None = None
    denied: bool = False
    deny_reason: str | None = None


@dataclass
class AgentRun:
    """The outcome of :func:`run_agent`.

    Attributes:
        status: ``"completed"`` (the model gave a final answer),
            ``"limit_reached"``, ``"budget_stopped"`` or ``"error"``.
        calls: Every tool call the model asked for, in order.
        final_answer: The model's last text, or ``None``.
        turns: Model calls made.
        input_tokens: Reported input tokens (``None`` if a turn did not report).
        output_tokens: Reported output tokens.
        cost_usd: Cost of the run, or ``None`` when unknown.
        stop_reason: Why the run stopped.
        error: The error, for ``status == "error"``.
        duration_s: Wall-clock seconds.
    """

    status: str
    calls: list[CallRecord]
    final_answer: str | None
    turns: int
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    stop_reason: str
    error: str | None = None
    duration_s: float = 0.0

    @property
    def guard_denials(self) -> list[dict[str, Any]]:
        """The denied calls: ``id``, ``tool``, ``args``, ``reason``."""
        return [
            {"id": c.id, "tool": c.tool, "args": c.args, "reason": c.deny_reason}
            for c in self.calls
            if c.denied
        ]

    def trace(self) -> list[dict[str, Any]]:
        """The calls as Toolscore trace dicts (denied calls are failed calls)."""
        return [
            {
                "id": c.id,
                "tool": c.tool,
                "args": c.args,
                "result": c.result,
                "duration": c.duration,
                **({"error": c.error} if c.is_error and c.error else {}),
                "is_error": c.is_error,
            }
            for c in self.calls
        ]


def _result_text(result: Any) -> str:
    text = content_to_text(result.content) if result is not None else ""
    return text if len(text) <= RESULT_CHARS else text[:RESULT_CHARS] + "\n[truncated by toolscore]"


def run_agent(
    client: MCPClient,
    provider: ModelProvider,
    prompt: str,
    system: str | None = None,
    guard: Any = None,
    budget: Budget | None = None,
    price: Price | None = None,
    limits: Limits | None = None,
    allow_tools: list[str] | None = None,
    task_id: str = "",
    arm_id: str = "",
) -> AgentRun:
    """Run one agent loop against a started MCP client.

    Args:
        client: A started MCP client.
        provider: A fresh provider (one per run).
        prompt: The task.
        system: The system prompt.
        guard: ``guard(GuardCall) -> allow() | deny(reason)`` (see :func:`rules_guard`).
        budget: A shared :class:`Budget`, checked before every model call.
        price: The model's price (``None``: unknown).
        limits: Per-run limits.
        allow_tools: Glob patterns of tools to offer the model.
        task_id: For the guard.
        arm_id: For the guard.

    Returns:
        The :class:`AgentRun`. Provider and server errors end the run with
        ``status="error"``; they are not raised.
    """
    limits = limits or Limits()
    budget = budget or Budget()
    started = time.perf_counter()
    calls: list[CallRecord] = []
    turns = 0
    tokens_in: int | None = 0
    tokens_out: int | None = 0
    cost: float | None = 0.0
    final: str | None = None
    status, reason, error = "completed", "final answer", None

    def finish() -> AgentRun:
        return AgentRun(
            status, calls, final, turns, tokens_in, tokens_out, cost, reason, error,
            round(time.perf_counter() - started, 6),
        )  # fmt: skip

    try:
        tools = map_tools(client.list_tools(), allow_tools)
        by_name = {t.name: t for t in tools}
        provider.start(system, prompt, tools)
        while True:
            if turns >= limits.max_turns:
                status, reason = "limit_reached", f"max_turns ({limits.max_turns})"
                break
            if not budget.allows(price, provider):
                status = "budget_stopped"
                reason = (
                    f"the next call could exceed max_usd {budget.max_usd} "
                    f"(spent ${budget.spent_usd:.4f})"
                )
                break
            turn = provider.complete()
            turns += 1
            tokens_in = (
                None
                if tokens_in is None or turn.input_tokens is None
                else tokens_in + turn.input_tokens
            )
            tokens_out = (
                None
                if tokens_out is None or turn.output_tokens is None
                else tokens_out + turn.output_tokens
            )
            turn_cost = budget.turn_cost(price, turn)
            if turn_cost is None:
                budget.unknown_cost_turns += 1
                cost = None
            else:
                budget.spent_usd += turn_cost
                cost = None if cost is None else cost + turn_cost
            if turn.text:
                final = turn.text
            if not turn.requests:
                break
            results: list[tuple[ToolRequest, str, bool]] = []
            for request in turn.requests:
                if len(calls) >= limits.max_calls:
                    break
                mapped = by_name.get(request.name)
                mcp_name = mapped.mcp_name if mapped else request.name
                record = CallRecord(request.id, mcp_name, request.name, request.arguments)
                calls.append(record)
                if mapped is None:
                    record.is_error, record.error = True, f"unknown tool {request.name!r}"
                elif request.argument_error:
                    record.is_error, record.error = True, request.argument_error
                else:
                    decision = _decide(
                        guard, GuardCall(mcp_name, request.arguments, task_id, arm_id, len(calls))
                    )
                    if not decision.allowed:
                        record.denied, record.deny_reason = True, decision.reason
                        record.is_error = True
                        record.error = f"denied by the harness guard: {decision.reason}"
                    else:
                        result = client.call_tool(mcp_name, request.arguments)
                        record.result = _result_text(result)
                        record.structured = result.structured_content
                        record.is_error = result.is_error
                        record.duration = round(result.duration, 6)
                        if result.is_error:
                            record.error = record.result or "tool error"
                text = record.result if record.result is not None else (record.error or "")
                results.append((request, text, record.is_error))
            provider.add_results(turn, results)
            if len(calls) >= limits.max_calls:
                status, reason = "limit_reached", f"max_calls ({limits.max_calls})"
                break
    except Exception as exc:  # a provider or server failure ends the run, recorded
        status, reason, error = "error", "exception", f"{type(exc).__name__}: {exc}"
    return finish()


# -- the spec ---------------------------------------------------------------------------------


@dataclass
class ArmSpec:
    """One arm: a provider, a model and a system prompt (inherited from the spec)."""

    id: str
    provider: str
    model: str
    system: str | None = None
    max_output_tokens: int = 1024
    extra: dict[str, Any] = field(default_factory=dict)
    pricing: dict[str, Any] | None = None


@dataclass
class TaskSpec:
    """One task: the prompt, and what to check."""

    id: str
    prompt: str
    expected: list[dict[str, Any]] | None = None
    forbidden: list[dict[str, Any]] | None = None
    min_score: float = 0.9
    script: list[dict[str, Any]] | dict[str, list[dict[str, Any]]] | None = None
    require_completed: bool = True

    def script_for(self, arm_id: str) -> list[dict[str, Any]] | None:
        """The scripted turns for an arm: ``script`` itself, or ``script[arm_id]`` when keyed by arm."""
        if isinstance(self.script, dict):
            return self.script.get(arm_id)
        return self.script


@dataclass
class AgentSpec:
    """A study: a server, arms, tasks, repetitions and the safety settings.

    See ``docs/agent_harness.rst`` for the file format.
    """

    name: str
    server: dict[str, Any]
    arms: list[ArmSpec]
    tasks: list[TaskSpec]
    repetitions: int = 1
    seed: int = 0
    budget: dict[str, Any] = field(default_factory=dict)
    limits: Limits = field(default_factory=Limits)
    guard: dict[str, Any] = field(default_factory=dict)
    verify: dict[str, Any] = field(default_factory=dict)
    allow_tools: list[str] | None = None
    output: str | None = None
    base_dir: str = "."

    def cells(self) -> list[tuple[TaskSpec, ArmSpec, int]]:
        """Every (task, arm, repetition), interleaved in a shuffled order fixed by ``seed``."""
        cells = [
            (task, arm, rep)
            for task in self.tasks
            for arm in self.arms
            for rep in range(1, self.repetitions + 1)
        ]
        random.Random(self.seed).shuffle(cells)
        return cells


_SPEC_KEYS = {
    "spec_version", "name", "server", "provider", "model", "system", "max_output_tokens",
    "extra", "pricing", "arms", "tasks", "repetitions", "seed", "budget", "limits", "guard",
    "verify", "allow_tools", "output",
}  # fmt: skip
_ARM_KEYS = {"id", "provider", "model", "system", "max_output_tokens", "extra", "pricing"}
_TASK_KEYS = {"id", "prompt", "expected", "forbidden", "min_score", "script", "require_completed"}
PROVIDERS = ("openai", "anthropic", "scripted")


def _check_keys(data: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {sorted(unknown)}")


def spec_from_mapping(data: Any, base_dir: str | Path = ".") -> AgentSpec:
    """Validate and build an :class:`AgentSpec` from parsed YAML/JSON.

    Raises:
        ValueError: On a missing or unknown key, or a value of the wrong type.
    """
    if not isinstance(data, dict):
        raise ValueError("an agent spec must be a mapping")
    _check_keys(data, _SPEC_KEYS, "spec")
    if int(data.get("spec_version", SPEC_VERSION)) != SPEC_VERSION:
        raise ValueError(f"spec_version must be {SPEC_VERSION}")
    server = data.get("server")
    if not isinstance(server, dict) or not (
        server.get("command") or server.get("url") or server.get("config")
    ):
        raise ValueError("server needs a command, url or config")
    defaults = {
        "provider": data.get("provider"),
        "model": data.get("model"),
        "system": data.get("system"),
        "max_output_tokens": int(data.get("max_output_tokens", 1024)),
        "extra": dict(data.get("extra") or {}),
        "pricing": data.get("pricing"),
    }
    raw_arms = data.get("arms") or [{"id": str(defaults["model"] or "default")}]
    arms = []
    for index, raw in enumerate(raw_arms):
        if not isinstance(raw, dict):
            raise ValueError(f"arm {index} must be a mapping")
        _check_keys(raw, _ARM_KEYS, f"arm {index}")
        merged = {**defaults, **{k: v for k, v in raw.items() if v is not None}}
        provider = str(merged.get("provider") or "")
        if provider not in PROVIDERS:
            raise ValueError(f"arm {raw.get('id', index)}: provider must be one of {PROVIDERS}")
        if not merged.get("model") and provider != "scripted":
            raise ValueError(f"arm {raw.get('id', index)}: needs a model")
        arms.append(
            ArmSpec(
                id=str(raw.get("id") or merged.get("model") or f"arm-{index + 1}"),
                provider=provider,
                model=str(merged.get("model") or "scripted"),
                system=merged.get("system"),
                max_output_tokens=int(merged.get("max_output_tokens") or 1024),
                extra=dict(merged.get("extra") or {}),
                pricing=merged.get("pricing"),
            )
        )
    if len({a.id for a in arms}) != len(arms):
        raise ValueError("arm ids must be unique")
    tasks = []
    for index, raw in enumerate(data.get("tasks") or []):
        if not isinstance(raw, dict) or not raw.get("prompt"):
            raise ValueError(f"task {index} needs a prompt")
        _check_keys(raw, _TASK_KEYS, f"task {index}")
        tasks.append(
            TaskSpec(
                id=str(raw.get("id") or f"task-{index + 1}"),
                prompt=str(raw["prompt"]),
                expected=raw.get("expected"),
                forbidden=raw.get("forbidden"),
                min_score=float(raw.get("min_score", 0.9)),
                script=raw.get("script"),
                require_completed=bool(raw.get("require_completed", True)),
            )
        )
    if not tasks:
        raise ValueError("the spec has no tasks")
    if len({t.id for t in tasks}) != len(tasks):
        raise ValueError("task ids must be unique")
    for arm in arms:
        if arm.provider == "scripted":
            missing = [t.id for t in tasks if t.script_for(arm.id) is None]
            if missing:
                raise ValueError(f"arm {arm.id} is scripted but task(s) {missing} have no script")
    limits = data.get("limits") or {}
    return AgentSpec(
        name=str(data.get("name") or "study"),
        server=dict(server),
        arms=arms,
        tasks=tasks,
        repetitions=int(data.get("repetitions", 1)),
        seed=int(data.get("seed", 0)),
        budget=dict(data.get("budget") or {}),
        limits=Limits(int(limits.get("max_turns", 10)), int(limits.get("max_calls", 20))),
        guard=dict(data.get("guard") or {}),
        verify=dict(data.get("verify") or {}),
        allow_tools=data.get("allow_tools"),
        output=data.get("output"),
        base_dir=str(base_dir),
    )


def load_agent_spec(path: str | Path) -> AgentSpec:
    """Read an agent spec (YAML with ``tool-scorer[yaml]``, or JSON)."""
    from toolscore.mcp.fixtures import load_structured_file

    return spec_from_mapping(load_structured_file(path), base_dir=Path(path).resolve().parent)


# -- the study ---------------------------------------------------------------------------------


class BuildMismatchError(RuntimeError):
    """The server is not the build the spec says it should be."""


def _matches(expected: Any, actual: str) -> bool:
    text = str(expected)
    if len(text) > 1 and text.startswith("/") and text.endswith("/"):
        return re.search(text[1:-1], actual) is not None
    return text == actual


def check_build(server_info: dict[str, Any], verify: dict[str, Any]) -> dict[str, Any]:
    """Check ``serverInfo`` against ``verify.server_name`` / ``verify.server_version``.

    Values are compared exactly, or as a regex when written ``/.../``.

    Returns:
        ``{"name", "version", "checked": [...], "ok": bool}``.
    """
    name = str(server_info.get("name") or "")
    version = str(server_info.get("version") or "")
    checked, ok = [], True
    for key, actual in (("server_name", name), ("server_version", version)):
        if key in verify:
            passed = _matches(verify[key], actual)
            checked.append(
                {"check": key, "expected": str(verify[key]), "actual": actual, "ok": passed}
            )
            ok = ok and passed
    return {"name": name, "version": version, "checked": checked, "ok": ok}


def run_version_command(verify: dict[str, Any], cwd: str | Path = ".") -> dict[str, Any] | None:
    """Run ``verify.command`` and match its output against ``verify.expect``.

    Returns:
        ``{"command", "output", "expect", "ok"}``, or ``None`` without a command.
    """
    command = verify.get("command")
    if not command:
        return None
    argv = shlex.split(command) if isinstance(command, str) else [str(c) for c in command]
    # The user's own spec names the command, like the server command itself.
    completed = subprocess.run(
        argv, capture_output=True, text=True, timeout=120, cwd=cwd, check=False
    )
    output = (completed.stdout or "").strip()
    expect = verify.get("expect")
    ok = completed.returncode == 0 and (
        expect is None or re.search(str(expect), output) is not None
    )
    return {"command": command, "output": output[:500], "expect": expect, "ok": ok}


def _server_spec(server: dict[str, Any], run_dir: str, base_dir: str) -> Any:
    from toolscore.mcp.config import _ENV_REFERENCE, MCPServerSpec, load_mcp_config

    def fill(value: str) -> str:
        return value.replace("{run_dir}", run_dir)

    env = {str(k): fill(str(v)) for k, v in (server.get("env") or {}).items()}
    if server.get("config"):
        spec = load_mcp_config(Path(base_dir) / server["config"], server=server.get("name"))
        spec.env.update(env)
        return spec
    if server.get("url"):
        headers = {str(k): fill(str(v)) for k, v in (server.get("headers") or {}).items()}
        headers = {
            k: _ENV_REFERENCE.sub(lambda m: os.environ.get(m.group(1), ""), v)
            for k, v in headers.items()
        }
        return MCPServerSpec(
            name=str(server["url"]), command=[], url=str(server["url"]), headers=headers
        )
    command = server["command"]
    argv = (
        shlex.split(fill(command)) if isinstance(command, str) else [fill(str(c)) for c in command]
    )
    return MCPServerSpec(name=" ".join(argv), command=argv, env=env)


def _server_label(server: dict[str, Any]) -> dict[str, Any]:
    from toolscore.mcp.client import safe_url

    if server.get("url"):
        return {"transport": "http", "url": safe_url(str(server["url"]))}
    if server.get("config"):
        return {"transport": "config", "config": str(server["config"]), "name": server.get("name")}
    command = server["command"]
    return {
        "transport": "stdio",
        "command": command if isinstance(command, str) else " ".join(map(str, command)),
        "env": sorted((server.get("env") or {}).keys()),
    }


def default_provider_factory(arm: ArmSpec, task: TaskSpec) -> ModelProvider:
    """Create the provider for a run: real SDK clients for openai/anthropic, a script otherwise.

    The SDK clients read their API keys from the environment
    (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``).

    Raises:
        ImportError: If the provider's SDK is not installed.
    """
    if arm.provider == "scripted":
        return ScriptedProvider(task.script_for(arm.id) or [], model=arm.model)
    if arm.provider == "openai":
        try:
            openai = importlib.import_module("openai")
        except ImportError as exc:
            raise ImportError('the openai provider needs: pip install "tool-scorer[llm]"') from exc
        return OpenAIResponsesProvider(openai.OpenAI(), arm.model, arm.max_output_tokens, arm.extra)
    try:
        anthropic = importlib.import_module("anthropic")
    except ImportError as exc:
        raise ImportError(
            'the anthropic provider needs: pip install "tool-scorer[anthropic]"'
        ) from exc
    return AnthropicMessagesProvider(
        anthropic.Anthropic(), arm.model, arm.max_output_tokens, arm.extra
    )


def _guard_for(spec: AgentSpec) -> Any:
    config = spec.guard
    guards: list[Any] = []
    if config.get("deny") or config.get("allow_tools"):
        guards.append(rules_guard(config.get("deny"), config.get("allow_tools")))
    if config.get("python"):
        module_name, _, attribute = str(config["python"]).partition(":")
        if spec.base_dir not in sys.path:
            sys.path.insert(0, spec.base_dir)
        guards.append(getattr(importlib.import_module(module_name), attribute or "guard"))
    if not guards:
        return None

    def combined(call: GuardCall) -> GuardDecision:
        for guard in guards:
            decision = _decide(guard, call)
            if not decision.allowed:
                return decision
        return allow()

    return combined


def evaluate_run(task: TaskSpec, run: AgentRun) -> tuple[dict[str, Any] | None, str]:
    """The Toolscore evaluation of a run and its outcome (pass, fail, error, unknown).

    A run passes when it completed, its score is at least ``min_score``, every
    required call succeeded (unless ``require_completed: false``, for tasks where
    the right answer is to report a refusal), no error-severity honesty finding
    fired and no forbidden call was requested. A run that errored or hit the
    budget is ``error``; a task with no expected or forbidden calls is
    ``unknown`` unless an honesty error makes it ``fail``.
    """
    from toolscore.core import evaluate

    if run.status in ("error", "budget_stopped"):
        return None, "error"
    if task.expected is None and task.forbidden is None:
        result = evaluate([], run.trace(), final_answer=run.final_answer)
        honesty = result.metrics.get("honesty_metrics") or {}
        dishonest = any(f.get("severity") == "error" for f in honesty.get("findings", []))
        return _evaluation_summary(result), "fail" if dishonest else "unknown"
    from toolscore.metrics.policy import rules_from_json

    result = evaluate(
        _expected_calls(task.expected or []),
        run.trace(),
        forbidden=rules_from_json(task.forbidden) if task.forbidden else None,
        final_answer=run.final_answer,
    )
    honesty = result.metrics.get("honesty_metrics") or {}
    dishonest = any(f.get("severity") == "error" for f in honesty.get("findings", []))
    recall = result.required_call_recall
    completed = not task.require_completed or recall is None or recall >= 1.0 - 1e-9
    passed = (
        result.score >= task.min_score - 1e-9
        and completed
        and not dishonest
        and not result.policy_violations
        and run.status == "completed"
    )
    return _evaluation_summary(result), "pass" if passed else "fail"


def _expected_calls(expected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from toolscore.metrics.policy import _matcher_from_json

    def convert(value: Any) -> Any:
        if isinstance(value, dict):
            matcher = _matcher_from_json(value)
            if matcher is not None:
                return matcher
            return {k: convert(v) for k, v in value.items()}
        return value

    return [
        {**call, **({"args": convert(call["args"])} if isinstance(call.get("args"), dict) else {})}
        for call in expected
    ]


def _evaluation_summary(result: Any) -> dict[str, Any]:
    record = result.to_dict()
    return {
        "score": record["score"],
        "grade": record["grade"],
        "weights": record["weights"],
        "required_call_recall": record["required_call_recall"],
        "honesty": record["metrics"].get("honesty_metrics"),
        "policy": record["metrics"].get("policy_metrics"),
        "security": record["metrics"].get("security_metrics"),
        "evidence": record["evidence"],
        "record_schema_version": record["schema_version"],
    }


@dataclass
class StudyResult:
    """What :func:`run_study` did.

    Attributes:
        output: The JSONL file.
        rows: The rows written by this invocation.
        skipped: Cells already in the output (resumed).
        stopped: Why the study stopped early, or ``""``.
        spent_usd: Known cost of this invocation.
        unknown_cost_turns: Model calls whose cost is unknown.
    """

    output: Path
    rows: list[dict[str, Any]]
    skipped: int
    stopped: str
    spent_usd: float
    unknown_cost_turns: int


def completed_cells(path: str | Path, retry_errors: bool = False) -> set[str]:
    """Cell IDs already in a JSONL output (errored ones only unless ``retry_errors``)."""
    target = Path(path)
    if not target.is_file():
        return set()
    done: set[str] = set()
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or not row.get("cell_id"):
            continue
        if retry_errors and row.get("outcome") == "error":
            continue
        done.add(str(row["cell_id"]))
    return done


def preflight_prices(spec: AgentSpec, allow_unknown_price: bool = False) -> dict[str, Price | None]:
    """The price of every arm, refusing unknown prices unless allowed.

    Raises:
        UnknownPriceError: For an arm (not scripted) without a known price.
    """
    allowed = allow_unknown_price or bool(spec.budget.get("allow_unknown_price"))
    prices: dict[str, Price | None] = {}
    for arm in spec.arms:
        if arm.provider == "scripted":
            prices[arm.id] = Price(0.0, 0.0, "scripted (free)")
            continue
        price = price_for(arm.model, arm.pricing or spec.budget.get("pricing"))
        if price is None and not allowed:
            raise UnknownPriceError(
                f"arm {arm.id}: no price is known for model {arm.model!r}. Add pricing: "
                "{input: USD_per_1M, output: USD_per_1M} to the arm or the budget, or set "
                "budget.allow_unknown_price: true (its cost is then unknown and the cap "
                "cannot be enforced)."
            )
        prices[arm.id] = price
    return prices


def run_study(
    spec: AgentSpec,
    output: str | Path | None = None,
    provider_factory: Callable[[ArmSpec, TaskSpec], ModelProvider] | None = None,
    max_runs: int | None = None,
    retry_errors: bool = False,
    allow_unknown_price: bool = False,
    on_row: Callable[[dict[str, Any]], None] | None = None,
) -> StudyResult:
    """Run every cell of a study and append one JSONL row per run.

    Args:
        spec: The study.
        output: The JSONL file (default: the spec's ``output``, else ``<name>.runs.jsonl``).
        provider_factory: Creates the provider of a run (default:
            :func:`default_provider_factory`; tests pass fakes).
        max_runs: Stop after this many new runs.
        retry_errors: Run errored cells again (they are skipped otherwise).
        allow_unknown_price: Allow models without a known price.
        on_row: Called with each row after it is written (for progress output).

    Returns:
        The :class:`StudyResult`.

    Raises:
        UnknownPriceError: Before any call, for a model without a known price.
        BuildMismatchError: When the server or the version command does not
            match ``verify`` (before the first model call of that run).
    """
    from toolscore import __version__
    from toolscore.mcp.config import open_client

    target = Path(output or spec.output or f"{spec.name}.runs.jsonl")
    if not target.is_absolute() and output is None and spec.output:
        target = Path(spec.base_dir) / target
    prices = preflight_prices(spec, allow_unknown_price)
    budget = Budget(
        max_usd=spec.budget.get("max_usd"),
        allow_unknown_price=allow_unknown_price or bool(spec.budget.get("allow_unknown_price")),
    )
    factory = provider_factory or default_provider_factory
    guard = _guard_for(spec)
    version_check = run_version_command(spec.verify, cwd=spec.base_dir)
    if version_check is not None and not version_check["ok"]:
        raise BuildMismatchError(
            f"verify.command {version_check['command']!r} printed {version_check['output']!r}, "
            f"expected {version_check['expect']!r}"
        )
    done = completed_cells(target, retry_errors)
    cells = spec.cells()
    rows: list[dict[str, Any]] = []
    skipped, stopped = 0, ""
    target.parent.mkdir(parents=True, exist_ok=True)
    protocol = str(spec.server.get("protocol", "auto"))
    timeout = float(spec.server.get("timeout", 30.0))
    for order, (task, arm, rep) in enumerate(cells, start=1):
        cell_id = f"{task.id}::{arm.id}::{rep}"
        if cell_id in done:
            skipped += 1
            continue
        if max_runs is not None and len(rows) >= max_runs:
            stopped = f"max_runs ({max_runs})"
            break
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with tempfile.TemporaryDirectory(prefix="toolscore-run-") as run_dir:
            server_spec = _server_spec(spec.server, run_dir, spec.base_dir)
            build: dict[str, Any] = {}
            server_record: dict[str, Any] = _server_label(spec.server)
            try:
                with open_client(server_spec, timeout=timeout, protocol=protocol) as client:  # type: ignore[arg-type]
                    build = check_build(client.server_info, spec.verify)
                    server_record.update(
                        {
                            "name": build["name"],
                            "version": build["version"],
                            "protocol_version": client.protocol_version,
                            "era": client.era,
                            "build_check": {**build, "command": version_check},
                        }
                    )
                    if not build["ok"]:
                        raise BuildMismatchError(
                            f"server {build['name']} {build['version']} does not match verify: "
                            + "; ".join(
                                f"{c['check']} expected {c['expected']!r}, got {c['actual']!r}"
                                for c in build["checked"]
                                if not c["ok"]
                            )
                        )
                    provider = factory(arm, task)
                    run = run_agent(
                        client,
                        provider,
                        task.prompt,
                        system=arm.system,
                        guard=guard,
                        budget=budget,
                        price=prices.get(arm.id),
                        limits=spec.limits,
                        allow_tools=spec.allow_tools,
                        task_id=task.id,
                        arm_id=arm.id,
                    )
            except BuildMismatchError:
                raise
            except Exception as exc:  # the server failed to start or answer
                run = AgentRun(
                    "error", [], None, 0, None, None, None, "server", f"{type(exc).__name__}: {exc}"
                )
        evaluation, outcome = evaluate_run(task, run)
        price = prices.get(arm.id)
        row = {
            "record": "run",
            "run_record_version": RUN_RECORD_VERSION,
            "producer": f"toolscore {__version__}",
            "study": spec.name,
            "cell_id": cell_id,
            "run_id": f"{spec.name}::{cell_id}",
            "task_id": task.id,
            "arm_id": arm.id,
            "repetition": rep,
            "order": order,
            "seed": spec.seed,
            "started_at": started_at,
            "duration_s": run.duration_s,
            "status": run.status,
            "stop_reason": run.stop_reason,
            "error": run.error,
            "provider": arm.provider,
            "model": arm.model,
            "server": server_record,
            "prompt": task.prompt,
            "calls": [asdict(c) for c in run.calls],
            "guard_denials": run.guard_denials,
            "final_answer": run.final_answer,
            "turns": run.turns,
            "usage": {"input_tokens": run.input_tokens, "output_tokens": run.output_tokens},
            "cost_usd": run.cost_usd,
            "price": asdict(price) if price else None,
            "expected": task.expected,
            "forbidden": task.forbidden,
            "min_score": task.min_score,
            "evaluation": evaluation,
            "outcome": outcome,
            "passed": None if outcome in ("error", "unknown") else outcome == "pass",
        }
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        rows.append(row)
        if on_row is not None:
            on_row(row)
        if run.status == "budget_stopped":
            stopped = "budget"
            break
    return StudyResult(target, rows, skipped, stopped, budget.spent_usd, budget.unknown_cost_turns)


def estimate_study_cost(spec: AgentSpec, prices: dict[str, Price | None]) -> dict[str, Any]:
    """A worst-case cost estimate before any call (for ``toolscore doctor`` and ``--dry-run``).

    Per run: ``max_turns`` model calls, each with ``max_output_tokens`` out and
    an input that grows by that much per turn, starting from the prompt and the
    system prompt (tool definitions are not known before the server starts and
    add to the input). An upper bound, not a forecast.

    Returns:
        ``runs``, ``per_arm`` (``usd`` or ``None`` when the price is unknown) and
        ``total_usd`` (``None`` when any arm's price is unknown).
    """
    from toolscore.metrics.cost_estimator import estimate_tokens

    per_arm: dict[str, float | None] = {}
    runs = len(spec.tasks) * spec.repetitions
    for arm in spec.arms:
        price = prices.get(arm.id)
        if price is None:
            per_arm[arm.id] = None
            continue
        total = 0.0
        for task in spec.tasks:
            base = estimate_tokens(task.prompt) + estimate_tokens(arm.system or "")
            out = arm.max_output_tokens if arm.provider != "scripted" else 0
            tokens_in = sum(base + turn * out for turn in range(spec.limits.max_turns))
            tokens_out = out * spec.limits.max_turns
            total += (tokens_in * price.input + tokens_out * price.output) / 1_000_000
        per_arm[arm.id] = total * spec.repetitions
    known = [v for v in per_arm.values() if v is not None]
    return {
        "runs": runs * len(spec.arms),
        "per_arm": per_arm,
        "total_usd": sum(known) if len(known) == len(per_arm) else None,
        "max_usd": spec.budget.get("max_usd"),
    }


def _run_from_row(row: dict[str, Any]) -> AgentRun:
    """Rebuild the :class:`AgentRun` of a saved row (for regrading)."""
    calls = [
        CallRecord(
            id=str(c.get("id") or ""),
            tool=str(c.get("tool") or ""),
            provider_name=str(c.get("provider_name") or c.get("tool") or ""),
            args=dict(c.get("args") or {}),
            result=c.get("result"),
            structured=c.get("structured"),
            is_error=bool(c.get("is_error")),
            error=c.get("error"),
            duration=c.get("duration"),
            denied=bool(c.get("denied")),
            deny_reason=c.get("deny_reason"),
        )
        for c in row.get("calls") or []
        if isinstance(c, dict)
    ]
    usage = row.get("usage") or {}
    return AgentRun(
        status=str(row.get("status") or "completed"),
        calls=calls,
        final_answer=row.get("final_answer"),
        turns=int(row.get("turns") or 0),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cost_usd=row.get("cost_usd"),
        stop_reason=str(row.get("stop_reason") or ""),
        error=row.get("error"),
        duration_s=float(row.get("duration_s") or 0.0),
    )


def regrade_rows(
    rows: list[dict[str, Any]],
    tasks: dict[str, TaskSpec] | None = None,
    expected: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Re-evaluate saved runs with new expectations, without running anything.

    Args:
        rows: Rows from :func:`run_study` (``record: "run"``).
        tasks: New task definitions by task ID (their ``expected``,
            ``forbidden``, ``min_score`` and ``require_completed`` are used);
            rows of other tasks keep their own.
        expected: New expected calls for every row (instead of ``tasks``).

    Returns:
        The rows with a new ``evaluation``, ``outcome`` and ``passed``, and a
        ``regraded`` block (``from_sha256`` of the original row, producer, time).
    """
    from toolscore import __version__
    from toolscore.receipts import json_sha256

    regraded = []
    for row in rows:
        if row.get("record") != "run":
            regraded.append(row)
            continue
        task_id = str(row.get("task_id") or "")
        if tasks is not None and task_id in tasks:
            task = tasks[task_id]
        else:
            task = TaskSpec(
                id=task_id,
                prompt=str(row.get("prompt") or ""),
                expected=expected if expected is not None else row.get("expected"),
                forbidden=row.get("forbidden"),
                min_score=float(row.get("min_score", 0.9)),
            )
        evaluation, outcome = evaluate_run(task, _run_from_row(row))
        new = dict(row)
        new.update(
            {
                "expected": task.expected,
                "forbidden": task.forbidden,
                "min_score": task.min_score,
                "evaluation": evaluation,
                "outcome": outcome,
                "passed": None if outcome in ("error", "unknown") else outcome == "pass",
                "regraded": {
                    "from_sha256": json_sha256(row),
                    "producer": f"toolscore {__version__}",
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                },
            }
        )
        regraded.append(new)
    return regraded
