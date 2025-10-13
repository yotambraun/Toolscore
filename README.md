# Toolscore

> A Python package for evaluating LLM tool usage against gold standard specifications

[![PyPI version](https://badge.fury.io/py/tool-scorer.svg)](https://badge.fury.io/py/tool-scorer)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Downloads](https://static.pepy.tech/badge/tool-scorer)](https://pepy.tech/project/tool-scorer)
[![Python Versions](https://img.shields.io/pypi/pyversions/tool-scorer.svg)](https://pypi.org/project/tool-scorer/)
[![CI](https://github.com/yotambraun/toolscore/workflows/CI/badge.svg)](https://github.com/yotambraun/toolscore/actions)
[![codecov](https://codecov.io/gh/yotambraun/toolscore/branch/main/graph/badge.svg)](https://codecov.io/gh/yotambraun/toolscore)

Toolscore helps developers evaluate the tool-using behavior of LLM-based agents by comparing recorded tool usage traces against gold-standard specifications, producing detailed metrics and reports.

## What is Toolscore?

**Toolscore evaluates LLM tool usage** - it doesn't call LLM APIs directly. Think of it as a testing framework for function-calling agents:

- ✅ **Evaluates** existing tool usage traces from OpenAI, Anthropic, or custom sources
- ✅ **Compares** actual behavior against expected gold standards
- ✅ **Reports** detailed metrics on accuracy, efficiency, and correctness
- ❌ **Does NOT** call LLM APIs or execute tools (you capture traces separately)

**Use Toolscore to:**
- Benchmark different LLM models on tool usage tasks
- Validate that your agent calls the right tools with the right arguments
- Track improvements in function calling accuracy over time
- Compare agent performance across different prompting strategies

## Features

- **Trace vs. Spec Comparison**: Load agent tool-use traces (OpenAI, Anthropic, LangChain, or custom) and compare against gold standard specifications
- **Comprehensive Metrics Suite**:
  - Tool Invocation Accuracy
  - Tool Selection Accuracy
  - Tool Call Sequence Edit Distance
  - Argument Match F1 Score
  - Redundant Call Rate
  - Side-Effect Success Rate
  - Latency/Cost Attribution
  - **NEW**: LLM-as-a-judge semantic correctness (optional)
- **Multiple Trace Adapters**: Built-in support for OpenAI, Anthropic Claude, LangChain, and custom JSON formats
- **CLI and API**: Command-line interface and Python API for programmatic use
- **Beautiful Console Output**: Color-coded metrics, tables, and progress indicators with Rich
- **Rich Output Reports**: Interactive HTML and machine-readable JSON reports
- **Pytest Integration**: Seamless test integration with pytest plugin and assertion helpers
- **Interactive Tutorials**: Jupyter notebooks for hands-on learning
- **Extensible Checks**: Validate side-effects like HTTP calls, file creation, database queries
- **Automated Releases**: Semantic versioning with conventional commits

## Installation

```bash
# Install from PyPI
pip install tool-scorer

# Or install from source
git clone https://github.com/yotambraun/toolscore.git
cd toolscore
pip install -e .
```

### Optional Dependencies

```bash
# Install with HTTP validation support
pip install tool-scorer[http]

# Install with LLM-as-a-judge metrics (requires OpenAI API key)
pip install tool-scorer[llm]

# Install with LangChain support
pip install tool-scorer[langchain]

# Install all optional features
pip install tool-scorer[all]
```

### Development Installation

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Install with dev + docs dependencies
pip install -e ".[dev,docs]"

# Or using uv (faster)
uv pip install -e ".[dev]"
```

## Quick Start

### 5-Minute Getting Started

1. **Install Toolscore:**
   ```bash
   pip install tool-scorer
   ```

2. **Run your first evaluation** (using included examples):
   ```bash
   tool-scorer eval examples/gold_calls.json examples/trace_openai.json --html report.html
   ```

3. **View results:**
   ```bash
   # Console output shows:
   Invocation Accuracy: 100.00%
   Selection Accuracy: 100.00%
   Sequence Accuracy: 100.00%

   # Open report.html in your browser for detailed analysis
   ```

4. **Want to test with your own LLM?** See the [Complete Tutorial](TUTORIAL.md) for step-by-step instructions on capturing traces from OpenAI/Anthropic APIs.

### Command Line Usage

```bash
# Evaluate a trace against gold standard
tool-scorer eval gold_calls.json trace.json

# Generate both JSON and HTML reports
tool-scorer eval gold_calls.json trace.json --html report.html

# Specify trace format explicitly
tool-scorer eval gold_calls.json trace.json --format openai

# Validate trace file format
tool-scorer validate trace.json
```

### Python API

```python
from toolscore import evaluate_trace

# Run evaluation
result = evaluate_trace(
    gold_file="gold_calls.json",
    trace_file="trace.json",
    format="auto"  # auto-detect format
)

# Access metrics
print(f"Invocation Accuracy: {result.metrics['invocation_accuracy']:.2%}")
print(f"Selection Accuracy: {result.metrics['selection_accuracy']:.2%}")

sequence = result.metrics['sequence_metrics']
print(f"Sequence Accuracy: {sequence['sequence_accuracy']:.2%}")

arguments = result.metrics['argument_metrics']
print(f"Argument F1: {arguments['f1']:.2%}")
```

### Pytest Integration

Toolscore includes a pytest plugin for seamless test integration:

```python
# test_my_agent.py
def test_agent_accuracy(toolscore_eval, toolscore_assertions):
    """Test that agent achieves high accuracy."""
    result = toolscore_eval("gold_calls.json", "trace.json")

    # Use built-in assertions
    toolscore_assertions.assert_invocation_accuracy(result, min_accuracy=0.9)
    toolscore_assertions.assert_selection_accuracy(result, min_accuracy=0.9)
    toolscore_assertions.assert_argument_f1(result, min_f1=0.8)
```

The plugin is automatically loaded when you install Toolscore. See the [examples](examples/test_example_with_pytest.py) for more patterns.

### Interactive Tutorials

Try Toolscore in your browser with our Jupyter notebooks:

- [Quickstart Tutorial](examples/notebooks/01_quickstart.ipynb) - 5-minute introduction
- [Custom Formats](examples/notebooks/02_custom_formats.ipynb) - Working with custom traces
- [Advanced Metrics](examples/notebooks/03_advanced_metrics.ipynb) - Deep dive into metrics

Open them in [Google Colab](https://colab.research.google.com/) for instant experimentation.

## Gold Standard Format

Create a `gold_calls.json` file defining the expected tool calls:

```json
[
  {
    "tool": "make_file",
    "args": {
      "filename": "poem.txt",
      "lines_of_text": ["Roses are red,", "Violets are blue."]
    },
    "side_effects": {
      "file_exists": "poem.txt"
    },
    "description": "Create a file with a poem"
  }
]
```

## Trace Formats

Toolscore supports multiple trace formats:

### OpenAI Format

```json
[
  {
    "role": "assistant",
    "function_call": {
      "name": "get_weather",
      "arguments": "{\"location\": \"Boston\"}"
    }
  }
]
```

### Anthropic Format

```json
[
  {
    "role": "assistant",
    "content": [
      {
        "type": "tool_use",
        "id": "toolu_123",
        "name": "search",
        "input": {"query": "Python"}
      }
    ]
  }
]
```

### LangChain Format

```json
[
  {
    "tool": "search",
    "tool_input": {"query": "Python tutorials"},
    "log": "Invoking search..."
  }
]
```

Or modern format:

```json
[
  {
    "name": "search",
    "args": {"query": "Python"},
    "id": "call_123"
  }
]
```

### Custom Format

```json
{
  "calls": [
    {
      "tool": "read_file",
      "args": {"path": "data.txt"},
      "result": "file contents"
    }
  ]
}
```

## Metrics Explained

### Tool Invocation Accuracy
Measures whether the agent invoked tools when needed and refrained when not needed.

### Tool Selection Accuracy
Proportion of tool calls that match expected tool names.

### Sequence Edit Distance
Levenshtein distance between expected and actual tool call sequences.

### Argument Match F1
Precision and recall of argument correctness across all tool calls.

### Redundant Call Rate
Percentage of unnecessary or duplicate tool calls.

### Side-Effect Success Rate
Proportion of validated side-effects (HTTP, filesystem, database) that succeeded.

### LLM-as-a-judge Semantic Correctness (Optional)
Uses OpenAI API to evaluate semantic equivalence beyond exact string matching. Great for catching cases where tool names differ but intentions match (e.g., `search_web` vs `web_search`).

```python
from toolscore.metrics import calculate_semantic_correctness

# Requires: pip install tool-scorer[llm]
# Set OPENAI_API_KEY environment variable
result = calculate_semantic_correctness(gold_calls, trace_calls)
print(f"Semantic Score: {result['semantic_score']:.2%}")
```

## Project Structure

```
toolscore/
├── adapters/          # Trace format adapters
│   ├── openai.py
│   ├── anthropic.py
│   └── custom.py
├── metrics/           # Metric calculators
│   ├── accuracy.py
│   ├── sequence.py
│   ├── arguments.py
│   └── ...
├── validators/        # Side-effect validators
│   ├── http.py
│   ├── filesystem.py
│   └── database.py
├── reports/           # Report generators
├── cli.py            # CLI interface
└── core.py           # Core evaluation logic
```

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=toolscore

# Type checking
mypy toolscore

# Linting and formatting
ruff check toolscore
ruff format toolscore
```

## Documentation

- **[ReadTheDocs](https://toolscore.readthedocs.io/)** - Complete API documentation
- **[Complete Tutorial](TUTORIAL.md)** - In-depth guide with end-to-end workflow
- **[Examples Directory](examples/)** - Sample traces and capture scripts
- **[Jupyter Notebooks](examples/notebooks/)** - Interactive tutorials
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute to Toolscore

## What's New

### v0.2.0 (Latest)

- **LLM-as-a-judge metrics**: Semantic correctness evaluation using OpenAI API
- **LangChain adapter**: Support for LangChain agent traces (legacy and modern formats)
- **Beautiful console output**: Color-coded metrics with Rich library
- **Pytest plugin**: Seamless test integration with fixtures and assertions
- **Interactive tutorials**: Jupyter notebooks for hands-on learning
- **Comprehensive documentation**: Sphinx docs on ReadTheDocs
- **Test coverage**: Increased to 80%+ with 123 passing tests
- **Automated releases**: Semantic versioning with conventional commits

See [CHANGELOG.md](CHANGELOG.md) for full release history.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Citation

If you use Toolscore in your research, please cite:

```bibtex
@software{toolscore,
  title = {Toolscore: LLM Tool Usage Evaluation Package},
  author = {Yotam Braun},
  year = {2025},
  url = {https://github.com/yotambraun/toolscore}
}
```
