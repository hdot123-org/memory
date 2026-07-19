"""Tests for truth-basis validation logic have been moved.

Cluster B refactoring removed module-level _classify_truth_ref, _authority_ref_allowed,
_lower_evidence_ref, _truth_basis_sections_for, _truth_basis_errors_for from gateway.py.
The authoritative implementation now lives in TruthBasisResolver (business_policy_checks.py).
Tests for these functions are in test_business_policy_paths.py, test_business_policy_schema.py,
and test_init_completeness.py.
"""
