"""Light statistics for comparing variants over repeated runs, and choosing one.

An agent that passes a task 7 times out of 10 and one that passes 9 times out
of 10 may not be different at all. :func:`compare_runs` reports, per variant:

* complete populations: ``N`` runs, of which ``pass``, ``fail``, ``error``
  and ``unknown``. Errored and unknown runs stay in the denominator: a run that
  crashed did not pass;
* the pass rate with a 95% Wilson score interval (:func:`wilson_interval`);
* ``pass^k``: the probability that all of ``k`` runs of a task pass, estimated
  per task with the unbiased estimator ``C(c, k) / C(n, k)`` for ``c`` passes
  in ``n`` runs (as in tau-bench), averaged over tasks with at least ``k`` runs;
* mean cost and latency over the runs that have them (unknown when none do).

Pairs of variants get the difference in pass rate and a two-sided Fisher exact
test (:func:`fisher_exact`). A pair is **not distinguishable** when either
variant has fewer than ``min_n`` runs, their 95% intervals overlap, or
``p >= alpha``.

:func:`select_variant` picks a variant by a lexicographic, weighted or Pareto
policy over objectives such as ``pass_rate:max``, ``cost:min`` and
``latency:min``, and always reports the Pareto front (an idea from Agent Eval
Flow's selection policies). :func:`evaluate_protocol` checks decision rules
declared before the runs (light pre-registration). For full studies (design,
pre-registration, grading, reports), use Agent Eval Flow.

Everything is standard library (``math.comb``); nothing is sampled.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

#: z for a two-sided 95% interval.
Z_95 = 1.959963984540054

#: Run outcomes.
OUTCOMES: tuple[str, ...] = ("pass", "fail", "error", "unknown")

#: Metrics :func:`select_variant` can optimize, and their usual direction.
OBJECTIVE_METRICS: dict[str, str] = {
    "pass_rate": "max",
    "pass_lower": "max",
    "pass_hat_k": "max",
    "cost": "min",
    "latency": "min",
    "error_rate": "min",
    "unknown_rate": "min",
}


# -- primitives -------------------------------------------------------------------


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """The Wilson score interval for a proportion.

    Args:
        successes: Successes.
        n: Trials (``0`` gives ``(0.0, 1.0)``: nothing is known).
        z: Normal quantile (1.96 for 95%).

    Returns:
        ``(lower, upper)`` in ``[0, 1]``.
    """
    if n <= 0:
        return 0.0, 1.0
    if not 0 <= successes <= n:
        raise ValueError(f"successes must be in [0, {n}], got {successes}")
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test p-value for the 2x2 table ``[[a, b], [c, d]]``.

    Rows are variants, columns pass / not pass. The p-value sums the
    probabilities of every table with the same margins that is no more likely
    than the observed one.

    Returns:
        The p-value in ``[0, 1]``.
    """
    if min(a, b, c, d) < 0:
        raise ValueError("table cells must be non-negative")
    row1, row2, col1 = a + b, c + d, a + c
    total = row1 + row2
    if total == 0:
        return 1.0
    denominator = math.comb(total, col1)

    def probability(x: int) -> float:
        return math.comb(row1, x) * math.comb(row2, col1 - x) / denominator

    observed = probability(a)
    low, high = max(0, col1 - row2), min(row1, col1)
    p = sum(probability(x) for x in range(low, high + 1) if probability(x) <= observed * (1 + 1e-7))
    return min(1.0, p)


