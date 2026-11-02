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

Findings in code scanning and test reports
------------------------------------------

The commands that produce findings can also write them as **SARIF 2.1.0**
(``--sarif PATH``) and **JUnit XML** (``--junit PATH``): ``mcp test``,
``mcp lint``, ``mcp verify-pin``, ``mcp diff``, ``lint-config``, ``honesty`` and
``eval``. Both come from one model, in which every check is pass, fail or
unknown:

==============================  =================================  =============================
Check                           SARIF                              JUnit
==============================  =================================  =============================
failed, error severity          result, ``kind: fail``,            ``<failure>``
                                ``level: error``
warning / note                  result, ``level: warning`` /       passing test case,
                                ``note``                           ``<system-out>warning: ...``
unknown (no final answer, an    result, ``kind: open``,            ``<skipped>``, its message
inconclusive probe, a call      ``level: none`` (SARIF's "not      starting ``unknown:``
that needed client input)       enough information")
passed                          not written                        passing test case
==============================  =================================  =============================

JUnit has no warning state, so warnings never fail a JUnit report; the
command's exit code (``--fail-on``, ``--fail-under``, ``--ci``) still decides
whether the job fails. Every SARIF rule has a description, help text and a link
to its documentation.

**Locations.** Code scanning shows a result only when it points at a file in
the repository. Results of ``lint-config`` carry the file and line;
``verify-pin`` points at the lock file; ``honesty`` and ``eval`` at the trace.
Server results (``mcp test``, ``mcp lint``, ``mcp diff``) point at
``--report-location FILE``, else the ``--config`` file, else a file of the
repository named in the server command (``python server.py`` gives
``server.py``), else the ``--pin`` lock file. A remote server tested by URL
alone has no file: pass ``--report-location``.

GitHub code scanning
~~~~~~~~~~~~~~~~~~~~

Give the action ``sarif-file`` (and ``report-location`` if needed), then upload
the file with GitHub's own action. ``if: always()`` uploads it when the
Toolscore step failed too:

.. code-block:: yaml

   permissions:
     contents: read
     security-events: write   # needed by upload-sarif

   steps:
     - uses: actions/checkout@v7
     - uses: yotambraun/toolscore@v1
       with:
         mcp-command: 'python server.py'
         mcp-probes: 'true'
         sarif-file: toolscore.sarif
     - uses: github/codeql-action/upload-sarif@v4
       if: always()
       with:
         sarif_file: toolscore.sarif
         category: toolscore-mcp

Or run the CLI yourself (``toolscore mcp test "python server.py" --sarif
toolscore.sarif``). Each command writes its own SARIF category
(``toolscore/mcp-test``, ``toolscore/honesty``...); give each upload its own
``category`` when you upload several files. Code scanning is available on
public repositories and on private ones with GitHub Advanced Security.

GitLab and Jenkins (JUnit)
~~~~~~~~~~~~~~~~~~~~~~~~~~

GitLab reads JUnit reports from ``artifacts:reports:junit``; ``when: always``
keeps the report of a failing job:

.. code-block:: yaml

   toolscore:
     image: python:3.12
     script:
       - pip install tool-scorer
       - toolscore mcp test "python server.py" --ci --junit toolscore-junit.xml
       - toolscore honesty traces/run.json --junit toolscore-honesty.xml --fail-on-findings
     artifacts:
       when: always
       reports:
         junit:
           - toolscore-junit.xml
           - toolscore-honesty.xml

Jenkins, with the JUnit plugin:

.. code-block:: groovy

   stage('Toolscore') {
     steps {
       sh 'toolscore mcp lint "python server.py" --junit toolscore-lint.xml'
     }
     post {
       always { junit 'toolscore-lint.xml' }
     }
   }

The action has a ``junit-file`` input for the same file on GitHub.

pre-commit
----------

Toolscore ships three `pre-commit <https://pre-commit.com>`__ hooks. They run
locally, deterministically and with no API key; none calls a tool.

==========================  ================================================================
Hook                        What it checks
==========================  ================================================================
``toolscore-lint-config``   instruction files and MCP host configs against the tools the
                            servers expose (:doc:`config_lint`); runs when one of them, a
                            lock or a snapshot file changes
``toolscore-verify-pin``    a server against its lock file (:doc:`pinning_diff`); runs when
                            a ``*.lock.json`` or ``*.snapshot.json`` file changes
``toolscore-mcp-lint``      a local server's tool definitions (starts it, lists its tools)
==========================  ================================================================

.. code-block:: yaml

   # .pre-commit-config.yaml
   repos:
     - repo: https://github.com/yotambraun/toolscore
       rev: v1.11.0
       hooks:
         - id: toolscore-lint-config
           args: [--pin, notes=pins/notes.lock.json]
         # The server lives in this repository: a changed tool definition fails
         # the commit until it is re-pinned with `toolscore mcp pin`.
         - id: toolscore-verify-pin
           args: ["python server.py", --lock, pins/notes.lock.json]
           files: ^(server\.py|pins/)
         - id: toolscore-mcp-lint
           args: ["python server.py"]
           files: ^server\.py$

``toolscore-verify-pin`` also takes a committed snapshot instead of a launch
command (``args: [pins/notes.snapshot.json, --lock, pins/notes.lock.json]``), so
nothing is started. Without ``--pin`` or ``--snapshot``, ``lint-config`` skips
the rules that need tool lists (it says so) rather than passing them.

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

