# Contributing to Toolscore

Thank you for your interest in contributing to Toolscore! This document provides guidelines and instructions for contributing.

## Getting Started

### Development Setup

1. Fork and clone the repository:
```bash
git clone https://github.com/yourusername/toolscore.git
cd toolscore
```

2. Install development dependencies:
```bash
# Using pip
pip install -e ".[dev]"

# Or using uv (faster)
uv pip install -e ".[dev]"
```

3. Verify installation:
```bash
pytest
mypy toolscore
ruff check toolscore
```

## Development Workflow

### Code Style

We use modern Python tooling (2025 best practices):

- **Formatting**: `ruff format` (replaces Black)
- **Linting**: `ruff check` (replaces flake8, isort, etc.)
- **Type Checking**: `mypy` with strict mode
- **Testing**: `pytest` with coverage

Run all checks:
```bash
# Format code
ruff format toolscore tests

# Lint code
ruff check toolscore tests

# Type check
mypy toolscore

# Run tests
pytest --cov=toolscore
```

### Type Hints

All code must include type hints. We use strict mypy configuration:

```python
def calculate_metric(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
) -> float:
    """Calculate some metric.

    Args:
        gold_calls: Expected tool calls.
        trace_calls: Actual tool calls.

    Returns:
        Metric score between 0.0 and 1.0.
    """
    pass
```

### Testing

Write tests for all new functionality:

```python
# tests/unit/test_myfeature.py
import pytest
from toolscore.adapters.base import ToolCall

def test_my_feature() -> None:
    """Test my new feature."""
    # Arrange
    calls = [ToolCall(tool="test")]

    # Act
    result = my_function(calls)

    # Assert
    assert result is not None
```

Run tests:
```bash
# All tests
pytest

# Specific file
pytest tests/unit/test_adapters.py

# With coverage
pytest --cov=toolscore --cov-report=html
```

### Commit Messages

Use conventional commits format:

```
feat: add support for custom validators
fix: correct argument matching for nested dicts
docs: update README with new examples
test: add tests for OpenAI adapter
refactor: simplify metric calculation logic
```

### Pull Request Process

1. Create a feature branch:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes with tests and documentation

3. Ensure all checks pass:
```bash
pytest
mypy toolscore
ruff check toolscore
```

4. Commit your changes:
```bash
git add .
git commit -m "feat: add your feature"
```

5. Push and create a pull request:
```bash
git push origin feature/your-feature-name
```

## Adding New Features

### Adding a New Trace Adapter

1. Create new adapter in `toolscore/adapters/`:
```python
from toolscore.adapters.base import BaseAdapter, ToolCall

class MyAdapter(BaseAdapter):
    def parse(self, trace_data: dict[str, Any] | list[Any]) -> list[ToolCall]:
        # Implementation
        pass
```

2. Add tests in `tests/unit/test_adapters.py`

3. Export in `toolscore/adapters/__init__.py`

4. Update documentation

### Adding a New Metric

1. Create new metric in `toolscore/metrics/`:
```python
from toolscore.adapters.base import ToolCall

def calculate_my_metric(
    gold_calls: list[ToolCall],
    trace_calls: list[ToolCall],
) -> dict[str, float]:
    """Calculate my metric.

    Args:
        gold_calls: Expected tool calls.
        trace_calls: Actual tool calls.

    Returns:
        Dictionary with metric results.
    """
    pass
```

2. Add tests in `tests/unit/test_metrics.py`

3. Export in `toolscore/metrics/__init__.py`

4. Integrate in `toolscore/core.py`

5. Update documentation

### Adding a New Validator

1. Create validator in `toolscore/validators/`:
```python
from toolscore.adapters.base import ToolCall

class MyValidator:
    def validate(self, call: ToolCall, expected: Any) -> bool:
        # Implementation
        pass
```

2. Add tests

3. Register in `toolscore/core.py` validators dict

## Documentation

- Update README.md for user-facing changes
- Add docstrings to all public APIs (Google style)
- Update examples/ if adding new formats
- Add inline comments for complex logic

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions
- Check existing issues and PRs first

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

Thank you for contributing to Toolscore!