def pass_hat_k(passes: int, n: int, k: int) -> float | None:
    """Unbiased estimate of the probability that ``k`` runs of a task all pass.

    ``C(passes, k) / C(n, k)``; ``None`` when ``n < k`` (not enough runs).
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    if n < k:
        return None
    return math.comb(passes, k) / math.comb(n, k)


def intervals_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """Whether two closed intervals overlap."""
    return a[0] <= b[1] and b[0] <= a[1]


# -- runs ---------------------------------------------------------------------------


@dataclass
class Run:
    """One run of one task under one variant.

    Attributes:
        variant: The variant (arm, model, configuration...).
        task: The task.
        outcome: ``"pass"``, ``"fail"``, ``"error"`` or ``"unknown"``.
        cost: Cost in USD, or ``None`` when unknown.
        latency: Wall-clock seconds, or ``None`` when unknown.
        run_id: An identifier for reports.
    """

    variant: str
    task: str
    outcome: str
    cost: float | None = None
    latency: float | None = None
    run_id: str = ""

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {OUTCOMES}, got {self.outcome!r}")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def run_from_row(row: dict[str, Any], variant_key: str | None = None) -> Run:
    """Read a run from a JSONL row: a ``toolscore agent run`` row or an exported record.

    The variant is ``row[variant_key]``, else ``arm_id``, ``variant``, ``arm``
    or ``model``; the task ``task_id`` or ``task``. The outcome is ``outcome``,
    else derived: ``status == "error"`` is an error, ``passed`` true/false is a
    pass/fail, anything else unknown. Cost is ``cost_usd`` or ``cost`` (a
    number, or ``{"usd": ...}``); latency ``duration_s``, ``latency`` or
    ``duration``.

    Raises:
        ValueError: If the row names no variant.
    """
    variant = None
    for key in ([variant_key] if variant_key else []) + ["arm_id", "variant", "arm", "model"]:
        if row.get(key) not in (None, ""):
            variant = str(row[key])
            break
    if variant is None:
        raise ValueError(f"row has no variant field ({variant_key or 'arm_id/variant'})")
    task = str(row.get("task_id") or row.get("task") or "task")
    outcome = row.get("outcome")
    if outcome not in OUTCOMES:
        if row.get("status") == "error":
            outcome = "error"
        elif isinstance(row.get("passed"), bool):
            outcome = "pass" if row["passed"] else "fail"
        else:
            outcome = "unknown"
    cost = row.get("cost_usd", row.get("cost"))
    if isinstance(cost, dict):
        cost = cost.get("usd")
    latency = row.get("duration_s", row.get("latency", row.get("duration")))
    return Run(
        variant=variant,
        task=task,
        outcome=str(outcome),
        cost=_number(cost),
        latency=_number(latency),
        run_id=str(row.get("run_id") or row.get("cell_id") or ""),
    )


def load_runs(paths: Iterable[str | Path], variant_key: str | None = None) -> list[Run]:
    """Read runs from JSONL files (one JSON object per line; blank lines skipped).

    Raises:
        ValueError: On a line that is not a JSON object, naming the file and line.
    """
    runs: list[Run] = []
    for path in paths:
        for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ValueError(f"{path}:{number}: not JSON ({exc})") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{number}: expected a JSON object")
            if row.get("record") == "header":  # an export header line
                continue
            try:
                runs.append(run_from_row(row, variant_key))
            except ValueError as exc:
                raise ValueError(f"{path}:{number}: {exc}") from exc
    return runs


#: Default pattern that splits a trace file name into task and repetition:
#: ``search-3.json``, ``search_r2.json`` and ``search.json`` are all task ``search``.
DEFAULT_TASK_PATTERN = r"^(?P<task>.+?)(?:[-_.]r?\d+)?$"


def runs_from_traces(
    variant: str,
    directory: str | Path,
    gold: str | Path,
    min_score: float = 0.9,
    task_pattern: str = DEFAULT_TASK_PATTERN,
) -> list[Run]:
    """Score every ``*.json`` trace in a directory against a gold file.

    A trace passes when its score is at least ``min_score`` and it has no
    error-severity honesty finding; a trace that cannot be read is an
    ``error`` (it stays in the population).

    Args:
        variant: The variant name.
        directory: The directory of trace files.
        gold: The gold file or contract.
        min_score: The passing score.
        task_pattern: Regex with a ``task`` group applied to each file stem.

    Returns:
        One run per trace file, sorted by file name.
    """
    from toolscore.core import evaluate_trace

    pattern = re.compile(task_pattern)
    runs: list[Run] = []
    for path in sorted(Path(directory).glob("*.json")):
        match = pattern.match(path.stem)
        task = match.group("task") if match and match.groupdict().get("task") else path.stem
        try:
            result = evaluate_trace(gold, path, validate_side_effects=False)
        except Exception:  # an unreadable trace is an errored run, not a missing one
            runs.append(Run(variant, task, "error", run_id=path.name))
            continue
        honesty = result.metrics.get("honesty_metrics") or {}
        dishonest = any(f.get("severity") == "error" for f in honesty.get("findings", []))
        passed = result.score >= min_score - 1e-9 and not dishonest
        latency = (result.metrics.get("latency_metrics") or {}).get("total_duration")
        cost = (result.metrics.get("cost_metrics") or {}).get("total_cost")
        runs.append(
            Run(
                variant,
                task,
                "pass" if passed else "fail",
                cost=_number(cost) if result.trace_calls else None,
                latency=_number(latency) if result.trace_calls else None,
                run_id=path.name,
            )
        )
    return runs


# -- comparison ---------------------------------------------------------------------


@dataclass
class VariantStats:
    """The summary of one variant (see the module docstring).

    Attributes:
        variant: The variant.
        n: Runs.
        counts: Runs per outcome.
        pass_rate: ``pass / n`` (``None`` with no runs).
        interval: 95% Wilson interval of the pass rate.
        pass_hat_k: Mean ``pass^k`` over tasks with at least ``k`` runs, or ``None``.
        k: The ``k`` used.
        tasks: Tasks seen.
        tasks_short: Tasks with fewer than ``k`` runs (left out of ``pass^k``).
        cost: Mean cost of the runs that have one, or ``None``.
        cost_known: Runs with a cost.
        latency: Mean latency of the runs that have one, or ``None``.
        latency_known: Runs with a latency.
    """

    variant: str
    n: int
    counts: dict[str, int]
    pass_rate: float | None
    interval: tuple[float, float]
    pass_hat_k: float | None
    k: int
    tasks: int
    tasks_short: int
    cost: float | None
    cost_known: int
    latency: float | None
    latency_known: int

    def metric(self, name: str) -> float | None:
        """A metric for selection (see :data:`OBJECTIVE_METRICS`)."""
        if name == "pass_rate":
            return self.pass_rate
        if name == "pass_lower":
            return self.interval[0] if self.n else None
        if name == "pass_hat_k":
            return self.pass_hat_k
        if name == "cost":
            return self.cost
        if name == "latency":
            return self.latency
        if name == "error_rate":
            return self.counts["error"] / self.n if self.n else None
        if name == "unknown_rate":
            return self.counts["unknown"] / self.n if self.n else None
        raise ValueError(f"unknown metric {name!r}; known: {sorted(OBJECTIVE_METRICS)}")


@dataclass
class PairComparison:
    """Two variants side by side.

    Attributes:
        a: The first variant.
        b: The second variant.
        difference: ``pass_rate(b) - pass_rate(a)``, or ``None``.
        p_value: Two-sided Fisher exact p-value.
        overlap: Whether the 95% intervals overlap.
        distinguishable: Whether the difference is distinguishable (see the
            module docstring).
        verdict: A sentence for reports.
    """

    a: str
    b: str
    difference: float | None
    p_value: float
    overlap: bool
    distinguishable: bool
    verdict: str


@dataclass
class Comparison:
    """The result of :func:`compare_runs`.

    Attributes:
        variants: Per-variant statistics, in first-seen order.
        pairs: Pairwise comparisons (each variant against the baseline, or all pairs).
        k: The ``k`` of ``pass^k``.
        min_n: Runs needed per variant before a difference can be called.
        alpha: Significance level.
    """

    variants: list[VariantStats]
    pairs: list[PairComparison]
    k: int
    min_n: int
    alpha: float
    notes: list[str] = field(default_factory=list)

    def by_name(self) -> dict[str, VariantStats]:
        """Statistics by variant name."""
        return {v.variant: v for v in self.variants}

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe report."""
        return {
            "k": self.k,
            "min_n": self.min_n,
            "alpha": self.alpha,
            "variants": [{**asdict(v), "interval": list(v.interval)} for v in self.variants],
            "pairs": [asdict(p) for p in self.pairs],
            "notes": self.notes,
        }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def variant_stats(variant: str, runs: list[Run], k: int = 1) -> VariantStats:
    """Summarize the runs of one variant."""
    counts = {outcome: sum(1 for r in runs if r.outcome == outcome) for outcome in OUTCOMES}
    n = len(runs)
    tasks: dict[str, list[Run]] = {}
    for run in runs:
        tasks.setdefault(run.task, []).append(run)
    estimates = [
        pass_hat_k(sum(1 for r in task_runs if r.outcome == "pass"), len(task_runs), k)
        for task_runs in tasks.values()
    ]
    known = [e for e in estimates if e is not None]
    costs = [r.cost for r in runs if r.cost is not None]
    latencies = [r.latency for r in runs if r.latency is not None]
    return VariantStats(
        variant=variant,
        n=n,
        counts=counts,
        pass_rate=counts["pass"] / n if n else None,
        interval=wilson_interval(counts["pass"], n),
        pass_hat_k=_mean(known),
        k=k,
        tasks=len(tasks),
        tasks_short=len(estimates) - len(known),
        cost=_mean(costs),
        cost_known=len(costs),
        latency=_mean(latencies),
        latency_known=len(latencies),
    )


