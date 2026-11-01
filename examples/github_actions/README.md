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

### 4. `mcp-badge.yml` - MCP Grade Badge
Grades your MCP server on every push to main and commits an SVG badge
("MCP grade: A · Toolscore") when the grade changes.
- The badge comes from that run's scorecard; there is no way to set a grade by hand
- Works with a launch command or a Streamable HTTP URL

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
      - uses: actions/checkout@v7

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

## MCP server scorecard in CI

Building an MCP server? Gate its quality with the scorecard. `--ci` writes the verdict to the GitHub Actions job summary and fails the build on blocking issues (a tool that fails on valid input, an edge-case crash, or a schema error):

```yaml
# .github/workflows/mcp-scorecard.yml
name: MCP Scorecard
on: [push, pull_request]

jobs:
  scorecard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10.3.0
      - name: Score the MCP server
        run: uvx tool-scorer mcp test "python my_server.py" --ci --fail-under B
```

Or with the action, which also takes a URL. For a server behind a token, store the
token as a secret and name its environment variable in `mcp-auth-env`; Toolscore
sends it as `Authorization: Bearer <token>` and never prints it:

```yaml
      - uses: yotambraun/toolscore@v1
        env:
          MCP_TOKEN: ${{ secrets.MCP_TOKEN }}
        with:
          mcp-command: 'https://mcp.example.com/mcp'
          mcp-auth-env: MCP_TOKEN
          mcp-fail-under: 'B'
          mcp-badge: .github/badges/mcp-grade.svg   # optional; see mcp-badge.yml
```

The action installs the Toolscore version that matches the action ref: `@v1` follows
the latest 1.x release, `@v1.11.0` stays on 1.11.0. Set `toolscore-version` to install
a specific PyPI release instead.

## Environment Variables

- `OPENAI_API_KEY` - Required for LLM judge feature (optional)
- The variable named in `mcp-auth-env` - a bearer token for a remote MCP server (optional)

## Outputs

The action provides these outputs for use in later steps:
- `selection-accuracy` - Tool selection accuracy (0.0-1.0)
- `invocation-accuracy` - Tool invocation accuracy (0.0-1.0)
- `argument-f1` - Argument match F1 score (0.0-1.0)
- `passed` - Whether all thresholds were met (true/false)
- `regression-detected` - Whether regression was detected (true/false)
- `score`, `grade` - Composite score (0.0-1.0) and letter grade
- `required-call-recall` - Share of required calls made without failing
- `violations` - Forbidden calls plus credentials found in tool arguments
- `mcp-grade`, `mcp-score` - MCP scorecard grade and score (MCP mode only)

## Tips

1. **Start with a high threshold** (0.95) for critical paths
2. **Use regression testing** for long-running projects
3. **Generate baseline** after major improvements
4. **Review HTML reports** for detailed debugging
