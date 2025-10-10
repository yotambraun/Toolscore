"""HTML report generation."""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Template

if TYPE_CHECKING:
    from toolscore.core import EvaluationResult


# HTML template
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Toolscore Evaluation Report</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            margin-bottom: 10px;
        }
        .timestamp {
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 30px;
        }
        .summary {
            background: #ecf0f1;
            padding: 20px;
            border-radius: 4px;
            margin-bottom: 30px;
        }
        .summary h2 {
            color: #2c3e50;
            margin-bottom: 15px;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        .summary-item {
            background: white;
            padding: 15px;
            border-radius: 4px;
        }
        .summary-item strong {
            display: block;
            color: #7f8c8d;
            font-size: 12px;
            text-transform: uppercase;
            margin-bottom: 5px;
        }
        .summary-item .value {
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
        }
        .metric-section {
            margin-bottom: 30px;
        }
        .metric-section h2 {
            color: #2c3e50;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #3498db;
        }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }
        .metric-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 4px;
            border-left: 4px solid #3498db;
        }
        .metric-card h3 {
            color: #2c3e50;
            font-size: 14px;
            margin-bottom: 10px;
        }
        .metric-value {
            font-size: 32px;
            font-weight: bold;
            color: #3498db;
        }
        .metric-value.good {
            color: #27ae60;
        }
        .metric-value.warning {
            color: #f39c12;
        }
        .metric-value.bad {
            color: #e74c3c;
        }
        .calls-section {
            margin-top: 40px;
        }
        .calls-section h2 {
            color: #2c3e50;
            margin-bottom: 15px;
        }
        .call-item {
            background: #f8f9fa;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 4px;
            border-left: 4px solid #95a5a6;
        }
        .call-item.match {
            border-left-color: #27ae60;
        }
        .call-item.mismatch {
            border-left-color: #e74c3c;
        }
        .call-item .tool-name {
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 5px;
        }
        .call-item .args {
            font-family: 'Courier New', monospace;
            font-size: 13px;
            color: #555;
            background: white;
            padding: 10px;
            border-radius: 3px;
            overflow-x: auto;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Toolscore Evaluation Report</h1>
        <div class="timestamp">Generated: {{ timestamp }}</div>

        <div class="summary">
            <h2>Summary</h2>
            <div class="summary-grid">
                <div class="summary-item">
                    <strong>Expected Calls</strong>
                    <div class="value">{{ gold_count }}</div>
                </div>
                <div class="summary-item">
                    <strong>Actual Calls</strong>
                    <div class="value">{{ trace_count }}</div>
                </div>
            </div>
        </div>

        <div class="metric-section">
            <h2>Core Metrics</h2>
            <div class="metric-grid">
                <div class="metric-card">
                    <h3>Invocation Accuracy</h3>
                    <div class="metric-value {{ 'good' if invocation_accuracy >= 0.8 else ('warning' if invocation_accuracy >= 0.5 else 'bad') }}">
                        {{ "%.1f"|format(invocation_accuracy * 100) }}%
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Selection Accuracy</h3>
                    <div class="metric-value {{ 'good' if selection_accuracy >= 0.8 else ('warning' if selection_accuracy >= 0.5 else 'bad') }}">
                        {{ "%.1f"|format(selection_accuracy * 100) }}%
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Sequence Accuracy</h3>
                    <div class="metric-value {{ 'good' if sequence_accuracy >= 0.8 else ('warning' if sequence_accuracy >= 0.5 else 'bad') }}">
                        {{ "%.1f"|format(sequence_accuracy * 100) }}%
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Argument F1 Score</h3>
                    <div class="metric-value {{ 'good' if argument_f1 >= 0.8 else ('warning' if argument_f1 >= 0.5 else 'bad') }}">
                        {{ "%.1f"|format(argument_f1 * 100) }}%
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Redundant Call Rate</h3>
                    <div class="metric-value {{ 'good' if redundant_rate <= 0.2 else ('warning' if redundant_rate <= 0.5 else 'bad') }}">
                        {{ "%.1f"|format(redundant_rate * 100) }}%
                    </div>
                </div>
                {% if side_effect_rate is not none %}
                <div class="metric-card">
                    <h3>Side-Effect Success</h3>
                    <div class="metric-value {{ 'good' if side_effect_rate >= 0.8 else ('warning' if side_effect_rate >= 0.5 else 'bad') }}">
                        {{ "%.1f"|format(side_effect_rate * 100) }}%
                    </div>
                </div>
                {% endif %}
            </div>
        </div>

        {% if total_duration > 0 or total_cost > 0 %}
        <div class="metric-section">
            <h2>Performance Metrics</h2>
            <div class="metric-grid">
                {% if total_duration > 0 %}
                <div class="metric-card">
                    <h3>Total Duration</h3>
                    <div class="metric-value">{{ "%.2f"|format(total_duration) }}s</div>
                </div>
                <div class="metric-card">
                    <h3>Average Duration</h3>
                    <div class="metric-value">{{ "%.2f"|format(avg_duration) }}s</div>
                </div>
                {% endif %}
                {% if total_cost > 0 %}
                <div class="metric-card">
                    <h3>Total Cost</h3>
                    <div class="metric-value">${{ "%.4f"|format(total_cost) }}</div>
                </div>
                {% endif %}
            </div>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""


def generate_html_report(
    result: "EvaluationResult",
    output_path: str | Path = "toolscore.html",
) -> Path:
    """Generate HTML report from evaluation result.

    Args:
        result: Evaluation result to report.
        output_path: Path to save the HTML report.

    Returns:
        Path to the generated report file.
    """
    path = Path(output_path)

    # Extract metrics
    metrics = result.metrics
    seq_metrics = metrics.get("sequence_metrics", {})
    arg_metrics = metrics.get("argument_metrics", {})
    eff_metrics = metrics.get("efficiency_metrics", {})
    se_metrics = metrics.get("side_effect_metrics", {})
    lat_metrics = metrics.get("latency_metrics", {})
    cost_metrics = metrics.get("cost_metrics", {})

    # Prepare template data
    template_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "gold_count": len(result.gold_calls),
        "trace_count": len(result.trace_calls),
        "invocation_accuracy": metrics.get("invocation_accuracy", 0.0),
        "selection_accuracy": metrics.get("selection_accuracy", 0.0),
        "sequence_accuracy": seq_metrics.get("sequence_accuracy", 0.0),
        "argument_f1": arg_metrics.get("f1", 0.0),
        "redundant_rate": eff_metrics.get("redundant_rate", 0.0),
        "side_effect_rate": se_metrics.get("success_rate") if se_metrics else None,
        "total_duration": lat_metrics.get("total_duration", 0.0),
        "avg_duration": lat_metrics.get("average_duration", 0.0),
        "total_cost": cost_metrics.get("total_cost", 0.0),
    }

    # Render template
    template = Template(HTML_TEMPLATE)
    html_content = template.render(**template_data)

    # Write to file
    with path.open("w") as f:
        f.write(html_content)

    return path