def compare_pair(
    a: VariantStats, b: VariantStats, min_n: int = 10, alpha: float = 0.05
) -> PairComparison:
    """Compare the pass rates of two variants."""
    a_pass, b_pass = a.counts["pass"], b.counts["pass"]
    p_value = fisher_exact(a_pass, a.n - a_pass, b_pass, b.n - b_pass)
    overlap = intervals_overlap(a.interval, b.interval)
    difference = None if a.pass_rate is None or b.pass_rate is None else b.pass_rate - a.pass_rate
    if min(a.n, b.n) < min_n:
        verdict = f"not distinguishable: fewer than {min_n} runs ({a.n} and {b.n})"
        distinguishable = False
    elif overlap or p_value >= alpha:
        why = "the 95% intervals overlap" if overlap else f"p = {p_value:.3f} >= {alpha}"
        verdict = f"not distinguishable: {why}"
        distinguishable = False
    else:
        better = b.variant if (difference or 0) > 0 else a.variant
        verdict = f"{better} has the higher pass rate (p = {p_value:.3g})"
        distinguishable = True
    return PairComparison(
        a.variant, b.variant, difference, p_value, overlap, distinguishable, verdict
    )


def compare_runs(
    runs: list[Run],
    k: int = 1,
    baseline: str | None = None,
    min_n: int = 10,
    alpha: float = 0.05,
) -> Comparison:
    """Compare variants over repeated runs (see the module docstring).

    Args:
        runs: Every run, of every variant.
        k: The ``k`` of ``pass^k``.
        baseline: Compare every variant with this one; ``None`` compares all pairs.
        min_n: Runs per variant needed before a difference can be called.
        alpha: Significance level for the Fisher test.

    Returns:
        The :class:`Comparison`.

    Raises:
        ValueError: If ``baseline`` is not one of the variants.
    """
    grouped: dict[str, list[Run]] = {}
    for run in runs:
        grouped.setdefault(run.variant, []).append(run)
    variants = [variant_stats(name, group, k) for name, group in grouped.items()]
    by_name = {v.variant: v for v in variants}
    if baseline is not None and baseline not in by_name:
        raise ValueError(f"baseline {baseline!r} is not a variant ({sorted(by_name)})")
    pairs: list[PairComparison] = []
    if baseline is not None:
        pairs = [
            compare_pair(by_name[baseline], v, min_n, alpha)
            for v in variants
            if v.variant != baseline
        ]
    else:
        pairs = [
            compare_pair(variants[i], variants[j], min_n, alpha)
            for i in range(len(variants))
            for j in range(i + 1, len(variants))
        ]
    notes = []
    if any(v.counts["error"] for v in variants):
        notes.append("Errored runs count as not passed and stay in N.")
    if any(v.counts["unknown"] for v in variants):
        notes.append("Runs with an unknown outcome count as not passed and stay in N.")
    if any(v.tasks_short for v in variants):
        notes.append(f"Tasks with fewer than k={k} runs are left out of pass^k.")
    return Comparison(variants, pairs, k, min_n, alpha, notes)


