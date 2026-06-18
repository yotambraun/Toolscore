# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and uses [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## [Unreleased]

### Highlights

- **Snapshot testing — record, approve, replay.** Stop hand-writing expected tool calls: `toolscore init` scaffolds a suite, the first `pytest` run records your agent's calls, `toolscore approve --all` blesses the baseline, and CI replays it forever. Jest snapshots for agents.
- **MCP Scorecard & instant health-check.** `toolscore mcp test "<server command>"` — or `toolscore demo` for a zero-setup sample server — auto-generates happy-path and edge-case scenarios from tool schemas, runs them, lints definitions, measures each tool's context-token cost, and prints an A–F grade with a ranked **Top issues to fix** list and concrete fixes. Export Markdown reports and gate CI with `--fail-under` or `--ci` (writes the verdict to `$GITHUB_STEP_SUMMARY` and fails on blocking issues) — the first standard testing tool for MCP servers.
- **Fluent `expect()` API, matchers, and rich diffs.** `expect(agent).on(prompt).calls("tool", arg=ANY).does_not_call(...).with_score(0.9).run()`, with `ANY`/`Regex`/`Approx`/`Contains`/`OneOf`/`IsType` matchers and aligned expected-vs-actual failure tables.
- **Native everywhere.** Raw responses from OpenAI, Anthropic, Gemini, LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, and CrewAI (experimental) go straight into `evaluate()`/`expect()`/snapshots — zero glue. Async agents via `test_agent_async()` / `.run_async()`.
- **LLM judge for every provider.** Optional semantic judging via OpenAI, Anthropic, Gemini, or any OpenAI-compatible endpoint (Ollama/vLLM/Groq) — one `judge=` parameter and matching `[llm]`/`[anthropic]`/`[gemini]` extras.

### Added

#### Snapshot Testing
- `snapshot_check()`, `Snapshot`, and `SnapshotStore` — record-approve-replay state machine backed by plain JSON files under `.toolscore/snapshots/`
- `toolscore_snapshot` pytest fixture: records on first run, replays approved baselines, fails on drift, and prints a Jest-style terminal summary (`toolscore: 1 snapshot created (pending approval), 5 passed`)
- Pytest options `--toolscore-update` (re-record + re-approve), `--toolscore-snapshot-dir`, and `--toolscore-allow-pending`; `TOOLSCORE_RECORD_UPDATE=1` mirrors `--toolscore-update`
- CLI commands: `toolscore record` (subprocess or `--from-trace` mode), `toolscore approve [NAME|--all]`, and `toolscore snapshots list|show|rm`
- CI-safe by design: snapshots are never created or auto-approved when the `CI` env var is set — missing/pending snapshots fail the build

#### MCP Scorecard
- Zero-dependency MCP stdio client (`MCPStdioClient`) with config-file support for Claude Desktop style files (`--config` / `--server`)
- Scenario harness: happy-path and edge-case scenarios generated from each tool's input schema
- Schema linting (`lint_tools`) for missing descriptions, malformed schemas, undeclared required lists, and more
- `MCPScorecard` with an A–F grade blending happy-path pass rate (60%), edge resilience (20%), and lint cleanliness (20%)
- CLI commands: `toolscore mcp list`, `toolscore mcp lint`, `toolscore mcp test` with `--cases`, `--no-edge-cases`, `--report md|json --output`, and `--fail-under A-F`
- GitHub Action MCP mode: set `mcp-command` (and optionally `mcp-fail-under`) to grade an MCP server in CI instead of running the eval path

#### Fluent API, Matchers & Diffs
- `expect()` / `Expectation` fluent builder: `.on()`, `.calls()`, `.then_calls()`, `.does_not_call()`, `.with_score()`, `.with_weights()`, `.with_strict_args()`, `.run()`, `.run_async()`
- Argument matchers usable anywhere expected args appear: `ANY`, `Regex`, `Approx`, `Contains`, `OneOf`, `IsType`
- Rich failure diffs: `ToolScoreAssertionError` messages now embed an aligned expected-vs-actual table with per-argument mismatches and targeted tips (colored on a TTY, plain text in CI logs)

