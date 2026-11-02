CI/CD
=====

``toolscore init`` writes a GitHub Actions workflow that replays your approved snapshots on every push. Or use the official action directly:

.. code-block:: yaml

   # Gold-standard evaluation with a threshold
   - uses: yotambraun/toolscore@v1
     with:
       gold-file: tests/gold_standard.json
       trace-file: tests/agent_trace.json
       threshold: '0.90'

   # Safety gate — fail on forbidden calls or credentials in tool arguments
   - uses: yotambraun/toolscore@v1
     with:
       gold-file: tests/gold_standard.json
       trace-file: tests/agent_trace.json
       forbidden-file: tests/forbidden.json
       fail-on-violations: 'true'

   # MCP scorecard mode — grade your MCP server on every PR
   - uses: yotambraun/toolscore@v1
     with:
       mcp-command: 'uvx my-mcp-server'      # or a URL; add mcp-auth-env for a token
       mcp-fail-under: 'B'
       mcp-probes: 'true'                    # effect probes; mcp-allow-writes for round trips
       mcp-pin-file: 'toolscore.lock.json'   # fail on drift from `toolscore mcp pin`
       mcp-diff-against: 'baseline.json'     # diff against a saved `mcp list --json` snapshot

Add ``fail-on-honesty: 'true'`` to an eval step to fail when the agent claims success after a failure, overrides a refusal with a code-execution tool, or hides an injected fault.

The action installs the Toolscore version that matches the action ref (``@v1`` follows the latest 1.x release; pin ``@v1.11.0`` for a fixed version). It outputs ``score``, ``grade``, ``required-call-recall``, ``violations`` and ``honesty-errors``, and in MCP mode ``mcp-grade``, ``mcp-score`` and ``mcp-diff-breaking``, for later steps.

Baseline regression checks catch slow degradation:

.. code-block:: bash

   toolscore eval gold.json trace.json --save-baseline baseline.json   # once
   toolscore regression baseline.json new_trace.json --gold-file gold.json
   # exit codes: 0 = PASS, 1 = regression detected, 2 = error


Show the grade in your README
-----------------------------

``--badge PATH`` writes an SVG badge and ``--badge-json PATH`` a `shields.io endpoint <https://shields.io/badges/endpoint-badge>`__ file, both from that run's grade; there is no option to set a grade by hand. The bundled sample server's badge:

.. image:: ../assets/sample-mcp-grade.svg
   :alt: MCP grade badge

.. code-block:: bash

   toolscore mcp test "python my_server.py" --badge .github/badges/mcp-grade.svg

.. code-block:: markdown

   [![MCP grade](.github/badges/mcp-grade.svg)](https://github.com/yotambraun/toolscore)

To keep it current, let CI regenerate and commit it (`full workflow <https://github.com/yotambraun/toolscore/tree/main/examples/github_actions/mcp-badge.yml>`__):

.. code-block:: yaml

   - uses: yotambraun/toolscore@v1
     with:
       mcp-command: 'python my_server.py'
       mcp-fail-under: 'F'          # update the badge whatever the grade
       mcp-badge: .github/badges/mcp-grade.svg
   - run: |
       git config user.name "github-actions[bot]"
       git config user.email "github-actions[bot]@users.noreply.github.com"
       git add .github/badges/mcp-grade.svg
       git diff --cached --quiet || { git commit -m "chore: update MCP grade badge"; git push; }