# -- selection ------------------------------------------------------------------------


@dataclass
class Objective:
    """One selection objective: a metric and a direction (``"max"`` or ``"min"``)."""

    metric: str
    direction: str

    @classmethod
    def parse(cls, text: str) -> Objective:
        """``"cost:min"``; the direction defaults to the metric's usual one."""
        metric, _, direction = text.partition(":")
        metric = metric.strip()
        if metric not in OBJECTIVE_METRICS:
            raise ValueError(f"unknown metric {metric!r}; known: {sorted(OBJECTIVE_METRICS)}")
        direction = direction.strip() or OBJECTIVE_METRICS[metric]
        if direction not in ("max", "min"):
            raise ValueError(f"direction must be max or min, got {direction!r}")
        return cls(metric, direction)

    def key(self, stats: VariantStats) -> float:
        """A sort key where smaller is better; unknown values sort last."""
        value = stats.metric(self.metric)
        if value is None:
            return math.inf
        return -value if self.direction == "max" else value


DEFAULT_OBJECTIVES = ("pass_rate:max", "cost:min", "latency:min")


def pareto_front(variants: list[VariantStats], objectives: list[Objective]) -> list[str]:
    """Variants no other variant dominates (at least as good on every objective, better on one).

    Unknown values count as the worst.
    """
    keys = {v.variant: [o.key(v) for o in objectives] for v in variants}

    def dominates(x: list[float], y: list[float]) -> bool:
        return all(a <= b for a, b in zip(x, y, strict=True)) and any(
            a < b for a, b in zip(x, y, strict=True)
        )

    return [
        name
        for name, key in keys.items()
        if not any(
            dominates(other, key) for other_name, other in keys.items() if other_name != name
        )
    ]