#### Framework & Async Support
- New extractors: `from_langgraph()`, `from_pydantic_ai()`, `from_openai_agents()`, `from_claude_agent_sdk()`, and `from_crewai()` (experimental); `auto_extract()` detects all of them, including list-shaped message formats
- `test_agent_async()` and `expect(...).run_async()` for async agents; sync entry points raise a clear `TypeError` pointing at the async variant

#### Multi-Provider LLM Judge
- `JudgeConfig` dataclass with provider inference from the model name (`claude-*` → Anthropic, `gemini-*` → Gemini, `base_url` → any OpenAI-compatible endpoint, otherwise OpenAI)
- CLI flags `--llm-model`, `--llm-provider`, and `--llm-base-url` on `toolscore eval` (e.g. Ollama: `--llm-model llama3.1 --llm-base-url http://localhost:11434/v1`)
- New extras: `tool-scorer[anthropic]` and `tool-scorer[gemini]`

#### Scaffolding & Quality
- `toolscore init` reworked into a framework-detecting wizard: detects your agent framework (LangGraph, Pydantic AI, OpenAI Agents SDK, Claude Agent SDK, CrewAI, raw SDKs, or generic), writes a pytest suite that passes immediately, and adds a snapshot-replay GitHub Actions workflow
- `evaluate()` validates inputs: `TypeError` for non-list `expected`, `ValueError` for unknown, negative, or non-finite weight keys; `assert_tools()`/`test_agent()` validate `min_score` range early
- `assert_score()` on `ToolscoreAssertions` and the `toolscore_assert_tools` fixture bridge the pytest plugin to the in-memory API
- `py.typed` marker (PEP 561) — mypy/pyright now see inline annotations
- Strict argument comparison mode (`strict=True` / `.with_strict_args()`): pure equality, no int/float coercion or string stripping

### Changed

**This release intentionally changes a few behaviors. Review these before upgrading:**

