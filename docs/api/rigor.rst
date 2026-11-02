Contracts, Receipts, Evidence, Statistics and Export
====================================================

Contracts
---------

See :doc:`../contracts`.

.. currentmodule:: toolscore.contract

.. autofunction:: evaluate_contract

.. autofunction:: load_contract

.. autofunction:: contract_from_mapping

.. autofunction:: is_contract

.. autofunction:: matcher_from_json

.. autofunction:: split_optional

.. autoclass:: Contract
   :members:

.. autoclass:: AlternativeGroup

Receipts and regrade
--------------------

See :doc:`../receipts`.

.. currentmodule:: toolscore.receipts

.. autofunction:: build_receipt

.. autofunction:: write_receipt

.. autofunction:: load_receipt

.. autofunction:: verify_receipt

.. autofunction:: regrade

.. autoclass:: Regrade
   :members:

.. autoexception:: ReceiptMismatchError

.. autofunction:: canonical_json

.. autofunction:: json_sha256

.. autofunction:: file_digest

Evidence
--------

.. automodule:: toolscore.evidence
   :members: evaluation_evidence, tally, summary_line, tri_state, Check

Statistics and selection
------------------------

See :doc:`../comparing_runs`.

.. currentmodule:: toolscore.stats

.. autofunction:: wilson_interval

.. autofunction:: fisher_exact

.. autofunction:: pass_hat_k

.. autofunction:: compare_runs

.. autofunction:: load_runs

.. autofunction:: runs_from_traces

.. autofunction:: run_from_row

.. autofunction:: select_variant

.. autofunction:: pareto_front

.. autofunction:: evaluate_protocol

.. autofunction:: load_protocol

.. autoclass:: Run

.. autoclass:: VariantStats
   :members: metric

.. autoclass:: Comparison
   :members: to_dict

.. autoclass:: PairComparison

.. autoclass:: Selection

.. autoclass:: ProtocolResult

Export
------

.. currentmodule:: toolscore.export

.. autofunction:: export_records

.. autofunction:: write_export

.. autofunction:: validate_record

.. autofunction:: record_from_run

.. autodata:: SCHEMA_VERSION

Doctor
------

.. currentmodule:: toolscore.doctor

.. autofunction:: run_doctor

.. autofunction:: check_server

.. autofunction:: doctor_report

.. autoclass:: DoctorCheck