@dataclass
class Selection:
    """The result of :func:`select_variant`.

    Attributes:
        chosen: The selected variant, or ``None`` with no variants.
        policy: ``"lexicographic"``, ``"weighted"`` or ``"pareto"``.
        objectives: The objectives used.
        ranking: Variants best first, under the policy.
        pareto_front: The non-dominated variants.
        scores: Weighted scores (``weighted`` policy only).
        unknown: Per variant, the objectives whose value is unknown.
        reason: Why the chosen variant won.
    """

    chosen: str | None
    policy: str
    objectives: list[Objective]
    ranking: list[str]
    pareto_front: list[str]
    scores: dict[str, float]
    unknown: dict[str, list[str]]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe report."""
        return {
            "chosen": self.chosen,
            "policy": self.policy,
            "objectives": [f"{o.metric}:{o.direction}" for o in self.objectives],
            "ranking": self.ranking,
            "pareto_front": self.pareto_front,
            "scores": self.scores,
            "unknown": self.unknown,
            "reason": self.reason,
        }


def select_variant(
    comparison: Comparison,
    policy: str = "lexicographic",
    objectives: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> Selection:
    """Pick a variant.

    * ``lexicographic``: best on the first objective, ties broken by the next.
    * ``weighted``: each objective's values are scaled to ``[0, 1]`` across the
      variants (1 is best; unknown is 0), and the weighted sum is highest.
    * ``pareto``: the Pareto front; when it has several variants, the first
      objective breaks the tie (then the next).

    Args:
        comparison: From :func:`compare_runs`.
        policy: The policy.
        objectives: ``"metric:direction"`` strings (default
            :data:`DEFAULT_OBJECTIVES`).
        weights: Weight per metric for ``weighted`` (default 1 each).

    Returns:
        The :class:`Selection`.

    Raises:
        ValueError: On an unknown policy or metric.
    """
    if policy not in ("lexicographic", "weighted", "pareto"):
        raise ValueError(f"policy must be lexicographic, weighted or pareto, got {policy!r}")
    parsed = [Objective.parse(o) for o in (objectives or list(DEFAULT_OBJECTIVES))]
    variants = comparison.variants
    front = pareto_front(variants, parsed)
    unknown = {
        v.variant: [o.metric for o in parsed if v.metric(o.metric) is None] for v in variants
    }
    unknown = {name: metrics for name, metrics in unknown.items() if metrics}
    scores: dict[str, float] = {}

    def lexicographic(pool: list[VariantStats]) -> list[str]:
        return [v.variant for v in sorted(pool, key=lambda v: [o.key(v) for o in parsed])]

    if policy == "weighted":
        weight_of = {o.metric: (weights or {}).get(o.metric, 1.0) for o in parsed}
        for v in variants:
            total = 0.0
            for objective in parsed:
                values = [
                    value for x in variants if (value := x.metric(objective.metric)) is not None
                ]
                value = v.metric(objective.metric)
                if value is None or not values:
                    scaled = 0.0
                elif max(values) == min(values):
                    scaled = 1.0
                else:
                    low, high = min(values), max(values)
                    scaled = (value - low) / (high - low)
                    if objective.direction == "min":
                        scaled = 1.0 - scaled
                total += weight_of[objective.metric] * scaled
            scores[v.variant] = round(total, 12)
        ranking = sorted(scores, key=lambda name: -scores[name])
        reason = "highest weighted score"
    elif policy == "pareto":
        ranking = lexicographic([v for v in variants if v.variant in front]) + lexicographic(
            [v for v in variants if v.variant not in front]
        )
        reason = (
            "the only variant on the Pareto front"
            if len(front) == 1
            else f"best on {parsed[0].metric} among {len(front)} variants on the Pareto front"
        )
    else:
        ranking = lexicographic(variants)
        reason = "best on " + ", then ".join(o.metric for o in parsed)
    chosen = ranking[0] if ranking else None
    if chosen and chosen in unknown:
        reason += f" (its {', '.join(unknown[chosen])} is unknown and ranked worst)"
    return Selection(chosen, policy, parsed, ranking, front, scores, unknown, reason)


# -- pre-declared decision rules ------------------------------------------------------


@dataclass
class RuleOutcome:
    """One protocol rule, evaluated: ``status`` is pass, fail or unknown."""

    id: str
    status: str
    detail: str


@dataclass
class ProtocolResult:
    """The result of :func:`evaluate_protocol`.

    Attributes:
        title: The protocol's title.
        protocol_sha256: Hash of the protocol as declared (record it before the runs).
        baseline: The baseline variant.
        candidate: The candidate variant.
        rules: Each rule's outcome.
        decision: ``"adopt"`` (every rule passed), ``"reject"`` (a rule failed)
            or ``"undecided"`` (a rule is unknown and none failed).
    """

    title: str
    protocol_sha256: str
    baseline: str
    candidate: str
    rules: list[RuleOutcome]
    decision: str

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe report."""
        return {**asdict(self), "rules": [asdict(r) for r in self.rules]}


