# Toolscore Jupyter Notebooks

Interactive tutorials for learning Toolscore.

## Notebooks

### 01_quickstart.ipynb
**5-Minute Introduction**

Learn the basics:
- Loading gold standards and traces
- Running evaluations
- Interpreting metrics
- Generating reports

**Best for**: Complete beginners, first-time users

### 02_custom_formats.ipynb
**Working with Custom Trace Formats**

Learn how to:
- Structure custom trace formats
- Create gold standards for custom workflows
- Evaluate non-standard traces
- Include performance metrics

**Best for**: Users with custom agent frameworks

### 03_advanced_metrics.ipynb
**Deep Dive into Metrics**

Understand:
- Each metric in detail
- When to use which metric
- How to optimize for specific metrics
- Model comparison strategies

**Best for**: Advanced users, researchers, benchmarking

## Running the Notebooks

### Option 1: Google Colab (No Setup Required)

Click the badges to open in Colab:

- [![Open 01 in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/yotambraun/Toolscore/blob/main/examples/notebooks/01_quickstart.ipynb)
- [![Open 02 in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/yotambraun/Toolscore/blob/main/examples/notebooks/02_custom_formats.ipynb)
- [![Open 03 in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/yotambraun/Toolscore/blob/main/examples/notebooks/03_advanced_metrics.ipynb)

### Option 2: Local Jupyter

```bash
# Install Jupyter
pip install jupyter

# Install Toolscore
pip install tool-scorer

# Start Jupyter
jupyter notebook

# Navigate to examples/notebooks/ and open a notebook
```

### Option 3: VS Code

1. Install VS Code with Python extension
2. Install `ipykernel`: `pip install ipykernel`
3. Open a `.ipynb` file
4. Select Python kernel

## Requirements

All notebooks require:
- Python 3.10+
- toolscore package (`pip install tool-scorer`)

No additional dependencies needed!

## Example Data

Notebooks use the example files in `examples/`:
- `gold_calls.json` - Gold standard specification
- `trace_openai.json` - OpenAI format trace
- `trace_anthropic.json` - Anthropic format trace
- `trace_custom.json` - Custom format trace

## Learning Path

**Recommended order**:
1. Start with `01_quickstart.ipynb` (5 minutes)
2. Try `02_custom_formats.ipynb` if you have custom traces (15 minutes)
3. Study `03_advanced_metrics.ipynb` for optimization (20 minutes)

## Support

- **Documentation**: https://toolscore.readthedocs.io/
- **Issues**: https://github.com/yotambraun/Toolscore/issues
- **Examples**: https://github.com/yotambraun/Toolscore/tree/main/examples

## Contributing

Have a great notebook idea? Please contribute!

1. Create your notebook
2. Test it thoroughly
3. Add it to this README
4. Submit a pull request

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines.
