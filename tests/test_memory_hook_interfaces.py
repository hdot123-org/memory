"""Tests for workspace/tools/memory_hook_interfaces.py interface definitions.

Covers:
- TypedDict structure & field completeness
- ABC instantiation prevention
- Abstract method existence via __abstractmethods__
"""

import sys
from pathlib import Path

import pytest

# Ensure workspace/tools is on the path so the module can be imported
TOOLS_DIR = str(Path(__file__).resolve().parent.parent / "memory_core" / "tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from memory_hook_interfaces import (
    ArtifactSink,
    ErrorSink,
    GatewayBusinessPolicy,
    HostDelegate,
    PathUtils,
    PolicyRegistry,
    RegistrationCommitGate,
    RouteTargetPolicy,
    TruthBasis,
    WriteTargetPolicy,
)

# ---------------------------------------------------------------------------
# 1. TypedDict structure validation
# ---------------------------------------------------------------------------

class TestTruthBasisTypedDict:
    """TruthBasis all-optional fields can be set correctly."""

    def test_all_fields_can_be_set(self):
        instance: TruthBasis = {
            "refs": ["ref-1"],
            "errors": ["err-1"],
            "validation": "passed",
            "policy": "strict",
            "project_ref": "proj-1",
            "source_refs": ["src-1"],
            "authority_refs": ["auth-1"],
            "evidence_refs": ["ev-1"],
            "global_refs": ["global-1"],
            "conflict_status": ["open"],
        }
        assert instance["refs"] == ["ref-1"]
        assert instance["global_refs"] == ["global-1"]
        assert instance["conflict_status"] == ["open"]

    def test_global_refs_field_exists(self):
        """global_refs is part of the TypedDict contract."""
        assert "global_refs" in TruthBasis.__annotations__

    def test_empty_instance_is_valid(self):
        """total=False means an empty dict satisfies the contract."""
        empty: TruthBasis = {}
        assert empty == {}

    def test_partial_instance_is_valid(self):
        partial: TruthBasis = {"refs": ["a"], "global_refs": ["b"]}
        assert partial["refs"] == ["a"]
        assert partial["global_refs"] == ["b"]


class TestRegistrationCommitGateTypedDict:
    """RegistrationCommitGate field completeness."""

    def test_all_fields_can_be_set(self):
        instance: RegistrationCommitGate = {
            "phase": "pre-commit",
            "enforced": True,
            "gate_event": "push",
            "triggered_on_current_event": False,
            "enforcement_result": "blocked",
            "status": "active",
        }
        assert instance["phase"] == "pre-commit"
        assert instance["enforced"] is True

    def test_empty_instance_is_valid(self):
        empty: RegistrationCommitGate = {}
        assert empty == {}


# ---------------------------------------------------------------------------
# 2. TypedDict __annotations__ field completeness
# ---------------------------------------------------------------------------

class TestTypedDictAnnotations:
    """Each TypedDict's __annotations__ contains the expected fields."""

    def test_truth_basis_annotations(self):
        expected = {
            "refs", "errors", "validation", "policy", "project_ref",
            "source_refs", "authority_refs", "evidence_refs",
            "global_refs", "conflict_status",
        }
        assert set(TruthBasis.__annotations__.keys()) == expected

    def test_registration_commit_gate_annotations(self):
        expected = {
            "phase", "enforced", "gate_event",
            "triggered_on_current_event", "enforcement_result", "status",
        }
        assert set(RegistrationCommitGate.__annotations__.keys()) == expected


# ---------------------------------------------------------------------------
# 3. ABC cannot be instantiated directly
# ---------------------------------------------------------------------------

class TestABCInstantiation:
    """Each ABC raises TypeError when instantiated directly."""

    @pytest.mark.parametrize("cls", [
        HostDelegate,
        PolicyRegistry,
        RouteTargetPolicy,
        WriteTargetPolicy,
        GatewayBusinessPolicy,
        ArtifactSink,
        ErrorSink,
        PathUtils,
    ])
    def test_cannot_instantiate_abc(self, cls):
        with pytest.raises(TypeError):
            cls()


# ---------------------------------------------------------------------------
# 4. Abstract method existence checks via __abstractmethods__
# ---------------------------------------------------------------------------

class TestAbstractMethods:
    """Each ABC declares the correct set of abstract methods."""

    def test_host_delegate_abstract_methods(self):
        assert HostDelegate.__abstractmethods__ == frozenset({
            "can_handle", "execute", "noop_response",
        })

    def test_policy_registry_abstract_methods(self):
        assert PolicyRegistry.__abstractmethods__ == frozenset({
            "get_policy", "validate", "get_policy_pack", "resolve_conflict",
            "validate_project_map", "validate_unique_legal_system_contract",
            "governance_frozen_tuple_errors", "event_contract_blocker_errors",
            "git_registration_probe", "truth_basis_for_scope",
            "decision_refs_for_scope", "lesson_refs_for_scope",
            "docs_refs_for_scope",
        })

    def test_route_target_policy_abstract_methods(self):
        assert RouteTargetPolicy.__abstractmethods__ == frozenset({"resolve"})

    def test_write_target_policy_abstract_methods(self):
        assert WriteTargetPolicy.__abstractmethods__ == frozenset({"get_targets"})

    def test_gateway_business_policy_abstract_methods(self):
        # get_required_gateway_inputs has a default impl, so it is NOT abstract
        assert GatewayBusinessPolicy.__abstractmethods__ == frozenset({
            "determine_project_scope", "get_project_canonical",
            "get_project_runtime_root", "get_required_canonical",
            "get_global_canonical", "project_map_refs",
            "validate_project_map_files", "validate_unique_legal_system_contract",
            "governance_frozen_tuple_blocker_errors", "event_contract_blocker_errors",
            "decision_refs_for_scope", "lesson_refs_for_scope",
            "docs_refs_for_scope", "truth_basis_for_scope",
        })

    def test_artifact_sink_abstract_methods(self):
        assert ArtifactSink.__abstractmethods__ == frozenset({
            "write", "ensure_dirs",
        })

    def test_error_sink_abstract_methods(self):
        assert ErrorSink.__abstractmethods__ == frozenset({"log"})

    def test_path_utils_abstract_methods(self):
        assert PathUtils.__abstractmethods__ == frozenset({
            "extract_excerpt", "write_targets",
        })