_PROTOCOL_KEYS = {
    "protocol_version",
    "title",
    "baseline",
    "candidate",
    "alpha",
    "min_runs",
    "rules",
}
_RULE_KEYS = {"id", "metric", "expect", "min", "max", "tolerance"}


def load_protocol(path: str | Path) -> dict[str, Any]:
    """Read a protocol file (YAML with ``pip install "tool-scorer[yaml]"``, or JSON)."""
    from toolscore.mcp.fixtures import load_structured_file

    data = load_structured_file(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: a protocol must be a mapping")
    return data


def evaluate_protocol(protocol: dict[str, Any], comparison: Comparison) -> ProtocolResult:
    """Evaluate decision rules declared before the runs.

    Protocol keys: ``protocol_version`` (1), ``title``, ``baseline``,
    ``candidate``, ``alpha`` (0.05), ``min_runs`` (runs per variant before any
    rule can pass; default the comparison's ``min_n``) and ``rules``. Each rule
    has an ``id``, a ``metric`` (:data:`OBJECTIVE_METRICS`) and one of:

    * ``expect: candidate_better``: the candidate is better than the baseline
      (for ``pass_rate``: distinguishable by the Fisher test and the intervals;
      for other metrics: better by more than ``tolerance``);
    * ``expect: not_worse``: the candidate is not worse by more than
      ``tolerance`` (default 0);
    * ``min`` / ``max``: bounds on the candidate's value.

    A rule whose metric is unknown, or whose variants have fewer than
    ``min_runs`` runs, is ``unknown``, never a pass.

    Raises:
        ValueError: On unknown keys, variants or metrics.
    """
    from toolscore.receipts import json_sha256

    unknown_keys = set(protocol) - _PROTOCOL_KEYS
    if unknown_keys:
        raise ValueError(f"unknown protocol key(s): {sorted(unknown_keys)}")
    stats = comparison.by_name()
    baseline, candidate = str(protocol.get("baseline", "")), str(protocol.get("candidate", ""))
    for role, name in (("baseline", baseline), ("candidate", candidate)):
        if name not in stats:
            raise ValueError(f"protocol {role} {name!r} is not a variant ({sorted(stats)})")
    alpha = float(protocol.get("alpha", comparison.alpha))
    min_runs = int(protocol.get("min_runs", comparison.min_n))
    base, cand = stats[baseline], stats[candidate]
    outcomes: list[RuleOutcome] = []
    for index, rule in enumerate(protocol.get("rules") or []):
        if not isinstance(rule, dict):
            raise ValueError(f"rule {index} must be a mapping")
        bad = set(rule) - _RULE_KEYS
        if bad:
            raise ValueError(f"rule {index}: unknown key(s) {sorted(bad)}")
        rule_id = str(rule.get("id") or f"rule-{index + 1}")
        metric = str(rule.get("metric", ""))
        if metric not in OBJECTIVE_METRICS:
            raise ValueError(f"rule {rule_id}: unknown metric {metric!r}")
        direction = OBJECTIVE_METRICS[metric]
        tolerance = float(rule.get("tolerance", 0.0))
        cand_value, base_value = cand.metric(metric), base.metric(metric)
        if min(base.n, cand.n) < min_runs:
            outcomes.append(
                RuleOutcome(rule_id, "unknown", f"fewer than {min_runs} runs ({base.n}, {cand.n})")
            )
            continue
        if cand_value is None or (rule.get("expect") and base_value is None):
            outcomes.append(RuleOutcome(rule_id, "unknown", f"{metric} is unknown"))
            continue
        checks: list[tuple[bool, str]] = []
        if "min" in rule:
            checks.append(
                (cand_value >= float(rule["min"]), f"{metric} {cand_value:.4g} >= {rule['min']}")
            )
        if "max" in rule:
            checks.append(
                (cand_value <= float(rule["max"]), f"{metric} {cand_value:.4g} <= {rule['max']}")
            )
        expect = rule.get("expect")
        if expect is not None:
            assert base_value is not None
            gain = (cand_value - base_value) if direction == "max" else (base_value - cand_value)
            if expect == "candidate_better":
                if metric in ("pass_rate", "pass_lower"):
                    pair = compare_pair(base, cand, min_runs, alpha)
                    checks.append((pair.distinguishable and gain > 0, pair.verdict))
                else:
                    checks.append((gain > tolerance, f"{metric} gain {gain:+.4g} > {tolerance}"))
            elif expect == "not_worse":
                checks.append((gain >= -tolerance, f"{metric} change {gain:+.4g} >= -{tolerance}"))
            else:
                raise ValueError(f"rule {rule_id}: expect must be candidate_better or not_worse")
        if not checks:
            raise ValueError(f"rule {rule_id}: needs expect, min or max")
        ok = all(result for result, _ in checks)
        outcomes.append(
            RuleOutcome(rule_id, "pass" if ok else "fail", "; ".join(text for _, text in checks))
        )
    statuses = [o.status for o in outcomes]
    decision = (
        "reject" if "fail" in statuses else ("undecided" if "unknown" in statuses else "adopt")
    )
    return ProtocolResult(
        title=str(protocol.get("title") or ""),
        protocol_sha256=json_sha256(protocol),
        baseline=baseline,
        candidate=candidate,
        rules=outcomes,
        decision=decision,
    )
