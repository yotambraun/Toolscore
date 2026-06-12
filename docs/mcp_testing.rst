Testing MCP Servers
===================

Test your MCP server in 60 seconds
----------------------------------

Toolscore ships a one-command test/lint/scorecard harness for any `Model
Context Protocol <https://modelcontextprotocol.io/>`_ server that speaks the
stdio transport. No code, no fixtures -- point it at a server and get a grade.

.. code-block:: bash

   uvx tool-scorer mcp test --config claude_desktop_config.json --server filesystem

That spins up the server, reads its advertised tools, generates happy-path and
edge-case calls from each tool's JSON schema, runs them, lints the schemas, and
prints an A--F **scorecard**.

You can also pass the launch command directly as a single quoted string instead
of a config file:

.. code-block:: bash

   uvx tool-scorer mcp test "python my_server.py"
   uvx tool-scorer mcp test "npx -y @modelcontextprotocol/server-filesystem /tmp"

The three subcommands
---------------------

``toolscore mcp list``
   Print a table of the tools the server advertises (name, parameter count,
   description). A quick sanity check that the server starts and handshakes.

``toolscore mcp lint``
   Statically lint the tool schemas for quality problems and exit non-zero if
   any **error**-severity issue is found -- handy as a fast CI gate.

``toolscore mcp test``
   Run the full scorecard: scenario generation, execution, linting, and an
   A--F grade. Supports machine-readable reports and a ``--fail-under`` gate.

Every command accepts **either** a quoted launch command **or**
``--config PATH [--server NAME]`` (a `Claude Desktop
<https://modelcontextprotocol.io/quickstart/user>`_ style config file). Supplying
both, or neither, is an error.

What the grade means
--------------------

The scorecard blends three signals into a single score in ``[0, 1]``:

.. code-block:: text

   score = 0.6 * happy_pass_rate
         + 0.2 * edge_resilience_rate
         + 0.2 * lint_score

* **happy_pass_rate** -- the fraction of well-formed (happy-path) calls that
  succeeded. This is the core "does the tool do what it advertises?" signal, so
  it carries the most weight.
* **edge_resilience_rate** -- the fraction of intentionally *bad* inputs
  (missing required arguments, wrong types, empty/zero values) that the server
  handled **without crashing or timing out**. A returned error is fine and
  expected here -- crashing the process is not.
* **lint_score** -- schema cleanliness, computed as
  ``max(0, 1 - (errors * 0.25 + warnings * 0.1) / num_tools)``.

The score maps to a letter grade:

========  ============
Grade     Score
========  ============
``A``     ``>= 0.90``
``B``     ``>= 0.80``
``C``     ``>= 0.70``
``D``     ``>= 0.60``
``F``     ``< 0.60``
========  ============

Servers with no scenarios (for example a tool whose schema can't be
introspected) never divide by zero -- the corresponding term defaults to full
credit.

Tuning the run
--------------

.. code-block:: bash

   toolscore mcp test "python my_server.py" \
     --cases 5 \          # happy-path scenarios per tool (default: 3)
     --no-edge-cases \    # skip the bad-input scenarios
     --timeout 10         # per-call timeout in seconds (default: 30)

Using it in CI
--------------

Gate a pull request on a minimum grade with ``--fail-under`` (a letter grade,
case-insensitive). The command exits ``1`` when the achieved grade is below the
threshold:

.. code-block:: yaml

   # .github/workflows/mcp.yml
   name: MCP Scorecard
   on: [push, pull_request]

   jobs:
     scorecard:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: astral-sh/setup-uv@v5
         - name: Score the MCP server
           run: |
             uvx tool-scorer mcp test "python my_server.py" \
               --fail-under B \
               --report md --output scorecard.md

You can also gate purely on the linter:

.. code-block:: bash

   toolscore mcp lint "python my_server.py"   # exit 1 on any schema error

Embedding the scorecard
-----------------------

``--report md`` writes a Markdown scorecard that drops straight into a README or
a PR comment, and ``--report json`` writes a machine-readable report for further
processing. Both still print a one-line summary to the console.

.. code-block:: bash

   toolscore mcp test "python my_server.py" --report md --output scorecard.md

A typical Markdown report looks like:

.. code-block:: markdown

   # MCP Scorecard: my-server 1.0.0

   **Grade: B** &middot; Score 84%

   - Happy-path pass rate: 100%
   - Edge-case resilience: 80%
   - Lint score: 70% (1 errors, 1 warnings)

   ## Tools

   | Tool | Scenarios | Avg latency |
   | --- | --- | --- |
   | `search` | 4/4 | 12.3 ms |
   | `fetch` | 3/4 | 8.1 ms |

   ## Lint

   - **error** &middot; `fetch`: property 'url' is missing a 'type'
   - warning &middot; `search`: properties defined but no 'required' list declared

Python API
----------

The same building blocks are available programmatically under
:mod:`toolscore.mcp`:

.. code-block:: python

   from toolscore.mcp import (
       MCPScorecard,
       MCPStdioClient,
       generate_scenarios,
       lint_tools,
       run_scenarios,
       scorecard_to_markdown,
   )

   with MCPStdioClient(["python", "my_server.py"]) as client:
       tools = client.list_tools()
       scenarios = generate_scenarios(tools, cases_per_tool=3)
       results = run_scenarios(client, scenarios)

   card = MCPScorecard(
       server_info=client.server_info,
       tools=tools,
       results=results,
       lint=lint_tools(tools),
   )
   print(card.grade, f"{card.score:.0%}")
   print(scorecard_to_markdown(card))
