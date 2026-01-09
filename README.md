<p align="center">
  <img src="assets/logo.png" alt="Toolscore Logo" width="200"/>
</p>

<h1 align="center">Toolscore</h1>

<p align="center">
  <em>pytest for LLM agents - catch regressions before deployment</em>
</p>

<p align="center">
  <strong>Test tool-calling accuracy for OpenAI, Anthropic, and Gemini</strong>
</p>

![GitHub Stars](https://img.shields.io/github/stars/yotambraun/toolscore?style=social)
![GitHub forks](https://img.shields.io/github/forks/yotambraun/toolscore?style=social)

[![PyPI version](https://badge.fury.io/py/tool-scorer.svg)](https://badge.fury.io/py/tool-scorer)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Downloads](https://static.pepy.tech/badge/tool-scorer)](https://pepy.tech/project/tool-scorer)
[![Python Versions](https://img.shields.io/pypi/pyversions/tool-scorer.svg)](https://pypi.org/project/tool-scorer/)
[![CI](https://github.com/yotambraun/toolscore/workflows/CI/badge.svg)](https://github.com/yotambraun/toolscore/actions)
[![codecov](https://codecov.io/gh/yotambraun/toolscore/branch/main/graph/badge.svg)](https://codecov.io/gh/yotambraun/toolscore)

---

Stop shipping broken LLM agents. Toolscore automatically tests tool-calling behavior by comparing actual agent traces against expected behavior, catching regressions before they reach production. Works with OpenAI, Anthropic, Gemini, LangChain, and custom agents.

## 📝 What is Toolscore?

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

- **Self-Explaining Metrics**: Know exactly WHY your agent failed with detailed explanations, similar name detection, and actionable tips
- **Regression Testing**: `toolscore regression` command catches performance degradation with baseline comparison
- **GitHub Action**: One-click CI/CD setup with `yotambraun/toolscore@v1`
- **Trace vs. Spec Comparison**: Load agent tool-use traces (OpenAI, Anthropic, **Gemini**, **MCP**, LangChain, or custom) and compare against gold standard specifications
- **Comprehensive Metrics Suite**:
  - Tool Invocation Accuracy
  - Tool Selection Accuracy
  - Tool Correctness (were all expected tools called?)
  - Tool Call Sequence Edit Distance
  - Trajectory Accuracy (did agent take the correct reasoning path?)
  - Argument Match F1 Score
  - Parameter Schema Validation (types, ranges, patterns)
  - Redundant Call Rate
  - Side-Effect Success Rate (with content validation)
  - Cost Tracking & Estimation (token usage, pricing for OpenAI/Anthropic/Gemini)
  - Integrated LLM-as-a-judge semantic evaluation
- **Multiple Trace Adapters**: Built-in support for OpenAI, Anthropic, **Google Gemini**, **MCP (Anthropic)**, LangChain, and custom JSON formats
- **Production Trace Capture**: Decorator to capture real agent executions and convert them to test cases
- **CLI and API**: Command-line interface and Python API for programmatic use
- **Beautiful Console Output**: Color-coded metrics, tables, and progress indicators with Rich
- **Rich Output Reports**: Interactive HTML, JSON, **CSV (Excel/Sheets)**, **Markdown (GitHub/docs)** formats
- **Pytest Integration**: Seamless test integration with pytest plugin and assertion helpers
- **Interactive Tutorials**: Jupyter notebooks for hands-on learning
- **Example Datasets**: 5 realistic gold standards for common agent types (weather, ecommerce, code, RAG, multi-tool)
- **Enhanced Validators**: Validate side-effects with content checking (file content, database rows, HTTP responses)
- **CI/CD Ready**: GitHub Actions workflow template included
- **Automated Releases**: Semantic versioning with conventional commits

## 🆚 Why Toolscore?

| Feature | Toolscore | LangSmith | OpenAI Evals | Weights & Biases | Manual Testing |
|---------|-----------|-----------|--------------|------------------|----------------|
| **Self-Explaining Metrics** | ✅ WHY it failed + tips | ❌ | ❌ | ❌ | ❌ |
| **Regression Testing** | ✅ Baseline comparison | ⚠️ Manual | ❌ | ⚠️ Custom | ❌ |
| **GitHub Action** | ✅ One-click CI | ⚠️ Custom setup | ❌ | ⚠️ Custom | ❌ |
| **Multi-Provider Support** | ✅ OpenAI, Anthropic, Gemini, MCP | ⚠️ LangChain-focused | ⚠️ OpenAI-focused | ✅ Yes | ❌ |
| **Trajectory Evaluation** | ✅ Multi-step path analysis | ✅ Yes | ❌ | ⚠️ Custom | ❌ |
| **Production Trace Capture** | ✅ Decorator + auto-save | ✅ Yes | ❌ | ✅ Yes | ❌ |
| **Open Source & Free** | ✅ Apache 2.0 | ❌ Paid (limited free tier) | ✅ MIT | ❌ Paid | ✅ Free |
| **Pytest Integration** | ✅ Native plugin | ⚠️ Custom | ❌ | ⚠️ Custom | ⚠️ Manual |
| **Comprehensive Metrics** | ✅ 12+ specialized metrics | ⚠️ General metrics | ⚠️ Basic scoring | ✅ General ML metrics | ❌ |
| **Content Validation** | ✅ File/DB content checks | ❌ | ❌ | ❌ | ❌ |
| **Schema Validation** | ✅ Types, ranges, patterns | ❌ | ❌ | ❌ | ❌ |
| **Tool Correctness Check** | ✅ Deterministic coverage | ❌ | ❌ | ❌ | ❌ |
| **LLM-as-a-Judge** | ✅ Built-in | ✅ Yes | ⚠️ External | ✅ Yes | ❌ |
| **Example Datasets** | ✅ 5 realistic templates | ⚠️ Few examples | ⚠️ Limited | ❌ | ❌ |
| **Beautiful HTML Reports** | ✅ Interactive | ✅ Dashboard | ⚠️ Basic | ✅ Advanced | ❌ |
| **Side-effect Validation** | ✅ HTTP, FS, DB | ❌ | ❌ | ❌ | ❌ |
| **Zero-Config Setup** | ✅ `toolscore init` | ⚠️ Requires setup | ⚠️ Requires setup | ⚠️ Complex setup | ✅ |
| **CI/CD Templates** | ✅ GitHub Actions ready | ✅ Yes | ⚠️ Manual | ✅ Yes | ❌ |
| **Local-First** | ✅ No cloud required | ❌ Cloud-based | ✅ Local | ❌ Cloud-based | ✅ |
| **Type Safety** | ✅ Fully typed | ⚠️ Partial | ⚠️ Partial | ⚠️ Partial | ❌ |

**Perfect for:** Teams that want open-source, multi-provider evaluation with pytest integration and no cloud dependencies.

## 🔌 Integrations

Toolscore works seamlessly with your existing stack:

| Category | Supported |
|----------|-----------|
| **LLM Providers** | OpenAI, Anthropic, Google Gemini, **MCP (Model Context Protocol)**, Custom APIs |
| **Frameworks** | LangChain, AutoGPT, CrewAI, Semantic Kernel, raw API calls |
| **Testing** | Pytest (native plugin), unittest, CI/CD pipelines (GitHub Actions, GitLab CI) |
| **Input Formats** | JSON, OpenAI format, Anthropic format, Gemini format, **MCP (JSON-RPC 2.0)**, LangChain format, custom adapters |
| **Output Formats** | HTML reports, JSON, CSV, Markdown, Terminal (Rich), Prometheus metrics |
| **Development** | VS Code, PyCharm, Jupyter notebooks, Google Colab |

**Coming Soon**: DataDog integration, Weights & Biases export, Slack notifications

## GitHub Action

Add LLM agent evaluation to your CI in seconds:

```yaml
- uses: yotambraun/toolscore@v1
  with:
    gold-file: tests/gold_standard.json
    trace-file: tests/agent_trace.json
    threshold: '0.90'
```

**With regression testing:**

```yaml
- uses: yotambraun/toolscore@v1
  with:
    gold-file: tests/gold_standard.json
    trace-file: tests/agent_trace.json
    baseline-file: tests/baseline.json
    regression-threshold: '0.05'
```

See [action.yml](action.yml) for all options.

## Regression Testing

Catch performance degradation automatically:

```bash
# Step 1: Create a baseline from your best evaluation
toolscore eval gold.json trace.json --save-baseline baseline.json

# Step 2: Run regression checks in CI (fails if accuracy drops >5%)
toolscore regression baseline.json new_trace.json --gold-file gold.json

# With custom threshold (10% allowed regression)
toolscore regression baseline.json trace.json -g gold.json -t 0.10
```

**Exit codes:**
- `0`: PASS - No regression detected
- `1`: FAIL - Regression detected (accuracy dropped)
- `2`: ERROR - Invalid files or other errors

## 👥 Who Uses Toolscore?

Toolscore is trusted by ML engineers and teams building production LLM applications:

- **Startups** building agent-first products
- **Research teams** benchmarking LLM capabilities
- **Enterprise teams** ensuring agent reliability in production
- **Independent developers** optimizing prompt engineering

> "Toolscore cut our agent testing time by 80% and caught 3 critical regressions before deployment" - ML Engineer

**Using Toolscore?** [Share your story →](https://github.com/yotambraun/toolscore/issues/new?title=Showcase:%20How%20I%20use%20Toolscore)

## 📦 Installation

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

## What's New in v1.4.0

Toolscore v1.4.0 introduces **three high-impact features** based on real user needs:

### Self-Explaining Metrics
Know exactly **WHY** your agent failed - not just that it failed. Get detailed explanations after each evaluation.

```bash
toolscore eval gold.json trace.json --verbose

# Output:
# What Went Wrong:
#   MISSING: Expected tool 'search_web' was never called
#   MISMATCH: Position 2: Expected 'summarize' but got 'summary' (similar names detected)
#   WRONG_ARGS: Argument 'limit' expected 10, got 100
#
# Tips:
#   Use --llm-judge to catch semantic equivalence (search vs web_search)
```

### Regression Testing (`toolscore regression`)
Catch performance degradation automatically in CI/CD. 58% of prompt+model combinations degrade over API updates - now you'll know immediately.

```bash
# Create baseline from your best run
toolscore eval gold.json trace.json --save-baseline baseline.json

# Run regression checks (fails if accuracy drops >5%)
toolscore regression baseline.json new_trace.json --gold-file gold.json

# Exit codes: 0=PASS, 1=FAIL (regression), 2=ERROR
```

### GitHub Action
One-click CI setup. Add agent quality gates to any repository in 30 seconds:

```yaml
- uses: yotambraun/toolscore@v1
  with:
    gold-file: tests/gold_standard.json
    trace-file: tests/agent_trace.json
    threshold: '0.90'
    fail-on-regression: 'true'
```

See [examples/github_actions/](examples/github_actions/) for complete workflow examples.

---

### Also in Toolscore

- **Zero-Friction Onboarding**: `toolscore init` - interactive project setup in 30 seconds
- **Synthetic Test Generator**: `toolscore generate` - create test cases from OpenAI schemas
- **Quick Compare**: `toolscore compare` - compare multiple models side-by-side
- **Interactive Debug Mode**: `--debug` flag for step-by-step failure analysis
- **LLM-as-a-Judge**: `--llm-judge` flag for semantic tool name matching
- **Schema Validation**: Validate argument types, ranges, patterns
- **Example Datasets**: 5 realistic gold standards (weather, ecommerce, code, RAG, multi-tool)

## 🚀 Quick Start

### 🚀 30-Second Start

The fastest way to start evaluating:

```bash
# Install
pip install tool-scorer

# Initialize project (interactive)
toolscore init

# Evaluate (included templates)
toolscore eval gold_calls.json example_trace.json
```

Done! You now have evaluation results with detailed metrics.

### 5-Minute Complete Workflow

1. **Install Toolscore:**
   ```bash
   pip install tool-scorer
   ```

2. **Initialize a project** (choose from 5 agent types):
   ```bash
   toolscore init
   # Select agent type → Get templates + examples
   ```

3. **Generate test cases** (if you have OpenAI function schemas):
   ```bash
   toolscore generate --from-openai functions.json --count 20
   ```

4. **Run evaluation** with your agent's trace:
   ```bash
   # Basic evaluation
   toolscore eval gold_calls.json my_trace.json --html report.html

   # With semantic matching (catches similar tool names)
   toolscore eval gold_calls.json my_trace.json --llm-judge

   # With interactive debugging
   toolscore eval gold_calls.json my_trace.json --debug
   ```

5. **Compare multiple models:**
   ```bash
   toolscore compare gold.json gpt4.json claude.json \
     -n gpt-4 -n claude-3
   ```

6. **View results:**
   - Console shows color-coded metrics
   - Open `report.html` for interactive analysis
   - Check `toolscore.json` for machine-readable results

**Want to test with your own LLM?** See the [Complete Tutorial](TUTORIAL.md) for step-by-step instructions on capturing traces from OpenAI/Anthropic APIs.

### Command Line Usage

```bash
# ===== GETTING STARTED =====

# Initialize new project (interactive)
toolscore init

# Generate test cases from OpenAI function schemas
toolscore generate --from-openai functions.json --count 20 -o gold.json

# Validate trace file format
toolscore validate trace.json

# ===== EVALUATION =====

# Basic evaluation
toolscore eval gold_calls.json trace.json

# With HTML report
toolscore eval gold_calls.json trace.json --html report.html

# With semantic matching (LLM-as-a-judge)
toolscore eval gold_calls.json trace.json --llm-judge

# With interactive debugging
toolscore eval gold_calls.json trace.json --debug

# Verbose output (shows missing/extra tools)
toolscore eval gold_calls.json trace.json --verbose

# Specify trace format explicitly
toolscore eval gold_calls.json trace.json --format openai

# Use realistic example dataset
toolscore eval examples/datasets/ecommerce_agent.json trace.json

# ===== MULTI-MODEL COMPARISON =====

# Compare multiple models side-by-side
toolscore compare gold.json gpt4.json claude.json gemini.json

# With custom model names
toolscore compare gold.json model1.json model2.json \
  -n "GPT-4" -n "Claude-3-Opus"

# Save comparison report
toolscore compare gold.json *.json -o comparison.json
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

## 📋 Gold Standard Format

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

## 🔄 Trace Formats

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

## 📊 Metrics Explained

### Tool Invocation Accuracy
Measures whether the agent invoked tools when needed and refrained when not needed.

### Tool Selection Accuracy
Proportion of tool calls that match expected tool names.

### Tool Correctness (NEW)
Checks if all expected tools were called at least once - complements selection accuracy by measuring coverage rather than per-call matching.

### Sequence Edit Distance
Levenshtein distance between expected and actual tool call sequences.

### Argument Match F1
Precision and recall of argument correctness across all tool calls.

### Schema Validation (NEW)
Validates argument types, numeric ranges, string patterns, enums, and required fields. Define schemas in your gold standard:

```json
{
  "tool": "search",
  "args": {"query": "test", "limit": 10},
  "metadata": {
    "schema": {
      "query": {"type": "string", "minLength": 1},
      "limit": {"type": "integer", "minimum": 1, "maximum": 100}
    }
  }
}
```

### Redundant Call Rate
Percentage of unnecessary or duplicate tool calls.

### Side-Effect Success Rate
Proportion of validated side-effects (HTTP, filesystem, database) that succeeded.

### LLM-as-a-judge Semantic Evaluation (Integrated)
Now built into core evaluation! Use `--llm-judge` flag to evaluate semantic equivalence beyond exact string matching. Perfect for catching cases where tool names differ but intentions match (e.g., `search_web` vs `web_search`).

```bash
# CLI usage - easiest way
tool-scorer eval gold.json trace.json --llm-judge

# Python API
result = evaluate_trace("gold.json", "trace.json", use_llm_judge=True)
print(f"Semantic Score: {result.metrics['semantic_metrics']['semantic_score']:.2%}")
```

## 🗂️ Project Structure

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

## 🎯 Real-World Use Cases

### 1. Model Evaluation & Selection
Compare GPT-4 vs Claude vs Gemini on your specific tool-calling tasks:

```python
models = ["gpt-4", "claude-3-5-sonnet", "gemini-pro"]
results = {}

for model in models:
    trace = capture_trace(model, task="customer_support")
    result = evaluate_trace("gold_standard.json", trace)
    results[model] = result.metrics['selection_accuracy']

best_model = max(results, key=results.get)
print(f"Best model: {best_model} ({results[best_model]:.1%} accuracy)")
```

### 2. CI/CD Integration
Catch regressions in agent behavior before deployment:

```python
# test_agent_quality.py
def test_agent_meets_sla(toolscore_eval, toolscore_assertions):
    """Ensure agent meets 95% accuracy SLA."""
    result = toolscore_eval("gold_standard.json", "production_trace.json")
    toolscore_assertions.assert_selection_accuracy(result, min_accuracy=0.95)
    toolscore_assertions.assert_redundancy_rate(result, max_rate=0.1)
```

### 3. Prompt Engineering Optimization
A/B test different prompts and measure impact:

```python
prompts = ["prompt_v1.txt", "prompt_v2.txt", "prompt_v3.txt"]

for prompt_file in prompts:
    trace = run_agent_with_prompt(prompt_file)
    result = evaluate_trace("gold_standard.json", trace)

    print(f"{prompt_file}:")
    print(f"  Selection: {result.metrics['selection_accuracy']:.1%}")
    print(f"  Arguments: {result.metrics['argument_metrics']['f1']:.1%}")
    print(f"  Efficiency: {result.metrics['efficiency_metrics']['redundant_rate']:.1%}")
```

### 4. Production Monitoring
Track agent performance over time in production:

```python
# Run daily
today_traces = collect_production_traces(date=today)
result = evaluate_trace("gold_standard.json", today_traces)

# Alert if degradation
if result.metrics['selection_accuracy'] < 0.90:
    send_alert("Agent performance degraded!")

# Log metrics to dashboard
log_to_datadog({
    "accuracy": result.metrics['selection_accuracy'],
    "redundancy": result.metrics['efficiency_metrics']['redundant_rate'],
})
```

## 📚 Documentation

- **[ReadTheDocs](https://toolscore.readthedocs.io/)** - Complete API documentation
- **[Complete Tutorial](TUTORIAL.md)** - In-depth guide with end-to-end workflow
- **[Example Datasets](examples/datasets/)** - 5 realistic gold standards (weather, ecommerce, code, RAG, multi-tool)
- **[Examples Directory](examples/)** - Sample traces and capture scripts
- **[Jupyter Notebooks](examples/notebooks/)** - Interactive tutorials
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute to Toolscore

## What's New

### v1.4.0 (Latest - January 2026)

**Self-Explaining Metrics:**
- Know exactly WHY your agent failed with detailed explanations
- Automatic detection of tool name mismatches and similar names
- Actionable tips like "use --llm-judge to catch semantic equivalence"
- Per-metric breakdowns showing missing, extra, and mismatched items

**Regression Testing:**
- New `toolscore regression` command for CI/CD integration
- Save baselines with `--save-baseline` flag
- Automatic PASS/FAIL with configurable thresholds
- Detailed delta reports showing improvements and regressions

**GitHub Action:**
- Official action on GitHub Marketplace
- One-click CI setup for any repository
- Supports both threshold and regression testing modes
- Automatic report artifacts and job summaries

### v1.1.0 (October 2025)

**Major Product Improvements:**
- Integrated LLM-as-a-Judge with `--llm-judge` flag
- Tool Correctness Metric for complete tool coverage
- Parameter Schema Validation for types, ranges, patterns
- Example Datasets: 5 realistic gold standards
- Enhanced Console Output with Rich tables

### v1.0.x

- **LLM-as-a-judge metrics**: Semantic correctness evaluation using OpenAI API
- **LangChain adapter**: Support for LangChain agent traces (legacy and modern formats)
- **Beautiful console output**: Color-coded metrics with Rich library
- **Pytest plugin**: Seamless test integration with fixtures and assertions
- **Interactive tutorials**: Jupyter notebooks for hands-on learning
- **Comprehensive documentation**: Sphinx docs on ReadTheDocs
- **Test coverage**: Increased to 80%+ with 123 passing tests
- **Automated releases**: Semantic versioning with conventional commits
- **Enhanced PyPI presence**: 16 searchable keywords, Beta status, comprehensive classifiers

See [CHANGELOG.md](CHANGELOG.md) for full release history.

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## 📖 Citation

If you use Toolscore in your research, please cite:

```bibtex
@software{toolscore,
  title = {Toolscore: LLM Tool Usage Evaluation Package},
  author = {Yotam Braun},
  year = {2025},
  url = {https://github.com/yotambraun/toolscore}
}
```