- **`evaluate_trace()` takes a single `judge` parameter.** The old `use_llm_judge`, `llm_judge_model`, and `llm_judge_api_key` keyword arguments are gone. Pass `judge=False` (default), `judge=True`, a model-name string, or a `JudgeConfig` — e.g. `evaluate_trace(gold, trace, judge=JudgeConfig(model="gemini-2.0-flash"))`.
- **Composite-score weights are renormalized.** Custom `weights=` are merged with the defaults and scaled so they sum to 1.0 before the composite score is computed. Scores produced with partial weight overrides may differ from previous releases; the relative ordering of metrics you emphasized is preserved.
- **Omitted gold arguments now mean "do not check arguments".** An expected call with `args` omitted (or `null`) is a tool-name-only expectation: the tool must be called, but any arguments are accepted. An explicit `"args": {}` keeps its strict meaning — "expect this tool to be called with zero arguments". This affects `argument_f1`, `tool_correctness`, trajectory, the composite score, gold-file loading, the fluent `.calls("tool")` (no kwargs = don't check args), and failure-diff rendering.
- **`ToolCall.args` preserves `None`.** It is no longer coerced to `{}` on construction, keeping "do not check" (`None`) distinct from "expect zero args" (`{}`). Code that assumed `.args` is always a dict should handle `None`.
- **The `min_accuracy` pytest marker is removed.** It was dead code; use `assert_tools(min_score=...)`, the `toolscore_snapshot` fixture, or the `toolscore_assert` helpers instead.
- **Importing `toolscore` no longer creates a `traces/` directory.** Trace capture creates its output directory lazily on first write, so simply importing the package leaves your filesystem untouched.
- Cost estimator pricing refreshed (February 2026), including a `claude-opus-4-6` entry.

### Fixed

- Zero-argument tool calls now score a perfect argument F1 when matched exactly (instead of being penalized as having no overlapping args)
- `evaluate()` routes `actual` through `auto_extract()`, so list-shaped raw formats (Claude Agent SDK / LangGraph message lists) are detected even when passed as plain lists
- LLM judge batching falls back to per-pair requests only on parse failures; transport and auth errors propagate instead of fanning out into doomed retries
- `MCPStdioClient.list_tools()` guards against runaway `nextCursor` pagination loops
- Argument comparison recurses strictly through nested dicts and lists
- `JudgeConfig` is exported from the package root

## [1.6.0]

### Added - Instant Value: Zero-Friction API

#### Auto-Detect Provider Responses
- **`auto_extract()`** — auto-detect OpenAI, Anthropic, and Gemini responses and extract tool calls
- **`evaluate()` and `assert_tools()` now accept raw provider responses** as the `actual` argument — no need to import or call `from_openai()` / `from_anthropic()` / `from_gemini()` manually
- Supports response objects (with `model_dump()`), plain dicts, and already-formatted lists

#### End-to-End Agent Testing
- **`test_agent()`** — run an agent callable, extract tool calls, evaluate, and optionally assert a minimum score, all in one call
- Accepts any callable that returns an LLM response (raw or pre-formatted)

#### Data-Driven Pytest Decorator
- **`@toolscore.cases()`** — parametrize pytest test functions with a list of test-case dicts
- Thin wrapper around `pytest.mark.parametrize` with automatic key extraction and test IDs
- Lazy pytest import avoids breaking non-pytest users

## [1.5.0]

### Added - In-Memory API, Integration Helpers & Simplified Output

#### In-Memory Python API
- **New `evaluate()` function** accepting Python dicts directly - no file I/O required
- **New `assert_tools()` one-liner** for pytest: `assert_tools(expected, actual, min_score=0.9)`
- **Composite `.score` property** on `EvaluationResult` (weighted average of key metrics)
- **Convenience properties**: `.selection_accuracy`, `.argument_f1`, `.sequence_accuracy`
- **Custom weights** support for composite score calculation
- **`ToolScoreAssertionError`** with detailed failure messages

#### Integration Helpers (`toolscore.integrations`)
- **`from_openai(response)`** - extract tool calls from OpenAI ChatCompletion responses
- **`from_anthropic(response)`** - extract tool calls from Anthropic Message responses
- **`from_gemini(response)`** - extract tool calls from Google Gemini responses
- Works with both response objects and plain dicts
- Supports modern and legacy formats (e.g., `tool_calls` and `function_call` for OpenAI)

#### Simplified CLI Output
- Default output now shows 4 key metrics: Overall Score, Selection Accuracy, Argument F1, Sequence Accuracy
- PASS/WARN/FAIL verdict with overall score
- Full detailed output available with `--verbose` flag
- Added `toolscore` as CLI alias alongside `tool-scorer`

#### README & Positioning
- New tagline: "Lightweight tool-call testing for LLM agents - deterministic, local, zero API cost"
- Leads with 3-line Python API example
- Honest comparison table including DeepEval, Ragas, and Inspect AI
- "When to use Toolscore vs. alternatives" section
- Advanced features moved to dedicated section

## [1.4.0] - 2026-01-09

### Added - Self-Explaining Metrics, Regression Testing & GitHub Action

#### Self-Explaining Metrics
- **Know exactly WHY your agent failed** with detailed explanations after each metric
- Automatic detection of tool name mismatches and similar names using SequenceMatcher
- Actionable tips like "use --llm-judge to catch semantic equivalence"
- Per-metric breakdowns showing MISSING, EXTRA, and MISMATCH items with severity levels
- New `toolscore/explainer.py` module with comprehensive explanation generation
- Categories: missing tools, extra tools, argument mismatches, type errors, value mismatches
- Tips tailored to specific failure patterns (low precision vs low recall, etc.)
- **Impact**: Users immediately understand what went wrong without manual debugging

#### Regression Testing (`toolscore regression`)
- **New CLI command** for CI/CD regression detection
- Save baselines with `--save-baseline` flag on `eval` command
- Automatic PASS/FAIL with configurable thresholds (default: 5%)
- Detailed delta reports showing improvements and regressions for each metric
- Exit codes: 0=PASS, 1=FAIL (regression), 2=ERROR
- Baseline includes:
  - Version tracking
  - Timestamp
  - Gold file hash for verification
  - All core metrics
- Comparison shows:
  - Baseline vs current values
  - Absolute delta and percentage change
  - Status per metric (REGRESSION/IMPROVED/OK)
- **Impact**: CI/CD pipelines can automatically catch agent degradation

#### GitHub Action
- **Official GitHub Action** for one-click CI setup
- Available on GitHub Actions Marketplace
- Supports both threshold and regression testing modes
- Features:
  - Automatic HTML report generation as artifacts
  - Job summary with evaluation results
  - Configurable accuracy thresholds
  - Regression testing against baselines
  - All trace format support
- Example usage:
  ```yaml
  - uses: yotambraun/toolscore@v1
    with:
      gold-file: tests/gold_standard.json
      trace-file: tests/agent_trace.json
      threshold: '0.90'
  ```
- **Impact**: Zero-config CI/CD setup for any repository

### Changed
- Enhanced console output with "What Went Wrong" section showing top issues
- Tips section now shows actionable suggestions based on detected problems
- Metrics table now shows self-explaining descriptions (e.g., "3 of 4 correct")
- Removed redundant "Suggestions for Improvement" section (replaced by new explainer)

### New Files
- `toolscore/explainer.py` - Self-explaining metrics generation
- `toolscore/baseline.py` - Baseline save/load/compare for regression testing
- `action.yml` - GitHub Action definition

## [1.2.0] - 2025-10-28

### Added - 🎯 Multi-Provider Support & Export Formats

#### 🤖 Google Gemini Adapter
- Full support for Google Gemini function calling traces
- Auto-detection for Gemini response format
- Handles multiple Gemini format variations:
  - `candidates` with `functionCall` (camelCase)
  - `function_call` (snake_case) alternative format
  - Direct `parts` list format
  - Mixed content with text and function calls
- Comprehensive test coverage (72.82%)
- **Impact**: Now supports all major LLM providers (OpenAI, Anthropic, Gemini)

#### 📊 CSV Export (`--csv`)
- Export evaluation results to CSV format for Excel/Google Sheets
- Human-readable formatting with percentage values
- Flattened metrics structure for easy sorting/filtering
- Ideal for sharing results with non-technical stakeholders
- 94.59% test coverage
- **Impact**: Business teams can analyze results in familiar spreadsheet tools

#### 📝 Markdown Export (`--markdown`)
- Export evaluation results to Markdown format for GitHub/docs
- Beautiful tables with status indicators (Excellent/Good/Fair/Needs Improvement)
- Collapsible details sections for clean PR comments
- Automatic timestamp and metadata
- Perfect for CI/CD workflows and pull request comments
- 81.38% test coverage
- **Impact**: Seamless integration with GitHub workflows

#### 💰 LLM Cost Estimation
- Built-in cost tracking with `calculate_llm_cost()` function
- Token estimation with `estimate_tokens()` function
- Trace-level cost estimation with `estimate_trace_cost()`
- Cost savings calculator with `calculate_cost_savings()`
- Up-to-date pricing for October 2025 models:
  - **OpenAI**: GPT-5 ($1.25/$10), GPT-5-mini, GPT-5-nano, GPT-4o, GPT-4o-mini
  - **Anthropic**: Sonnet 4.5 ($3/$15), Haiku 4.5 ($1/$5), Opus 4.1 ($15/$75)
  - **Google**: Gemini 2.5 Pro, 2.5 Flash, 2.5 Flash-Lite, 2.0 Flash
- Legacy model support for backward compatibility
- **Impact**: Quantify ROI and optimize agent costs

#### 🔧 CI/CD Integration Template
- Ready-to-use GitHub Actions workflow (`.github/workflows/toolscore-example.yml`)
- Automatic PR comments with evaluation results
- Quality gates with configurable thresholds
- CSV/Markdown/HTML report generation
- **Impact**: Zero-config CI/CD setup

#### 🛤️ Trajectory Evaluation
- Multi-step path analysis with `calculate_trajectory_accuracy()`
- Evaluates reasoning PATH taken by agent, not just final result
- Step-by-step comparison with detailed trajectory analysis
- Path efficiency metrics (penalizes unnecessary detours)
- Partial trajectory matching for flexible evaluation
- 89.29% test coverage with 13 comprehensive tests
- **Impact**: Industry-standard evaluation (matches BFCL V3/V4 capabilities)

#### 🔌 MCP (Model Context Protocol) Adapter
- Full support for Anthropic's Model Context Protocol (JSON-RPC 2.0)
- Auto-detection for MCP message format
- Handles tool requests, results, and error responses
- Batch call support
- 93.10% test coverage with 20 comprehensive tests
- **Impact**: Future-proof support for emerging open standard

#### 📦 Production Trace Capture
- `@capture_trace` decorator for capturing real agent executions
- Auto-save production traces as JSON test cases
- Convert captured traces to gold standard format
- Manual tool capture API with `TraceCapture` class
- **Impact**: Closes production→testing feedback loop

#### 🔍 Enhanced State Validators
- **FileSystemValidator**: Content validation (file contains text, size constraints)
- **SQLValidator**: Row-level validation (WHERE conditions, specific row matching)
- Deeper validation beyond simple existence checks
- **Impact**: State-based evaluation like BFCL V4

### Changed

- **Enhanced README**: Complete repositioning as "pytest for LLM agents"
- **Improved SEO**: Expanded PyPI keywords from 16 to 40+ for better discoverability
- **Updated Comparison Table**: Now compares against real competitors (LangSmith, OpenAI Evals, W&B)
- **CLI Enhancement**: Added `--csv` and `--markdown` flags to `eval` command
- **Format Support**: Added "gemini" option to all format-related commands

### Testing

- Increased test coverage from 47.80% to 55.05% (+7.25%)
- Added 63 comprehensive tests across new features (31 from initial features, 32 from advanced features)
- All 215 tests passing with zero bugs
- Strict mypy type checking compliance maintained
- New test suites:
  - 13 trajectory evaluation tests
  - 20 MCP adapter tests
  - Enhanced validator tests

## [1.1.0] - 2025-10-18

### Added - 🎯 Week 2: Major UX & Developer Experience Improvements

#### 🚀 Zero-Friction Onboarding (`toolscore init`)
- **Interactive CLI command** for project setup in 30 seconds
- Choose from 5 pre-built agent types (Weather, E-commerce, Code, RAG, Multi-tool)
- Automatically generates gold standard templates, README, and example files
- **Impact**: Onboarding time: 1+ hour → 30 seconds

#### ⚡ Synthetic Test Generator (`toolscore generate`)
- Generate comprehensive test cases from OpenAI function schemas
- Automatic edge case and boundary value generation (60% normal, 20% boundary, 20% edge)
- Smart value generation based on parameter names (email, url, query, etc.)
- Schema validation metadata extraction
- **Impact**: Test creation time: hours → 30 seconds

#### 📊 Quick Compare (`toolscore compare`)
- Compare multiple model traces side-by-side in single command
- Color-coded performance comparison table
- Automatic ranking per metric with best model highlighted
- Overall winner calculation with weighted average scores
- JSON comparison report export
- **Impact**: Multi-model benchmarking: manual spreadsheet → 1 command

#### 🔍 Interactive Debug Mode (`--debug`)
- Step-by-step failure analysis with `--debug` flag on eval command
- Interactive navigation through mismatches (next/previous/quit)
- Side-by-side expected vs actual comparison tables
- Context-specific fix suggestions for each failure type
- Detailed failure categorization:
  - Missing tools (expected but never called)
  - Extra tools (called but not expected)
  - Tool name mismatches
  - Argument mismatches with field-by-field comparison
  - Missing calls (trace ended early)
  - Extra calls (redundant invocations)
- **Impact**: Debugging: manual JSON diffing → guided walkthrough

#### 💡 Actionable Error Messages
- Automatic detection of common failure patterns during evaluation
- Specific fix suggestions displayed in console output
- Suggests `--llm-judge` for tool name mismatches
- Suggests `--verbose` for schema validation errors
- Suggests reviewing logic for missing tools
- Suggests checking arguments for type/value errors
- **Impact**: Users know exactly what to fix instead of guessing

### Added - 🎯 Week 1: Core Evaluation Features

#### Tool Correctness Metric
- New metric measuring whether ALL expected tools were called
- Complements selection accuracy by checking coverage vs per-call matching
- Reports `missing_tools` and `extra_tools` lists
- Deterministic evaluation without LLM needed

#### Integrated LLM-as-a-Judge
- Semantic evaluation now built into core evaluation engine
- Simple `--llm-judge` CLI flag (no separate script needed)
- Catches semantically equivalent tool names (e.g., "search" vs "web_search")
- Configurable model selection with `--llm-model` option
- **Previously**: Separate script in metrics directory
- **Now**: Integrated with single flag

#### Parameter Schema Validation
- Validate argument types (string, integer, number, boolean, array, object)
- Numeric constraints (minimum, maximum)
- String constraints (minLength, maxLength, pattern regex)
- Enum validation for allowed values
- Required field checking
- Detailed error reporting with field-level validation failures
- Define schemas in gold standard metadata:
  ```json
  {
    "metadata": {
      "schema": {
        "query": {"type": "string", "minLength": 1},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100}
      }
    }
  }
  ```

#### Example Datasets
- 5 realistic gold standard templates included:
  - `weather_agent.json` (Beginner - API lookup)
  - `ecommerce_agent.json` (Intermediate - Shopping workflow)
  - `code_assistant.json` (Intermediate - Code search/edit)
  - `rag_agent.json` (Advanced - Retrieval pipeline)
  - `multi_tool_agent.json` (Advanced - Research workflow)
- Each includes schema validation examples and descriptions
- Located in `examples/datasets/` directory

### Added - 🎯 Previous Features

- **LLM-as-a-judge metrics** (now integrated): Optional semantic correctness evaluation using OpenAI API
  - `calculate_semantic_correctness()` function for single evaluations
  - `calculate_batch_semantic_correctness()` for batch processing
  - Detects semantically equivalent tool calls beyond exact string matching
  - Supports custom models (default: gpt-4o-mini)
- **LangChain adapter**: Support for LangChain agent traces
  - Legacy AgentAction format (`tool`, `tool_input`, `log`)
  - Modern ToolCall format (`name`, `args`, `id`)
  - Alternative action/action_input format
  - Auto-detection support
- Comprehensive test suite increasing coverage from 37% to 80%+
- Complete Sphinx documentation with ReadTheDocs integration
- Interactive Jupyter notebook tutorials (quickstart, custom formats, advanced metrics)
- Rich-formatted console output with color-coded metrics tables
- Pytest plugin for seamless test integration
- Python-semantic-release configuration for automated versioning
- Optional dependency groups: `llm`, `langchain`, `all`

### Changed

- **Enhanced console output** with new tables:
  - Tool Correctness metrics table
  - Schema Validation metrics table
  - Actionable suggestions section
- **Improved CLI help text** for all commands
- Updated CLI to include all new commands: `init`, `generate`, `compare`
- Enhanced documentation with comprehensive examples
- Improved README with "What's New in v1.1" section
- Better command organization in help output

### Fixed

- Windows console Unicode compatibility (removed emoji characters causing UnicodeEncodeError)
- SQLValidator now supports multiple database field name variations
- CLI tests updated for correct Click exit codes
- Moved manual test files to proper `tests/manual/` directory

## [0.1.0] - 2025-10-13

### Added

- Initial release of Toolscore
- Core evaluation engine for LLM tool usage
- Support for OpenAI, Anthropic, and custom trace formats
- Comprehensive metrics:
  - Invocation accuracy
  - Selection accuracy
  - Sequence edit distance
  - Argument F1 score
  - Redundant call rate
  - Side-effect validation (HTTP, filesystem, database)
  - Performance metrics (latency, cost)
- CLI with `eval` and `validate` commands
- JSON and HTML report generation
- Side-effect validators for HTTP, filesystem, and SQL operations
- Format auto-detection
- Adapters for multiple LLM providers

### Documentation

- README with quick start guide
- Example files for all supported formats
- API documentation
- Usage examples

[Unreleased]: https://github.com/yotambraun/Toolscore/compare/v1.6.0...HEAD
[1.6.0]: https://github.com/yotambraun/Toolscore/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/yotambraun/toolscore/compare/v1.4.2...v1.5.0
[1.4.0]: https://github.com/yotambraun/Toolscore/compare/v1.2.0...v1.4.0
[1.2.0]: https://github.com/yotambraun/Toolscore/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/yotambraun/Toolscore/compare/v0.1.0...v1.1.0
[0.1.0]: https://github.com/yotambraun/Toolscore/releases/tag/v0.1.0
