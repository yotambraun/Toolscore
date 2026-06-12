"""Unit tests for the multi-provider LLM-as-a-judge subsystem.

No network calls: provider SDK clients are faked via monkeypatching. The
``_JudgeBackend`` seam is exercised directly, and SDK-missing scenarios are
simulated by manipulating ``sys.modules`` / ``builtins.__import__``.
"""

from __future__ import annotations

import builtins
import json
import warnings

import pytest

from toolscore.adapters.base import ToolCall
from toolscore.core import evaluate_trace
from toolscore.metrics import llm_judge
from toolscore.metrics.llm_judge import (
    JudgeConfig,
    calculate_semantic_correctness,
    infer_provider,
)


@pytest.fixture
def gold():
    return [
        ToolCall(tool="search", args={"query": "Python"}),
        ToolCall(tool="read_file", args={"path": "a.txt"}),
    ]


@pytest.fixture
def trace():
    return [
        ToolCall(tool="web_search", args={"q": "Python"}),
        ToolCall(tool="read", args={"file": "a.txt"}),
    ]


class FakeBackend:
    """A fake ``_JudgeBackend`` that returns a canned string and records calls."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.response


# --------------------------------------------------------------------------- #
# Provider inference matrix
# --------------------------------------------------------------------------- #


class TestProviderInference:
    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("gpt-4o-mini", "openai"),
            ("gpt-4o", "openai"),
            ("o1-preview", "openai"),
            ("claude-3-5-haiku", "anthropic"),
            ("claude-opus-4-8", "anthropic"),
            ("gemini-2.0-flash", "gemini"),
            ("gemini-1.5-pro", "gemini"),
            ("llama3.1", "openai"),  # unknown -> openai by default
        ],
    )
    def test_inferred_from_model_name(self, model, expected):
        assert infer_provider(JudgeConfig(model=model)) == expected

    def test_base_url_forces_openai_compatible(self):
        # base_url wins even for a claude-* model name.
        cfg = JudgeConfig(model="claude-3-5-haiku", base_url="http://localhost:11434/v1")
        assert infer_provider(cfg) == "openai_compatible"

    def test_explicit_provider_wins_over_name(self):
        cfg = JudgeConfig(model="gpt-4o-mini", provider="anthropic")
        assert infer_provider(cfg) == "anthropic"

    def test_base_url_wins_over_explicit_provider(self):
        cfg = JudgeConfig(model="gpt-4o-mini", provider="anthropic", base_url="http://x/v1")
        assert infer_provider(cfg) == "openai_compatible"


# --------------------------------------------------------------------------- #
# Env-var API key fallback per provider
# --------------------------------------------------------------------------- #


class TestApiKeyFallback:
    def test_openai_env_fallback(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        assert llm_judge._resolve_api_key(JudgeConfig(model="gpt-4o-mini"), "openai") == (
            "sk-openai"
        )

    def test_anthropic_env_fallback(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        cfg = JudgeConfig(model="claude-3-5-haiku")
        assert llm_judge._resolve_api_key(cfg, "anthropic") == "sk-ant"

    def test_gemini_env_fallback(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "g-key")
        cfg = JudgeConfig(model="gemini-2.0-flash")
        assert llm_judge._resolve_api_key(cfg, "gemini") == "g-key"

    def test_explicit_key_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        cfg = JudgeConfig(model="gpt-4o-mini", api_key="sk-explicit")
        assert llm_judge._resolve_api_key(cfg, "openai") == "sk-explicit"

    def test_missing_key_raises_value_error(self, monkeypatch, gold, trace):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="API key required"):
            calculate_semantic_correctness(gold, trace, judge="gpt-4o-mini")

    def test_openai_compatible_no_key_required(self, monkeypatch, gold, trace):
        # No key needed for a local OpenAI-compatible endpoint.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        backend = FakeBackend(
            json.dumps(
                [
                    {"index": 0, "score": 1.0, "explanation": "ok"},
                    {"index": 1, "score": 1.0, "explanation": "ok"},
                ]
            )
        )
        monkeypatch.setattr(llm_judge, "_make_backend", lambda config: backend)
        cfg = JudgeConfig(model="llama3.1", base_url="http://localhost:11434/v1")
        result = calculate_semantic_correctness(gold, trace, judge=cfg)
        assert result["semantic_score"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Backend selection: missing SDK -> ImportError with correct hint
# --------------------------------------------------------------------------- #


def _block_import(monkeypatch, *blocked: str) -> None:
    """Make ``import <blocked>`` raise ImportError."""
    import sys

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in blocked or any(name.startswith(b + ".") for b in blocked):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    for b in blocked:
        for mod in list(sys.modules):
            if mod == b or mod.startswith(b + "."):
                monkeypatch.delitem(sys.modules, mod, raising=False)


class TestMissingSDK:
    def test_openai_missing_hint(self, monkeypatch):
        _block_import(monkeypatch, "openai")
        with pytest.raises(ImportError, match=r"tool-scorer\[llm\]"):
            llm_judge._make_backend(JudgeConfig(model="gpt-4o-mini"))

    def test_anthropic_missing_hint(self, monkeypatch):
        _block_import(monkeypatch, "anthropic")
        with pytest.raises(ImportError, match=r"tool-scorer\[anthropic\]"):
            llm_judge._make_backend(JudgeConfig(model="claude-3-5-haiku"))

    def test_gemini_missing_hint(self, monkeypatch):
        _block_import(monkeypatch, "google")
        with pytest.raises(ImportError, match=r"tool-scorer\[gemini\]"):
            llm_judge._make_backend(JudgeConfig(model="gemini-2.0-flash"))

    def test_openai_compatible_missing_hint(self, monkeypatch):
        _block_import(monkeypatch, "openai")
        cfg = JudgeConfig(model="llama3.1", base_url="http://localhost:11434/v1")
        with pytest.raises(ImportError, match=r"tool-scorer\[llm\]"):
            llm_judge._make_backend(cfg)


# --------------------------------------------------------------------------- #
# Backend routing: correct backend class per provider (clients faked)
# --------------------------------------------------------------------------- #


class TestBackendRouting:
    def test_claude_routes_to_anthropic_backend(self, monkeypatch):
        constructed = {}

        class FakeAnthropicBackend:
            def __init__(self, config):
                constructed["anthropic"] = config

            def complete(self, system, prompt):  # pragma: no cover - not called
                return "{}"

        monkeypatch.setattr(llm_judge, "_AnthropicBackend", FakeAnthropicBackend)
        backend = llm_judge._make_backend(JudgeConfig(model="claude-3-5-haiku"))
        assert isinstance(backend, FakeAnthropicBackend)
        assert constructed["anthropic"].model == "claude-3-5-haiku"

    def test_gemini_routes_to_gemini_backend(self, monkeypatch):
        class FakeGeminiBackend:
            def __init__(self, config):
                self.config = config

            def complete(self, system, prompt):  # pragma: no cover
                return "{}"

        monkeypatch.setattr(llm_judge, "_GeminiBackend", FakeGeminiBackend)
        backend = llm_judge._make_backend(JudgeConfig(model="gemini-2.0-flash"))
        assert isinstance(backend, FakeGeminiBackend)

    def test_openai_compatible_routes_to_openai_backend(self, monkeypatch):
        seen = {}

        class FakeOpenAIBackend:
            def __init__(self, config, provider):
                seen["provider"] = provider

            def complete(self, system, prompt):  # pragma: no cover
                return "{}"

        monkeypatch.setattr(llm_judge, "_OpenAIBackend", FakeOpenAIBackend)
        cfg = JudgeConfig(model="llama3.1", base_url="http://x/v1")
        backend = llm_judge._make_backend(cfg)
        assert isinstance(backend, FakeOpenAIBackend)
        assert seen["provider"] == "openai_compatible"


# --------------------------------------------------------------------------- #
# Batched judging + fallback + dict shape
# --------------------------------------------------------------------------- #

EXPECTED_KEYS = {
    "semantic_score",
    "per_call_scores",
    "explanations",
    "model_used",
    "gold_count",
    "trace_count",
}


class TestBatchedJudging:
    @pytest.fixture(autouse=True)
    def _api_key(self, monkeypatch):
        # Backend is faked in every test here; provide a key so the early
        # key-presence check passes for the default (openai) provider.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def test_batched_array_parsed(self, monkeypatch, gold, trace):
        backend = FakeBackend(
            json.dumps(
                [
                    {"index": 0, "score": 0.9, "explanation": "close"},
                    {"index": 1, "score": 0.8, "explanation": "ok"},
                ]
            )
        )
        monkeypatch.setattr(llm_judge, "_make_backend", lambda config: backend)
        result = calculate_semantic_correctness(gold, trace, judge="gpt-4o-mini")

        # One batched request, not per-pair.
        assert len(backend.calls) == 1
        assert result["per_call_scores"] == [0.9, 0.8]
        assert result["explanations"] == ["close", "ok"]
        assert result["semantic_score"] == pytest.approx(0.85)
        assert result["model_used"] == "gpt-4o-mini"
        assert result["gold_count"] == 2
        assert result["trace_count"] == 2
        assert set(result.keys()) == EXPECTED_KEYS

    def test_code_fenced_json_parsed(self, monkeypatch, gold, trace):
        fenced = (
            "```json\n"
            + json.dumps(
                [
                    {"index": 0, "score": 1.0, "explanation": "x"},
                    {"index": 1, "score": 1.0, "explanation": "y"},
                ]
            )
            + "\n```"
        )
        backend = FakeBackend(fenced)
        monkeypatch.setattr(llm_judge, "_make_backend", lambda config: backend)
        result = calculate_semantic_correctness(gold, trace)
        assert result["per_call_scores"] == [1.0, 1.0]
        assert len(backend.calls) == 1

    def test_out_of_order_indices_reordered(self, monkeypatch, gold, trace):
        backend = FakeBackend(
            json.dumps(
                [
                    {"index": 1, "score": 0.2, "explanation": "second"},
                    {"index": 0, "score": 0.7, "explanation": "first"},
                ]
            )
        )
        monkeypatch.setattr(llm_judge, "_make_backend", lambda config: backend)
        result = calculate_semantic_correctness(gold, trace)
        assert result["per_call_scores"] == [0.7, 0.2]
        assert result["explanations"] == ["first", "second"]

    def test_malformed_json_falls_back_to_per_pair(self, monkeypatch, gold, trace):
        responses = iter(
            [
                "not json at all",  # batched attempt fails
                json.dumps({"score": 0.5, "explanation": "p0"}),
                json.dumps({"score": 0.6, "explanation": "p1"}),
            ]
        )

        class SequencedBackend:
            def __init__(self):
                self.calls = 0

            def complete(self, system, prompt):
                self.calls += 1
                return next(responses)

        backend = SequencedBackend()
        monkeypatch.setattr(llm_judge, "_make_backend", lambda config: backend)
        result = calculate_semantic_correctness(gold, trace)

        # 1 batched (failed) + 2 per-pair requests.
        assert backend.calls == 3
        assert result["per_call_scores"] == [0.5, 0.6]
        assert result["explanations"] == ["p0", "p1"]
        assert set(result.keys()) == EXPECTED_KEYS

    def test_wrong_length_array_falls_back(self, monkeypatch, gold, trace):
        responses = iter(
            [
                json.dumps([{"index": 0, "score": 1.0, "explanation": "only one"}]),
                json.dumps({"score": 0.4, "explanation": "p0"}),
                json.dumps({"score": 0.3, "explanation": "p1"}),
            ]
        )

        class SequencedBackend:
            def __init__(self):
                self.calls = 0

            def complete(self, system, prompt):
                self.calls += 1
                return next(responses)

        backend = SequencedBackend()
        monkeypatch.setattr(llm_judge, "_make_backend", lambda config: backend)
        result = calculate_semantic_correctness(gold, trace)
        assert backend.calls == 3
        assert result["per_call_scores"] == [0.4, 0.3]

    def test_object_wrapped_array_parsed(self, monkeypatch, gold, trace):
        backend = FakeBackend(
            json.dumps(
                {
                    "results": [
                        {"index": 0, "score": 0.5, "explanation": "a"},
                        {"index": 1, "score": 0.5, "explanation": "b"},
                    ]
                }
            )
        )
        monkeypatch.setattr(llm_judge, "_make_backend", lambda config: backend)
        result = calculate_semantic_correctness(gold, trace)
        assert result["per_call_scores"] == [0.5, 0.5]
        assert len(backend.calls) == 1

    def test_length_mismatch_penalty(self, monkeypatch):
        gold = [
            ToolCall(tool="a", args={}),
            ToolCall(tool="b", args={}),
        ]
        trace = [ToolCall(tool="a", args={})]  # only one trace call
        backend = FakeBackend(json.dumps([{"index": 0, "score": 1.0, "explanation": "match"}]))
        monkeypatch.setattr(llm_judge, "_make_backend", lambda config: backend)
        result = calculate_semantic_correctness(gold, trace)
        # min_len == 1, perfect pair score 1.0, but length mismatch halves it.
        assert result["semantic_score"] == pytest.approx(0.5)
        assert result["gold_count"] == 2
        assert result["trace_count"] == 1

    def test_empty_calls(self, monkeypatch):
        backend = FakeBackend("[]")
        monkeypatch.setattr(llm_judge, "_make_backend", lambda config: backend)
        result = calculate_semantic_correctness([], [], judge="gpt-4o-mini")
        assert result["semantic_score"] == 0.0
        assert result["per_call_scores"] == []
        assert len(backend.calls) == 0  # nothing to judge


# --------------------------------------------------------------------------- #
# evaluate_trace integration
# --------------------------------------------------------------------------- #


def _write_files(tmp_path):
    gold_file = tmp_path / "gold.json"
    trace_file = tmp_path / "trace.json"
    gold_file.write_text(json.dumps([{"tool": "search", "args": {"query": "x"}}]))
    trace_file.write_text(json.dumps([{"tool": "search", "args": {"query": "x"}}]))
    return gold_file, trace_file


class TestEvaluateTraceIntegration:
    def test_judge_false_skips_semantic(self, tmp_path):
        gold_file, trace_file = _write_files(tmp_path)
        result = evaluate_trace(gold_file, trace_file, judge=False)
        assert "semantic_metrics" not in result.metrics

    def test_judge_true_with_sdk_missing_warns(self, tmp_path, monkeypatch):
        gold_file, trace_file = _write_files(tmp_path)

        def boom(*args, **kwargs):
            raise ImportError("openai package required. Install with: pip install tool-scorer[llm]")

        monkeypatch.setattr("toolscore.core.calculate_semantic_correctness", boom)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = evaluate_trace(gold_file, trace_file, judge=True)

        assert any(issubclass(w.category, UserWarning) for w in caught)
        assert any("tool-scorer[llm]" in str(w.message) for w in caught)
        # Graceful skip: no crash, no semantic metrics recorded.
        assert "semantic_metrics" not in result.metrics

    def test_judge_string_routes_to_anthropic(self, tmp_path, monkeypatch):
        gold_file, trace_file = _write_files(tmp_path)
        captured = {}

        class FakeAnthropicBackend:
            def __init__(self, config):
                captured["model"] = config.model

            def complete(self, system, prompt):
                return json.dumps([{"index": 0, "score": 1.0, "explanation": "ok"}])

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        monkeypatch.setattr(llm_judge, "_AnthropicBackend", FakeAnthropicBackend)

        result = evaluate_trace(gold_file, trace_file, judge="claude-3-5-haiku")
        assert captured["model"] == "claude-3-5-haiku"
        assert result.metrics["semantic_metrics"]["semantic_score"] == pytest.approx(1.0)
        assert result.metrics["semantic_metrics"]["model_used"] == "claude-3-5-haiku"

    def test_judge_missing_api_key_records_error(self, tmp_path, monkeypatch):
        gold_file, trace_file = _write_files(tmp_path)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = evaluate_trace(gold_file, trace_file, judge=True)
        sem = result.metrics["semantic_metrics"]
        assert sem["semantic_score"] is None
        assert "error" in sem

    def test_judge_config_object(self, tmp_path, monkeypatch):
        gold_file, trace_file = _write_files(tmp_path)

        class FakeAnthropicBackend:
            def __init__(self, config):
                pass

            def complete(self, system, prompt):
                return json.dumps([{"index": 0, "score": 0.7, "explanation": "ok"}])

        monkeypatch.setattr(llm_judge, "_AnthropicBackend", FakeAnthropicBackend)
        cfg = JudgeConfig(model="claude-opus-4-8", provider="anthropic", api_key="sk-ant")
        result = evaluate_trace(gold_file, trace_file, judge=cfg)
        assert result.metrics["semantic_metrics"]["semantic_score"] == pytest.approx(0.7)


# --------------------------------------------------------------------------- #
# CLI wiring
# --------------------------------------------------------------------------- #


class TestCliWiring:
    @pytest.fixture
    def cli_files(self, tmp_path):
        return _write_files(tmp_path)

    def _invoke(self, monkeypatch, cli_files, extra_args):
        from click.testing import CliRunner

        from toolscore.cli import main

        captured = {}

        def fake_evaluate_trace(gold, trace, **kwargs):
            captured["judge"] = kwargs.get("judge")
            from toolscore.core import EvaluationResult

            return EvaluationResult()

        monkeypatch.setattr("toolscore.cli.evaluate_trace", fake_evaluate_trace)
        gold_file, trace_file = cli_files
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["eval", str(gold_file), str(trace_file), *extra_args],
        )
        return result, captured

    def test_no_llm_judge_passes_false(self, monkeypatch, cli_files):
        result, captured = self._invoke(monkeypatch, cli_files, [])
        assert result.exit_code == 0, result.output
        assert captured["judge"] is False

    def test_llm_judge_builds_config(self, monkeypatch, cli_files):
        result, captured = self._invoke(monkeypatch, cli_files, ["--llm-judge"])
        assert result.exit_code == 0, result.output
        judge = captured["judge"]
        assert isinstance(judge, JudgeConfig)
        assert judge.model == "gpt-4o-mini"
        assert judge.provider is None
        assert judge.base_url is None

    def test_llm_model_and_provider_wired(self, monkeypatch, cli_files):
        result, captured = self._invoke(
            monkeypatch,
            cli_files,
            ["--llm-judge", "--llm-model", "claude-3-5-haiku", "--llm-provider", "anthropic"],
        )
        assert result.exit_code == 0, result.output
        judge = captured["judge"]
        assert judge.model == "claude-3-5-haiku"
        assert judge.provider == "anthropic"

    def test_llm_base_url_wired(self, monkeypatch, cli_files):
        result, captured = self._invoke(
            monkeypatch,
            cli_files,
            [
                "--llm-judge",
                "--llm-model",
                "llama3.1",
                "--llm-base-url",
                "http://localhost:11434/v1",
            ],
        )
        assert result.exit_code == 0, result.output
        judge = captured["judge"]
        assert judge.model == "llama3.1"
        assert judge.base_url == "http://localhost:11434/v1"
        assert infer_provider(judge) == "openai_compatible"
