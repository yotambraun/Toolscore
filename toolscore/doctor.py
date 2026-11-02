"""Preflight checks before any paid call: ``toolscore doctor``.

A study that fails on its first model call wastes time; one that fails on its
fiftieth wastes money. :func:`run_doctor` checks, without calling a model:

* Python, Toolscore and the optional packages a spec needs (``httpx`` for URL
  servers, ``pyyaml`` for YAML files, ``openai`` / ``anthropic`` for the arms);
* API keys **by name only**: present or missing, never their values;
* the agent spec, the contract or gold file: do they parse and validate;
* the MCP server: does it start, which protocol, how many tools, and does its
  ``serverInfo`` match the spec's ``verify`` (and the version command, if any);
* prices: every arm's model has a known price (or the spec allows unknown ones);
* the budget: the worst-case cost of the whole study against ``max_usd``.

Each check is ``pass``, ``warn``, ``fail``, ``unknown`` (the check could not be
made) or ``skip`` (not applicable). An idea from Agent Eval Flow's preflight.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.mcp.agent import AgentSpec
    from toolscore.mcp.config import MCPServerSpec

#: Check statuses, worst first.
STATUSES: tuple[str, ...] = ("fail", "unknown", "warn", "pass", "skip")

#: The API key each provider reads.
PROVIDER_KEYS: dict[str, str] = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
#: The package each provider needs, and the extra that installs it.
PROVIDER_PACKAGES: dict[str, tuple[str, str]] = {
    "openai": ("openai", "tool-scorer[llm]"),
    "anthropic": ("anthropic", "tool-scorer[anthropic]"),
}


@dataclass
class DoctorCheck:
    """One preflight check: ``name``, ``status`` and a ``detail`` sentence."""

    name: str
    status: str
    detail: str


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _env_references(server: dict[str, Any]) -> set[str]:
    import re

    names: set[str] = set()
    for value in (server.get("headers") or {}).values():
        names.update(re.findall(r"\$\{(?:env:)?([A-Za-z_][A-Za-z0-9_]*)\}", str(value)))
    url = str(server.get("url") or "")
    names.update(re.findall(r"\$\{(?:env:)?([A-Za-z_][A-Za-z0-9_]*)\}", url))
    return names


def check_server(
    spec: MCPServerSpec, verify: dict[str, Any] | None = None, timeout: float = 30.0
) -> list[DoctorCheck]:
    """Start a server, list its tools and check its build; nothing else is called."""
    from toolscore.mcp.agent import check_build
    from toolscore.mcp.config import open_client

    checks: list[DoctorCheck] = []
    try:
        with open_client(spec, timeout=timeout) as client:
            tools = client.list_tools()
            info = client.server_info
            era = "stateless" if client.era == "modern" else "initialize handshake"
            checks.append(
                DoctorCheck(
                    "server",
                    "pass" if tools else "warn",
                    f"{info.get('name', '?')} {info.get('version', '')} started; "
                    f"{len(tools)} tool(s); MCP {client.protocol_version} ({era})",
                )
            )
            if verify:
                build = check_build(info, verify)
                if build["checked"]:
                    detail = "; ".join(
                        f"{c['check']} {c['actual']!r} "
                        + ("matches" if c["ok"] else f"is not {c['expected']!r}")
                        for c in build["checked"]
                    )
                    checks.append(DoctorCheck("build", "pass" if build["ok"] else "fail", detail))
    except Exception as exc:  # report any launch/protocol failure as a failed check
        checks.append(DoctorCheck("server", "fail", f"did not start or answer: {exc}"))
    return checks


def _spec_checks(
    spec: AgentSpec, allow_unknown_price: bool, start_server: bool
) -> list[DoctorCheck]:
    from toolscore.mcp.agent import (
        _server_spec,
        estimate_study_cost,
        price_for,
        run_version_command,
    )

    checks: list[DoctorCheck] = []
    providers = {arm.provider for arm in spec.arms}
    for provider in sorted(providers & set(PROVIDER_PACKAGES)):
        module, extra = PROVIDER_PACKAGES[provider]
        checks.append(
            DoctorCheck(
                f"package {module}",
                "pass" if _installed(module) else "fail",
                "installed" if _installed(module) else f'missing: pip install "{extra}"',
            )
        )
    if spec.server.get("url") and not _installed("httpx"):
        checks.append(
            DoctorCheck("package httpx", "fail", 'missing: pip install "tool-scorer[http]"')
        )
    keys = {PROVIDER_KEYS[p] for p in providers if p in PROVIDER_KEYS} | _env_references(
        spec.server
    )
    for name in sorted(keys):
        present = bool(os.environ.get(name))
        checks.append(
            DoctorCheck(
                f"key {name}",
                "pass" if present else "fail",
                "set (value not shown)" if present else "not set",
            )
        )

    allowed = allow_unknown_price or bool(spec.budget.get("allow_unknown_price"))
    prices = {}
    for arm in spec.arms:
        if arm.provider == "scripted":
            prices[arm.id] = price_for("scripted", {"input": 0, "output": 0})
            checks.append(DoctorCheck(f"price {arm.id}", "pass", "scripted: free"))
            continue
        price = price_for(arm.model, arm.pricing or spec.budget.get("pricing"))
        prices[arm.id] = price
        if price is not None:
            checks.append(
                DoctorCheck(
                    f"price {arm.id}",
                    "pass",
                    f"{arm.model}: ${price.input} in / ${price.output} out per 1M ({price.source})",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    f"price {arm.id}",
                    "warn" if allowed else "fail",
                    f"{arm.model}: no known price"
                    + (" (allowed; its cost will be unknown)" if allowed else "; add pricing"),
                )
            )
    estimate = estimate_study_cost(spec, prices)
    total, cap = estimate["total_usd"], estimate["max_usd"]
    if total is None:
        checks.append(
            DoctorCheck("budget", "unknown", f"{estimate['runs']} run(s); worst case unknown")
        )
    elif cap is not None and total > float(cap):
        checks.append(
            DoctorCheck(
                "budget",
                "warn",
                f"{estimate['runs']} run(s); worst case ${total:.4f} exceeds max_usd {cap}: the "
                "study stops when the next call could cross it",
            )
        )
    else:
        cap_text = f" (max_usd {cap})" if cap is not None else " (no max_usd set)"
        checks.append(
            DoctorCheck(
                "budget",
                "pass" if cap is not None or total == 0 else "warn",
                f"{estimate['runs']} run(s); worst case ${total:.4f}{cap_text}",
            )
        )

    if spec.verify.get("command"):
        try:
            result = run_version_command(spec.verify, cwd=spec.base_dir)
        except Exception as exc:  # a missing program is a failed check
            checks.append(DoctorCheck("version command", "fail", str(exc)))
        else:
            assert result is not None
            checks.append(
                DoctorCheck(
                    "version command",
                    "pass" if result["ok"] else "fail",
                    f"{result['command']!r} printed {result['output']!r}"
                    + ("" if result["ok"] else f", expected {result['expect']!r}"),
                )
            )
    if start_server:
        with tempfile.TemporaryDirectory(prefix="toolscore-doctor-") as run_dir:
            checks.extend(
                check_server(
                    _server_spec(spec.server, run_dir, spec.base_dir),
                    spec.verify,
                    float(spec.server.get("timeout", 30.0)),
                )
            )
    return checks


def run_doctor(
    spec_path: str | Path | None = None,
    contract_path: str | Path | None = None,
    server: MCPServerSpec | None = None,
    keys: list[str] | None = None,
    allow_unknown_price: bool = False,
    start_server: bool = True,
) -> list[DoctorCheck]:
    """Run the preflight checks (see the module docstring).

    Args:
        spec_path: An agent spec to check (server, keys, packages, prices, budget).
        contract_path: A contract or gold file to validate.
        server: A server to start and list (when there is no spec).
        keys: More environment variable names that must be set.
        allow_unknown_price: As for ``toolscore agent run``.
        start_server: Start the spec's server (``False`` checks only the files).

    Returns:
        The checks, in the order they ran.
    """
    from toolscore import __version__

    checks = [
        DoctorCheck(
            "toolscore",
            "pass",
            f"{__version__} on Python {platform.python_version()} ({sys.platform})",
        )
    ]
    if spec_path is not None:
        from toolscore.mcp.agent import load_agent_spec

        if Path(spec_path).suffix in (".yaml", ".yml") and not _installed("yaml"):
            checks.append(
                DoctorCheck("package pyyaml", "fail", 'missing: pip install "tool-scorer[yaml]"')
            )
        else:
            try:
                spec = load_agent_spec(spec_path)
            except (OSError, ValueError) as exc:
                checks.append(DoctorCheck("spec", "fail", f"{spec_path}: {exc}"))
            else:
                checks.append(
                    DoctorCheck(
                        "spec",
                        "pass",
                        f"{spec.name}: {len(spec.tasks)} task(s), {len(spec.arms)} arm(s), "
                        f"{spec.repetitions} repetition(s), seed {spec.seed}",
                    )
                )
                checks.extend(_spec_checks(spec, allow_unknown_price, start_server))
    if contract_path is not None:
        checks.append(_contract_check(contract_path))
    if server is not None:
        checks.extend(check_server(server))
    for name in keys or []:
        present = bool(os.environ.get(name))
        checks.append(
            DoctorCheck(
                f"key {name}",
                "pass" if present else "fail",
                "set (value not shown)" if present else "not set",
            )
        )
    return checks


def _contract_check(path: str | Path) -> DoctorCheck:
    from toolscore.contract import contract_file_data, contract_from_mapping, is_contract
    from toolscore.core import load_gold_standard

    try:
        data = contract_file_data(path)
        if is_contract(data):
            contract = contract_from_mapping(data)
            combinations = len(contract.expansions())
            return DoctorCheck(
                "contract",
                "pass",
                f"{path}: version 2, {len(contract.required)} required entr(ies), "
                f"{len(contract.optional)} optional, {len(contract.forbidden)} forbidden, "
                f"{combinations} combination(s) of alternatives",
            )
        calls = load_gold_standard(path)
    except (OSError, ValueError) as exc:
        return DoctorCheck("contract", "fail", f"{path}: {exc}")
    return DoctorCheck(
        "contract", "pass" if calls else "warn", f"{path}: gold file, {len(calls)} call(s)"
    )


def worst_status(checks: list[DoctorCheck]) -> str:
    """The worst status among the checks."""
    for status in STATUSES:
        if any(c.status == status for c in checks):
            return status
    return "pass"


def doctor_report(checks: list[DoctorCheck]) -> dict[str, Any]:
    """A JSON-safe report: the checks, the counts and the worst status."""
    return {
        "ok": not any(c.status == "fail" for c in checks),
        "worst": worst_status(checks),
        "counts": {s: sum(1 for c in checks if c.status == s) for s in STATUSES},
        "checks": [asdict(c) for c in checks],
    }
