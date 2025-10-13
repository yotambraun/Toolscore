# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and uses [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## [Unreleased]

### Added

- **LLM-as-a-judge metrics**: Optional semantic correctness evaluation using OpenAI API
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
  - Added .env loading for optional features
  - Included expected output examples
- Rich-formatted console output with color-coded metrics tables
- Pytest plugin for seamless test integration
  - `toolscore_eval()` fixture for running evaluations in tests
  - `toolscore_assertions()` fixture with assertion helpers
  - `toolscore_gold_dir` and `toolscore_trace_dir` fixtures
  - Custom markers and CLI options
- Python-semantic-release configuration for automated versioning
- Optional dependency groups: `llm`, `langchain`, `all`

### Changed

- Updated CLI to include `langchain` format option in both `eval` and `validate` commands
- Enhanced documentation with LLM judge and LangChain examples
- Improved README with all new features and "What's New" section

### Fixed

- SQLValidator now supports multiple database field name variations
- CLI tests updated for correct Click exit codes
- Unicode compatibility for Windows console output
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

[Unreleased]: https://github.com/yotambraun/Toolscore/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yotambraun/Toolscore/releases/tag/v0.1.0
