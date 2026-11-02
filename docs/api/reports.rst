Reports Module
==============

.. currentmodule:: toolscore.reports

The reports module generates evaluation reports in various formats.

JSON Reports
------------

.. autofunction:: generate_json_report

HTML Reports
------------

.. autofunction:: generate_html_report

Markdown and CSV Reports
------------------------

.. autofunction:: generate_markdown_report

.. autofunction:: generate_csv_report

Behavior and Safety Findings
----------------------------

.. autofunction:: toolscore.reports.findings.behavior_findings

SARIF and JUnit
---------------

.. automodule:: toolscore.reports.ci
   :members: Outcome, to_sarif, to_junit, write_ci_reports, default_location,
      outcomes_from_scorecard, outcomes_from_lint, outcomes_from_pin, outcomes_from_diff,
      outcomes_from_config_lint, outcomes_from_honesty, outcomes_from_evaluation
