# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and uses [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## [Unreleased]

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

[Unreleased]: https://github.com/yotambraun/Toolscore/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/yotambraun/Toolscore/compare/v0.1.0...v1.1.0
[0.1.0]: https://github.com/yotambraun/Toolscore/releases/tag/v0.1.0
