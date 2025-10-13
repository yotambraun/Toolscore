# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
and uses [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## [Unreleased]

### Added

- Comprehensive test suite increasing coverage from 37% to 80%+
- Complete Sphinx documentation with ReadTheDocs integration
- Interactive Jupyter notebook tutorials (quickstart, custom formats, advanced metrics)
- Rich-formatted console output with color-coded metrics tables
- Pytest plugin for seamless test integration
  - `toolscore_eval()` fixture for running evaluations in tests
  - `toolscore_assert()` fixture with assertion helpers
  - Custom markers and CLI options
- Python-semantic-release configuration for automated versioning

### Fixed

- SQLValidator now supports multiple database field name variations
- CLI tests updated for correct Click exit codes
- Unicode compatibility for Windows console output

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
