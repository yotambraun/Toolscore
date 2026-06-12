Snapshots Module
================

.. currentmodule:: toolscore.snapshots

The storage and state-machine core behind :doc:`../snapshot_testing`. The pytest
``toolscore_snapshot`` fixture and the ``toolscore record/approve/snapshots``
CLI commands are built on this API.

.. autofunction:: snapshot_check

.. autoclass:: Snapshot
   :members:
   :undoc-members:

.. autoclass:: SnapshotStore
   :members:
   :undoc-members:
