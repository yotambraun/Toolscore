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

Optional Dependencies
---------------------

HTTP Validators
^^^^^^^^^^^^^^^

For HTTP side-effect validation:

.. code-block:: bash

   pip install tool-scorer[http]

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
