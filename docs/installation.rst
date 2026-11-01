Installation
============

Requirements
------------

* Python 3.10 or later
* pip or uv package manager

From PyPI
---------

The simplest way to install Toolscore is from PyPI:

.. code-block:: bash

   pip install tool-scorer

Or using uv (faster):

.. code-block:: bash

   uv pip install tool-scorer

From Source
-----------

To install the latest development version:

.. code-block:: bash

   git clone https://github.com/yotambraun/Toolscore.git
   cd Toolscore
   pip install -e .

Development Installation
------------------------

To install with development dependencies:

.. code-block:: bash

   pip install -e ".[dev]"

This includes:

* pytest - Testing framework
* pytest-cov - Coverage reporting
* mypy - Type checking
* ruff - Linting and formatting
* types-click - Type stubs for Click
* httpx - Runs the Streamable HTTP transport tests

Optional Dependencies
---------------------

Remote MCP Servers and HTTP Validators
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To test MCP servers over Streamable HTTP (``toolscore mcp test https://...``)
and for HTTP side-effect validation (adds ``httpx``):

.. code-block:: bash

   pip install "tool-scorer[http]"

Testing stdio MCP servers needs no extra.

LLM-as-a-judge Metrics
^^^^^^^^^^^^^^^^^^^^^^

For semantic correctness evaluation using OpenAI API (default model ``gpt-6-luna``;
``[anthropic]`` and ``[gemini]`` extras cover the other providers):

.. code-block:: bash

   pip install tool-scorer[llm]

Requires ``OPENAI_API_KEY`` environment variable.

LangChain Support
^^^^^^^^^^^^^^^^^

For LangChain agent trace parsing:

.. code-block:: bash

   pip install tool-scorer[langchain]

All Optional Features
^^^^^^^^^^^^^^^^^^^^^

To install all optional dependencies at once:

.. code-block:: bash

   pip install tool-scorer[all]

Documentation
^^^^^^^^^^^^^

To build documentation locally:

.. code-block:: bash

   pip install tool-scorer[docs]

Verification
------------

Verify your installation:

.. code-block:: bash

   tool-scorer --version

Run the test suite:

.. code-block:: bash

   pytest tests/

Next Steps
----------

* Check out the :doc:`quickstart` guide
* Read the :doc:`user_guide` for detailed usage
* Explore the :doc:`api/index` reference
