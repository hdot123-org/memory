"""Tests for validate_memory_system module."""


from memory_core.tools.validate_memory_system import (
    REQUIRED_PACKAGE_KEYS,
    REQUIRED_SYSTEM_CONTEXT_KEYS,
    REQUIRED_TASK_CONTEXT_KEYS,
    ValidateResult,
    _empty_truth_basis,
    check_core_builder_resolve,
    check_gateway_import,
)


class TestConstants:
    def test_required_package_keys(self):
        assert "status" in REQUIRED_PACKAGE_KEYS
        assert "host" in REQUIRED_PACKAGE_KEYS
        assert "event" in REQUIRED_PACKAGE_KEYS

    def test_required_system_context_keys(self):
        assert "boot_entry" in REQUIRED_SYSTEM_CONTEXT_KEYS
        assert "state_entry" in REQUIRED_SYSTEM_CONTEXT_KEYS

    def test_required_task_context_keys(self):
        assert "session_id" in REQUIRED_TASK_CONTEXT_KEYS
        assert "event" in REQUIRED_TASK_CONTEXT_KEYS


class TestEmptyTruthBasis:
    def test_returns_dict_with_required_keys(self):
        basis = _empty_truth_basis()
        assert "refs" in basis
        assert "errors" in basis
        assert "validation" in basis
        assert "policy" in basis

    def test_validation_pass(self):
        basis = _empty_truth_basis()
        assert basis["validation"] == "pass"

    def test_errors_empty(self):
        basis = _empty_truth_basis()
        assert basis["errors"] == []

    def test_conflict_status_resolved(self):
        basis = _empty_truth_basis()
        assert "resolved" in basis["conflict_status"]


class TestValidateResult:
    def test_init_empty(self):
        result = ValidateResult()
        assert result.checks == []

    def test_add_check(self):
        result = ValidateResult()
        result.checks.append(("test", True, ""))
        assert len(result.checks) == 1

    def test_all_passed_no_checks(self):
        result = ValidateResult()
        assert result.checks == []

    def test_all_passed_with_pass(self):
        result = ValidateResult()
        result.checks.append(("test1", True, ""))
        result.checks.append(("test2", True, ""))
        assert all(ok for _, ok, _ in result.checks)

    def test_all_passed_with_fail(self):
        result = ValidateResult()
        result.checks.append(("test1", True, ""))
        result.checks.append(("test2", False, "error msg"))
        assert not all(ok for _, ok, _ in result.checks)


class TestCheckGatewayImport:
    def test_returns_true_when_importable(self):
        result = ValidateResult()
        ok = check_gateway_import(result)
        # The gateway should be importable in a valid repo
        assert isinstance(ok, bool)
        assert len(result.checks) >= 1


class TestCheckCoreBuilderResolve:
    def test_returns_tuple(self):
        result = ValidateResult()
        outcome = check_core_builder_resolve(result)
        assert isinstance(outcome, tuple)
        assert len(outcome) == 2
