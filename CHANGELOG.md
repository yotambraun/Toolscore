# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and uses [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## [Unreleased]

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

[Unreleased]: https://github.com/yotambraun/Toolscore/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/yotambraun/Toolscore/compare/v1.2.0...v1.4.0
[1.2.0]: https://github.com/yotambraun/Toolscore/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/yotambraun/Toolscore/compare/v0.1.0...v1.1.0
[0.1.0]: https://github.com/yotambraun/Toolscore/releases/tag/v0.1.0
