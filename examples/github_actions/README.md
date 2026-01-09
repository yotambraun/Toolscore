# GitHub Actions Examples for Toolscore

This directory contains example GitHub Actions workflows for integrating Toolscore
into your CI/CD pipeline.

## Available Workflows

### 1. `toolscore-evaluation.yml` - Basic Evaluation
Simple workflow that runs Toolscore evaluation on every push/PR.
- Evaluates agent trace against gold standard
- Fails if accuracy drops below threshold
- Generates HTML report artifact

### 2. `toolscore-regression.yml` - Regression Testing
Advanced workflow that detects performance regressions over time.
- Compares current trace against saved baseline
- Fails only if regression exceeds threshold
- Great for catching slow degradation

### 3. `toolscore-quality-gates.yml` - Full Quality Gates
Complete workflow with multiple quality checks.
- Threshold checks + regression detection
- Multi-model comparison
- Detailed job summary

## Quick Start

1. Copy the workflow you need to `.github/workflows/` in your repository

2. Create your gold standard file (e.g., `tests/gold_standard.json`)

3. Add a step to capture your agent's trace after running

4. The workflow will automatically evaluate and report results

## Usage in Your Repository

```yaml
# .github/workflows/agent-quality.yml
name: Agent Quality Check

on:
  push:
    branches: [main]
  pull_request:

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Your agent execution step here
      - name: Run Agent
        run: python run_agent.py --output trace.json

      # Toolscore evaluation
      - uses: yotambraun/toolscore@v1
        with:
          gold-file: tests/gold_standard.json
          trace-file: trace.json
          threshold: '0.90'
```

## Environment Variables

- `OPENAI_API_KEY` - Required for LLM judge feature (optional)

## Outputs

The action provides these outputs for use in later steps:
- `selection-accuracy` - Tool selection accuracy (0.0-1.0)
- `invocation-accuracy` - Tool invocation accuracy (0.0-1.0)
- `argument-f1` - Argument match F1 score (0.0-1.0)
- `passed` - Whether all thresholds were met (true/false)
- `regression-detected` - Whether regression was detected (true/false)

## Tips

1. **Start with a high threshold** (0.95) for critical paths
2. **Use regression testing** for long-running projects
3. **Generate baseline** after major improvements
4. **Review HTML reports** for detailed debugging
