"""LLM-as-a-judge metrics for semantic evaluation.

This module uses large language models to evaluate the semantic correctness
of tool calls beyond simple syntactic matching.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from toolscore.adapters.base import ToolCall


def calculate_semantic_correctness(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """Calculate semantic correctness using LLM-as-a-judge.

    This metric uses an LLM to evaluate whether the trace calls are
    semantically equivalent to the gold standard calls, even if they
    differ syntactically.

    Args:
        gold_calls: Expected tool calls
        trace_calls: Actual tool calls from agent
        api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        model: OpenAI model to use (default: gpt-4o-mini)

    Returns:
        Dictionary containing:
        - semantic_score: Overall semantic correctness (0.0 to 1.0)
        - per_call_scores: List of scores for each call pair
        - explanations: List of explanations for each evaluation
        - model_used: The model that was used

    Raises:
        ImportError: If openai package is not installed
        ValueError: If API key is not provided or invalid

    Example:
        >>> gold = [ToolCall(tool="search", args={"query": "Python"})]
        >>> trace = [ToolCall(tool="web_search", args={"q": "Python"})]
        >>> result = calculate_semantic_correctness(gold, trace)
        >>> result["semantic_score"]
        0.95  # High score despite different naming
    """
    try:
        from openai import OpenAI
    except ImportError as e:
        raise ImportError(
            "openai package required for LLM judge metrics. "
            "Install with: pip install tool-scorer[llm]"
        ) from e

    # Get API key
    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OpenAI API key required. Set OPENAI_API_KEY environment variable "
            "or pass api_key parameter."
        )

    client = OpenAI(api_key=api_key)

    # If lengths don't match, we still evaluate what we have
    min_len = min(len(gold_calls), len(trace_calls))

    per_call_scores = []
    explanations = []

    for i in range(min_len):
        gold_call = gold_calls[i]
        trace_call = trace_calls[i]

        # Create evaluation prompt
        prompt = _create_evaluation_prompt(gold_call, trace_call)

        try:
            # Call OpenAI API
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert evaluator of LLM tool usage. "
                        "Evaluate whether two tool calls are semantically equivalent.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )

            # Parse response
            result_text = response.choices[0].message.content
            if result_text:
                result = json.loads(result_text)
                score = float(result.get("score", 0.0))
                explanation = result.get("explanation", "No explanation provided")
            else:
                score = 0.0
                explanation = "No response from model"

            per_call_scores.append(score)
            explanations.append(explanation)

        except Exception as e:
            # If API call fails, record it but continue
            per_call_scores.append(0.0)
            explanations.append(f"Evaluation failed: {e!s}")

    # Calculate overall score
    semantic_score = sum(per_call_scores) / len(per_call_scores) if per_call_scores else 0.0

    # Penalize length mismatch
    if len(gold_calls) != len(trace_calls):
        length_penalty = 1.0 - (abs(len(gold_calls) - len(trace_calls)) /
                                 max(len(gold_calls), len(trace_calls), 1))
        semantic_score *= length_penalty

    return {
        "semantic_score": semantic_score,
        "per_call_scores": per_call_scores,
        "explanations": explanations,
        "model_used": model,
        "gold_count": len(gold_calls),
        "trace_count": len(trace_calls),
    }


def _create_evaluation_prompt(gold_call: ToolCall, trace_call: ToolCall) -> str:
    """Create evaluation prompt for LLM judge.

    Args:
        gold_call: Expected tool call
        trace_call: Actual tool call

    Returns:
        Prompt string for LLM evaluation
    """
    return f"""Evaluate whether these two tool calls are semantically equivalent.

**Expected Tool Call:**
- Tool: {gold_call.tool}
- Arguments: {json.dumps(gold_call.args, indent=2)}

**Actual Tool Call:**
- Tool: {trace_call.tool}
- Arguments: {json.dumps(trace_call.args, indent=2)}

Evaluate semantic equivalence considering:
1. Tool names may differ but serve the same purpose (e.g., "search" vs "web_search")
2. Argument names may differ but contain the same data (e.g., "query" vs "q")
3. Argument values may be phrased differently but mean the same thing
4. Missing optional arguments are acceptable if they don't change the intent
5. Order of arguments doesn't matter

Respond with a JSON object:
{{
    "score": <float between 0.0 and 1.0>,
    "explanation": "<brief explanation of your evaluation>"
}}

Examples of scoring:
- 1.0: Semantically identical, same intent and data
- 0.8-0.9: Minor differences that don't affect meaning
- 0.5-0.7: Similar intent but significant differences
- 0.0-0.4: Different intent or missing critical information
- 0.0: Completely different or wrong tool/arguments"""


def calculate_batch_semantic_correctness(
    evaluations: list[tuple[list[ToolCall], list[ToolCall]]],
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """Calculate semantic correctness for multiple evaluations.

    This is useful for evaluating multiple test cases at once.

    Args:
        evaluations: List of (gold_calls, trace_calls) tuples
        api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        model: OpenAI model to use

    Returns:
        Dictionary containing:
        - average_score: Average semantic score across all evaluations
        - individual_scores: List of scores for each evaluation
        - total_evaluations: Number of evaluations performed
    """
    individual_scores = []

    for gold_calls, trace_calls in evaluations:
        result = calculate_semantic_correctness(
            gold_calls, trace_calls, api_key=api_key, model=model
        )
        individual_scores.append(result["semantic_score"])

    average_score = sum(individual_scores) / len(individual_scores) if individual_scores else 0.0

    return {
        "average_score": average_score,
        "individual_scores": individual_scores,
        "total_evaluations": len(evaluations),
    }
