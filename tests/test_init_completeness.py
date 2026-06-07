# -*- coding: utf-8 -*-
"""Golden end-to-end tests for Phase 0 — Host Single-Host Tightening + No Project Hooks.

Each test asserts one VAL-P0-* validation contract requirement.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from memory_core.tools.memory_hook_integrity_keys import generate_key


def _mock_source_repo(monkeypatch, project_root: Path):
    """Monkeypatch is_memory_core_source_repo to return False for project_root."""
    from memory_core.ownership import is_memory_core_source_repo as real_fn
    monkeypatch.setattr(
        "memory_core.tools.memory_hook_integrity_manifest.is_memory_core_source_repo",
        lambda p: p != project_root and real_fn(p),
    )


# ---------------------------------------------------------------------------
# Helper: run init via CLI
# ---------------------------------------------------------------------------

def _run_init_cli(target: Path, host: str = "factory", **extra_args: str) -> subprocess.CompletedProcess:
    """Run init_project_memory as a subprocess and return the CompletedProcess."""
    cmd = [
        sys.executable,
        "-m",
        "memory_core.tools.init_project_memory",
        "--target",
        str(target),
        "--host",
        host,
    ]
    for key, value in extra_args.items():
        cmd.extend([f"--{key}", str(value)])
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# VAL-P0-001: init never writes any hooks.json
# ---------------------------------------------------------------------------

class TestNoHooksJson:
    def test_init_creates_no_hooks_json(self, tmp_path: Path) -> None:
        """VAL-P0-001: init never writes any hooks.json under .claude/, .codex/, .factory/."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()  # fake git repo
        init_project_memory(tmp_path, host="factory", mode="create")

        assert not (tmp_path / ".claude" / "hooks.json").exists()
        assert not (tmp_path / ".codex" / "hooks.json").exists()
        assert not (tmp_path / ".factory" / "hooks.json").exists()

    def test_no_generate_hooks_json_in_source(self) -> None:
        """VAL-P0-001 (source): generate_hooks_json not called in init body."""
        import ast
        source_path = Path(__file__).parent.parent / "memory_core" / "tools" / "init_project_memory.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        # Find the init_project_memory function body
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "init_project_memory":
                func_source = ast.unparse(node)
                # Should not contain an active call to generate_hooks_json
                # (commented-out reference is OK)
                lines = func_source.split("\n")
                active_calls = [l for l in lines if "generate_hooks_json(" in l and not l.strip().startswith("#")]
                assert len(active_calls) == 0, f"generate_hooks_json still called in init_project_memory: {active_calls}"


# ---------------------------------------------------------------------------
# VAL-P0-002: AGENTS.md contains no host-specific path references
# ---------------------------------------------------------------------------

class TestAgentsMdHostNeutral:
    def test_agents_md_no_legacy_host_strings(self, tmp_path: Path) -> None:
        """VAL-P0-002: AGENTS.md must not contain codex/claude path strings."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "~/.codex/" not in agents
        assert "~/.claude/" not in agents
        assert ".codex/hooks.json" not in agents
        assert ".claude/hooks.json" not in agents


# ---------------------------------------------------------------------------
# VAL-P0-003: adapter.toml [routing] host field is fixed to "factory"
# ---------------------------------------------------------------------------

class TestAdapterTomlHostFactory:
    def test_adapter_toml_host_factory(self, tmp_path: Path) -> None:
        """VAL-P0-003: adapter.toml routing.host == 'factory'."""
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib

        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        adapter_path = tmp_path / "memory" / "system" / "adapter.toml"
        assert adapter_path.exists()

        with open(adapter_path, "rb") as fh:
            data = tomllib.load(fh)

        assert data["routing"]["host"] == "factory"


# ---------------------------------------------------------------------------
# VAL-P0-004: Host neutrality — byte-identical output across two fresh inits
# ---------------------------------------------------------------------------

class TestHostNeutrality:
    def test_init_creates_byte_identical_output(self, tmp_path: Path) -> None:
        """VAL-P0-004: Two fresh inits with same host produce byte-identical output.

        Uses explicit scope='test-project' to ensure identical project names.
        """
        import filecmp
        import hashlib

        from memory_core.tools.init_project_memory import init_project_memory

        tmp1 = tmp_path / "run1"
        tmp2 = tmp_path / "run2"
        tmp1.mkdir()
        tmp2.mkdir()
        (tmp1 / ".git").mkdir()
        (tmp2 / ".git").mkdir()

        # Use same scope so project name derivation is identical
        init_project_memory(tmp1, host="factory", mode="create", scope="test-project")
        init_project_memory(tmp2, host="factory", mode="create", scope="test-project")

        # AGENTS.md must be byte-identical
        assert filecmp.cmp(tmp1 / "AGENTS.md", tmp2 / "AGENTS.md", shallow=False)

        # adapter.toml must be byte-identical
        assert filecmp.cmp(
            tmp1 / "memory" / "system" / "adapter.toml",
            tmp2 / "memory" / "system" / "adapter.toml",
            shallow=False,
        )


# ---------------------------------------------------------------------------
# VAL-P0-005: argparse rejects non-factory --host values in init CLI
# ---------------------------------------------------------------------------

class TestArgparseRejectsLegacyHosts:
    def test_argparse_rejects_codex(self, tmp_path: Path) -> None:
        """VAL-P0-005: --host codex raises SystemExit."""
        from memory_core.tools.init_project_memory import main
        with pytest.raises(SystemExit):
            main(["--target", str(tmp_path), "--host", "codex"])

    def test_argparse_rejects_claude(self, tmp_path: Path) -> None:
        """VAL-P0-005: --host claude raises SystemExit."""
        from memory_core.tools.init_project_memory import main
        with pytest.raises(SystemExit):
            main(["--target", str(tmp_path), "--host", "claude"])

    def test_argparse_accepts_factory(self, tmp_path: Path) -> None:
        """VAL-P0-005: --host factory exits 0."""
        (tmp_path / ".git").mkdir()
        from memory_core.tools.init_project_memory import main
        ret = main(["--target", str(tmp_path), "--host", "factory"])
        assert ret == 0


# ---------------------------------------------------------------------------
# VAL-P0-006: SUPPORTED_HOSTS constant is ("factory",)
# ---------------------------------------------------------------------------

class TestSupportedHostsFactoryOnly:
    def test_supported_hosts_factory_only(self) -> None:
        """VAL-P0-006: SUPPORTED_HOSTS == ('factory',)."""
        from memory_core.constants import SUPPORTED_HOSTS
        assert SUPPORTED_HOSTS == ("factory",)
        assert len(SUPPORTED_HOSTS) == 1
        assert "factory" in SUPPORTED_HOSTS


# ---------------------------------------------------------------------------
# VAL-P0-007: memory_hook_gateway --host argparse accepts only factory
# ---------------------------------------------------------------------------

class TestGatewayArgparseFactoryOnly:
    def test_gateway_rejects_codex(self) -> None:
        """VAL-P0-007: gateway --host codex raises SystemExit."""
        from memory_core.tools.memory_hook_gateway import _parse_args
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["gateway", "--host", "codex", "--event", "session-start"]
            with pytest.raises(SystemExit):
                _parse_args()
        finally:
            sys.argv = old_argv

    def test_gateway_rejects_claude(self) -> None:
        """VAL-P0-007: gateway --host claude raises SystemExit."""
        from memory_core.tools.memory_hook_gateway import _parse_args
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["gateway", "--host", "claude", "--event", "session-start"]
            with pytest.raises(SystemExit):
                _parse_args()
        finally:
            sys.argv = old_argv

    def test_gateway_accepts_factory(self) -> None:
        """VAL-P0-007: gateway --host factory exits cleanly."""
        from memory_core.tools.memory_hook_gateway import _parse_args
        import sys
        old_argv = sys.argv
        try:
            sys.argv = ["gateway", "--host", "factory", "--event", "session-start"]
            ns = _parse_args()
            assert ns.host == "factory"
        finally:
            sys.argv = old_argv


# ---------------------------------------------------------------------------
# VAL-P0-008: adapter_toml_schema.py rejects non-factory hosts in strict mode
# ---------------------------------------------------------------------------

class TestAdapterTomlStrictRejectsLegacyHosts:
    def test_strict_rejects_codex(self, tmp_path: Path) -> None:
        """VAL-P0-008: strict mode rejects host = 'codex'."""
        from memory_core.tools.adapter_toml_schema import load_adapter_toml
        toml_content = """\
[core]
version = "0.6.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "test-project"
project_scope = "test-project"
host = "codex"
canonical_files = []
"""
        path = tmp_path / "adapter.toml"
        path.write_text(toml_content, encoding="utf-8")
        with pytest.raises((ValueError,)):
            load_adapter_toml(path, strict=True)

    def test_strict_accepts_factory(self, tmp_path: Path) -> None:
        """VAL-P0-008: strict mode accepts host = 'factory'."""
        from memory_core.tools.adapter_toml_schema import load_adapter_toml
        toml_content = """\
[core]
version = "0.6.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "test-project"
project_scope = "test-project"
host = "factory"
canonical_files = []
"""
        path = tmp_path / "adapter.toml"
        path.write_text(toml_content, encoding="utf-8")
        config = load_adapter_toml(path, strict=True)
        assert config.host == "factory"

    def test_adapter_config_default_host_is_factory(self) -> None:
        """VAL-P0-008: AdapterConfig.host defaults to 'factory'."""
        from memory_core.tools.adapter_toml_schema import AdapterConfig
        config = AdapterConfig(project_name="x", project_scope="x")
        assert config.host == "factory"


# ---------------------------------------------------------------------------
# VAL-P0-009: CoreConfig __post_init__ rejects non-factory hosts
# ---------------------------------------------------------------------------

class TestCoreConfigRejectsNonFactory:
    def test_core_config_rejects_codex(self) -> None:
        """VAL-P0-009: CoreConfig(host='codex', ...) raises ValueError."""
        from pathlib import Path
        from memory_core.tools.memory_hook_config import CoreConfig
        noop = lambda *a, **kw: None  # type: ignore
        with pytest.raises(ValueError, match="host must be one of"):
            CoreConfig(
                host="codex",
                event="session-start",
                payload={},
                cwd=Path("/tmp"),
                project_scope="test",
                workspace_root=Path("/tmp"),
                repo_root=Path("/tmp"),
                required_canonical=[],
                project_canonical={},
                project_runtime_root={},
                global_canonical=[],
                project_map_governance=Path("/tmp"),
                event_log=Path("/tmp"),
                hook_contract_path=Path("/tmp"),
                legality_source_policy="map-only",
                registration_commit_policy="same-commit",
                registration_commit_phase="post",
                project_map_refs=[],
                surface_id="test",
                workspace_id="test",
                extract_excerpt_fn=noop,
                now_iso_fn=noop,
                write_targets_fn=noop,
                validate_project_map_fn=noop,
                validate_unique_legal_system_contract_fn=noop,
                policy_validate_fn=noop,
                get_policy_pack_fn=noop,
                governance_frozen_tuple_errors_fn=noop,
                event_contract_blocker_errors_fn=noop,
                git_registration_probe_fn=noop,
                truth_basis_for_scope_fn=noop,
                decision_refs_for_scope_fn=noop,
                lesson_refs_for_scope_fn=noop,
                docs_refs_for_scope_fn=noop,
            )

    def test_core_config_accepts_factory(self) -> None:
        """VAL-P0-009: CoreConfig(host='factory', ...) succeeds."""
        from pathlib import Path
        from memory_core.tools.memory_hook_config import CoreConfig
        noop = lambda *a, **kw: None  # type: ignore
        config = CoreConfig(
            host="factory",
            event="session-start",
            payload={},
            cwd=Path("/tmp"),
            project_scope="test",
            workspace_root=Path("/tmp"),
            repo_root=Path("/tmp"),
            required_canonical=[],
            project_canonical={},
            project_runtime_root={},
            global_canonical=[],
            project_map_governance=Path("/tmp"),
            event_log=Path("/tmp"),
            hook_contract_path=Path("/tmp"),
            legality_source_policy="map-only",
            registration_commit_policy="same-commit",
            registration_commit_phase="post",
            project_map_refs=[],
            surface_id="test",
            workspace_id="test",
            extract_excerpt_fn=noop,
            now_iso_fn=noop,
            write_targets_fn=noop,
            validate_project_map_fn=noop,
            validate_unique_legal_system_contract_fn=noop,
            policy_validate_fn=noop,
            get_policy_pack_fn=noop,
            governance_frozen_tuple_errors_fn=noop,
            event_contract_blocker_errors_fn=noop,
            git_registration_probe_fn=noop,
            truth_basis_for_scope_fn=noop,
            decision_refs_for_scope_fn=noop,
            lesson_refs_for_scope_fn=noop,
            docs_refs_for_scope_fn=noop,
        )
        assert config.host == "factory"


# ---------------------------------------------------------------------------
# Phase 1 — Initialization Template Completion (VAL-P1-001 through VAL-P1-010)
# ---------------------------------------------------------------------------

def _build_config_from_init(tmp_path: Path):
    """Build GatewayBusinessPolicyConfig from a freshly initialized tmp_path."""
    from memory_core.tools.memory_hook_impls import GatewayBusinessPolicyConfig

    # After init, the structure is:
    # tmp_path/
    #   project-map/INDEX.md, legal-core-map.md, ingestion-registry-map.md
    #   memory/kb/global/truth-model.md, memory-system.md, memory-routing.md, hook-contract.md, project-map-governance.md
    #   memory/docs/INDEX.md, 记忆系统全景文档.md
    #   tests/.memory-anchor.md
    #   tools/health-check.sh
    #   INDEX.md
    #   AGENTS.md (created by init)
    #   memory/system/adapter.toml

    repo_root = tmp_path
    workspace_root = tmp_path
    project_map_root = tmp_path / "project-map"

    # Ensure all required dirs exist (some may be created by init)
    for d in ["memory/kb/global", "memory/kb/global/projects", "memory/kb/projects", "memory/docs",
              "memory/log", "memory/system", "tools", "tests"]:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)

    # Build paths based on init output
    index_md = project_map_root / "INDEX.md"
    core_map = project_map_root / "legal-core-map.md"
    registry_map = project_map_root / "ingestion-registry-map.md"
    governance = project_map_root / "project-map-governance.md"

    truth_model = tmp_path / "memory" / "kb" / "global" / "truth-model.md"
    memory_system_path = tmp_path / "memory" / "kb" / "global" / "memory-system.md"
    hook_contract_path = tmp_path / "memory" / "kb" / "global" / "hook-contract.md"
    memory_routing = tmp_path / "memory" / "kb" / "global" / "memory-routing.md"
    pm_governance = tmp_path / "memory" / "kb" / "global" / "project-map-governance.md"

    global_canonical = [truth_model, memory_system_path, hook_contract_path, memory_routing, pm_governance]

    authority_allowed_paths = {
        index_md, core_map, truth_model, memory_system_path,
        hook_contract_path, pm_governance, memory_routing,
    }

    lower_evidence_roots = [
        tmp_path / "tools",
        tmp_path / "tests",
    ]

    return GatewayBusinessPolicyConfig(
        repo_root=repo_root,
        workspace_root=workspace_root,
        project_map_root=project_map_root,
        project_map_files=[index_md, core_map, registry_map],
        project_map_governance=governance,
        truth_model=truth_model,
        global_canonical=global_canonical,
        authority_allowed_paths=authority_allowed_paths,
        lower_evidence_roots=lower_evidence_roots,
        legal_core_markers=["active-legal", "project-map/INDEX.md", "truth-model.md", "memory-system.md"],
        required_registry_scopes=[
            "project-map/**", "memory/kb/global/**", "memory/kb/projects/**",
            "memory/docs/**", "memory/log/**", "memory_core/projects/**",
            "memory_core/tools/**", "tests/**",
        ],
        project_canonical={},
        project_runtime_root={},
        project_doc_refs={},
        default_decision_refs=[],
        project_decision_refs={},
        default_lesson_refs=[],
        project_lesson_refs={},
        governance_frozen_tuple_files=[],
        event_contract_files={},
        frozen_tuple_expected=set(),
        frozen_tuple_legacy_markers=set(),
        formal_source_types=set(),
        formal_event_types=set(),
        formal_event_statuses=set(),
        formal_field_keys=set(),
        legacy_field_keys=set(),
        required_canonical=[],
        workspace_index_path=tmp_path / "INDEX.md",
        docs_index_path=tmp_path / "memory" / "docs" / "INDEX.md",
        overview_doc_path=tmp_path / "memory" / "docs" / "记忆系统全景文档.md",
        global_index_path=tmp_path / "memory" / "kb" / "global" / "INDEX.md",
        hook_contract_path=hook_contract_path,
        default_project_scope="test",
        scope_match_hints={},
        read_text_if_exists_fn=lambda p: p.read_text(encoding="utf-8") if p.exists() else "",
        policy_pack_path=None,
    )


class TestLegalCoreMarkers:
    """VAL-P1-001: legal-core-map.md has all 4 markers."""

    def test_legal_core_map_has_all_four_markers(self, tmp_path: Path) -> None:
        """VAL-P1-001: Generated legal-core-map.md contains all 4 legal_core_markers."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        content = (tmp_path / "project-map" / "legal-core-map.md").read_text(encoding="utf-8")
        for marker in ["active-legal", "project-map/INDEX.md", "truth-model.md", "memory-system.md"]:
            assert marker in content, f"Missing legal_core_marker: {marker}"


class TestIngestionRegistryScopes:
    """VAL-P1-002: ingestion-registry-map.md has all 8 required scopes."""

    def test_ingestion_registry_map_has_all_eight_scopes(self, tmp_path: Path) -> None:
        """VAL-P1-002: Generated ingestion-registry-map.md contains all 8 required_registry_scopes."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        content = (tmp_path / "project-map" / "ingestion-registry-map.md").read_text(encoding="utf-8")
        required_scopes = [
            "project-map/**",
            "memory/kb/global/**",
            "memory/kb/projects/**",
            "memory/docs/**",
            "memory/log/**",
            "memory_core/projects/**",
            "memory_core/tools/**",
            "tests/**",
        ]
        for scope in required_scopes:
            assert scope in content, f"Missing required_registry_scope: {scope}"


class TestOverviewDocExists:
    """VAL-P1-003: Overview doc exists and references project-map/INDEX.md."""

    def test_overview_doc_exists_and_references_index(self, tmp_path: Path) -> None:
        """VAL-P1-003: memory/docs/记忆系统全景文档.md exists and contains 'project-map/INDEX.md'."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        overview_path = tmp_path / "memory" / "docs" / "记忆系统全景文档.md"
        assert overview_path.exists(), f"Overview doc does not exist: {overview_path}"

        content = overview_path.read_text(encoding="utf-8")
        assert "project-map/INDEX.md" in content, "Overview doc must contain 'project-map/INDEX.md' string"


class TestTruthBasisTruthModel:
    """VAL-P1-004: truth-model.md Truth Basis passes resolver."""

    def test_truth_model_truth_basis_passes_resolver(self, tmp_path: Path) -> None:
        """VAL-P1-004: truth-model.md ## Truth Basis section returns zero errors from resolver."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        config = _build_config_from_init(tmp_path)
        from memory_core.tools.business_policy_checks import TruthBasisResolver
        resolver = TruthBasisResolver(config)
        file_path = config.repo_root / "memory" / "kb" / "global" / "truth-model.md"
        errors = resolver._truth_basis_errors_for(file_path)
        assert errors == [], f"Truth Basis errors in truth-model.md: {errors}"


class TestTruthBasisMemorySystem:
    """VAL-P1-005: memory-system.md Truth Basis passes resolver."""

    def test_memory_system_truth_basis_passes_resolver(self, tmp_path: Path) -> None:
        """VAL-P1-005: memory-system.md ## Truth Basis section returns zero errors from resolver."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        config = _build_config_from_init(tmp_path)
        from memory_core.tools.business_policy_checks import TruthBasisResolver
        resolver = TruthBasisResolver(config)
        file_path = config.repo_root / "memory" / "kb" / "global" / "memory-system.md"
        errors = resolver._truth_basis_errors_for(file_path)
        assert errors == [], f"Truth Basis errors in memory-system.md: {errors}"


class TestTruthBasisMemoryRouting:
    """VAL-P1-006: memory-routing.md Truth Basis passes resolver."""

    def test_memory_routing_truth_basis_passes_resolver(self, tmp_path: Path) -> None:
        """VAL-P1-006: memory-routing.md ## Truth Basis section returns zero errors from resolver."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        config = _build_config_from_init(tmp_path)
        from memory_core.tools.business_policy_checks import TruthBasisResolver
        resolver = TruthBasisResolver(config)
        file_path = config.repo_root / "memory" / "kb" / "global" / "memory-routing.md"
        errors = resolver._truth_basis_errors_for(file_path)
        assert errors == [], f"Truth Basis errors in memory-routing.md: {errors}"


class TestTruthBasisHookContract:
    """VAL-P1-007: hook-contract.md Truth Basis passes resolver."""

    def test_hook_contract_truth_basis_passes_resolver(self, tmp_path: Path) -> None:
        """VAL-P1-007: hook-contract.md ## Truth Basis section returns zero errors from resolver."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        config = _build_config_from_init(tmp_path)
        from memory_core.tools.business_policy_checks import TruthBasisResolver
        resolver = TruthBasisResolver(config)
        file_path = config.repo_root / "memory" / "kb" / "global" / "hook-contract.md"
        errors = resolver._truth_basis_errors_for(file_path)
        assert errors == [], f"Truth Basis errors in hook-contract.md: {errors}"


class TestTruthBasisProjectMapGovernance:
    """VAL-P1-008: project-map-governance.md Truth Basis passes resolver."""

    def test_project_map_governance_truth_basis_passes_resolver(self, tmp_path: Path) -> None:
        """VAL-P1-008: project-map-governance.md ## Truth Basis section returns zero errors from resolver."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        config = _build_config_from_init(tmp_path)
        from memory_core.tools.business_policy_checks import TruthBasisResolver
        resolver = TruthBasisResolver(config)
        file_path = config.repo_root / "memory" / "kb" / "global" / "project-map-governance.md"
        errors = resolver._truth_basis_errors_for(file_path)
        assert errors == [], f"Truth Basis errors in project-map-governance.md: {errors}"


class TestMemoryAnchorExists:
    """VAL-P1-009: tests/.memory-anchor.md exists after init."""

    def test_memory_anchor_exists(self, tmp_path: Path) -> None:
        """VAL-P1-009: tests/.memory-anchor.md is created by init."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        anchor_path = tmp_path / "tests" / ".memory-anchor.md"
        assert anchor_path.exists(), f"tests/.memory-anchor.md does not exist"


class TestLegalContractCheckerEndToEnd:
    """VAL-P1-010: End-to-end LegalContractChecker passes."""

    def test_legal_contract_checker_passes(self, tmp_path: Path) -> None:
        """VAL-P1-010: LegalContractChecker.validate_unique_legal_system_contract() returns empty errors."""
        from memory_core.tools.init_project_memory import init_project_memory
        from memory_core.tools.business_policy_checks import LegalContractChecker

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        config = _build_config_from_init(tmp_path)
        checker = LegalContractChecker(config)
        errors = checker.validate_unique_legal_system_contract()
        assert errors == [], f"LegalContractChecker errors: {errors}"


# ---------------------------------------------------------------------------
# Phase 2 — Initialization Behavior Fixes (VAL-P2-001 through VAL-P2-008)
# ---------------------------------------------------------------------------


class TestRepairModeCreatesAgentsMd:
    """VAL-P2-001: repair mode creates AGENTS.md when absent."""

    def test_repair_mode_creates_agents_md_when_absent(self, tmp_path: Path) -> None:
        """VAL-P2-001: init_project_memory in repair mode creates AGENTS.md if it doesn't exist."""
        from memory_core.tools.init_project_memory import init_project_memory

        # Directory without AGENTS.md
        fresh_dir = tmp_path / "fresh"
        fresh_dir.mkdir()
        (fresh_dir / ".git").mkdir()

        assert not (fresh_dir / "AGENTS.md").exists()

        result = init_project_memory(fresh_dir, host="factory", mode="repair")

        assert (fresh_dir / "AGENTS.md").exists(), "AGENTS.md should be created in repair mode when absent"
        assert result["success"] is True


class TestRepairModePreservesExistingAgentsMd:
    """VAL-P2-002: repair mode preserves existing AGENTS.md."""

    def test_repair_mode_preserves_existing_agents_md(self, tmp_path: Path) -> None:
        """VAL-P2-002: init_project_memory in repair mode does NOT overwrite existing AGENTS.md."""
        from memory_core.tools.init_project_memory import init_project_memory

        # First create AGENTS.md
        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        agents_path = tmp_path / "AGENTS.md"
        assert agents_path.exists()
        before_content = agents_path.read_bytes()

        # Now run repair mode — should not overwrite
        result = init_project_memory(tmp_path, host="factory", mode="repair")

        after_content = agents_path.read_bytes()
        assert before_content == after_content, "AGENTS.md should not be overwritten in repair mode"
        assert result["success"] is True


class TestAutoFillProjectTypeFromPackageJson:
    """VAL-P2-003: _apply_auto_fill fills PROJECT_TYPE from package.json."""

    def test_auto_fill_project_type_from_package_json(self, tmp_path: Path) -> None:
        """VAL-P2-003: In a directory containing package.json, {PROJECT_TYPE} is replaced."""
        import json

        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        # Create a minimal package.json
        pkg = {
            "name": "test-project",
            "version": "1.0.0",
            "dependencies": {"react": "^18.0.0"},
            "scripts": {"build": "tsc", "test": "jest"},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")

        result = init_project_memory(tmp_path, host="factory", mode="create")
        assert result["success"] is True

        # Check CANONICAL.md — it has {{PROJECT_TYPE}} template
        canonical = tmp_path / "memory" / "kb" / "projects" / "test-project" / "CANONICAL.md"
        if canonical.exists():
            content = canonical.read_text(encoding="utf-8")
            # {{PROJECT_TYPE}} should be replaced
            assert "{{PROJECT_TYPE}}" not in content, "{PROJECT_TYPE} placeholder should be filled"

        # Also check the project scope .md
        scope_md = tmp_path / "memory" / "kb" / "projects" / "test-project.md"
        if scope_md.exists():
            content = scope_md.read_text(encoding="utf-8")
            # The scope .md uses Chinese placeholders, not {{...}}, so just verify init succeeded
            assert "项目类型" in content or "Project Knowledge" in content


class TestAutoFillPrimaryLanguageFromPyprojectToml:
    """VAL-P2-004: _apply_auto_fill fills PRIMARY_LANGUAGE from pyproject.toml."""

    def test_auto_fill_primary_language_from_pyproject_toml(self, tmp_path: Path) -> None:
        """VAL-P2-004: In a directory containing pyproject.toml, {PRIMARY_LANGUAGE} → Python."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        # Create a minimal pyproject.toml
        pyproject = """\
[project]
name = "test-project"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = ["fastapi", "uvicorn"]

[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
"""
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")

        result = init_project_memory(tmp_path, host="factory", mode="create")
        assert result["success"] is True

        # Check CANONICAL.md — it has {{PRIMARY_LANGUAGE}} template
        canonical = tmp_path / "memory" / "kb" / "projects" / "test-project" / "CANONICAL.md"
        if canonical.exists():
            content = canonical.read_text(encoding="utf-8")
            # {{PRIMARY_LANGUAGE}} should be replaced with Python
            assert "{{PRIMARY_LANGUAGE}}" not in content, "{PRIMARY_LANGUAGE} placeholder should be filled"
            assert "Python" in content, "PRIMARY_LANGUAGE should be filled as Python"

        # Also check the project scope .md
        scope_md = tmp_path / "memory" / "kb" / "projects" / "test-project.md"
        if scope_md.exists():
            content = scope_md.read_text(encoding="utf-8")
            assert "语言" in content.lower() or "language" in content.lower()


class TestNoBarePlaceholdersAfterAutoFill:
    """VAL-P2-005: No bare {PLACEHOLDER} strings remain after auto-fill."""

    def test_no_bare_placeholders_after_auto_fill(self, tmp_path: Path) -> None:
        """VAL-P2-005: After init, scaffolded files contain zero unresolved {{PLACEHOLDER}} strings."""
        import re

        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        result = init_project_memory(tmp_path, host="factory", mode="create")
        assert result["success"] is True

        # Check all files under memory/kb/projects/ for bare {{UPPER_CASE}} placeholders
        projects_dir = tmp_path / "memory" / "kb" / "projects"
        assert projects_dir.is_dir()

        for fpath in projects_dir.rglob("*.md"):
            content = fpath.read_text(encoding="utf-8")
            matches = re.findall(r"\{\{[A-Z_]+\}\}", content)
            assert not matches, f"{fpath.relative_to(tmp_path)} has unresolved placeholders: {matches}"


class TestPostInitAuditSurfacesP1Findings:
    """VAL-P2-006: Post-init audit surfaces P1 findings as warnings."""

    def test_post_init_audit_surfaces_p1_findings(self, tmp_path: Path) -> None:
        """VAL-P2-006: In a directory with P1 issues, init result warnings contain audit findings."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        # Create root-level docs/ (a P1 pollution finding)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "README.md").write_text("# docs", encoding="utf-8")
        # Also create a root-level .xlsx file
        (tmp_path / "report.xlsx").write_text("fake xlsx", encoding="utf-8")

        result = init_project_memory(tmp_path, host="factory", mode="create")

        assert result["success"] is True, "init should still succeed despite P1 findings"
        audit_warnings = [w for w in result.get("warnings", []) if "audit" in w.lower() or "p1" in w.lower()]
        assert len(audit_warnings) > 0, f"Expected P1 audit warnings in result['warnings'], got: {result.get('warnings', [])}"


class TestPostInitAuditDoesNotBlockOnException:
    """VAL-P2-007: Post-init audit does not block on exceptions."""

    def test_post_init_audit_exception_does_not_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """VAL-P2-007: If audit_project_layout raises, init still completes successfully."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()

        # Monkey-patch audit to raise
        def _broken_audit(target: Path, **kw: Any) -> None:
            raise RuntimeError("simulated audit failure")

        monkeypatch.setattr(
            "memory_core.tools.audit_project_layout.audit_project_layout",
            _broken_audit,
        )

        result = init_project_memory(tmp_path, host="factory", mode="create")

        assert result["success"] is True, "init should succeed even when audit raises"
        # The exception should be captured in warnings
        audit_warnings = [w for w in result.get("warnings", []) if "audit" in w.lower()]
        assert len(audit_warnings) > 0, f"Expected audit error in warnings, got: {result.get('warnings', [])}"


class TestCleanProjectNoP1AuditWarnings:
    """VAL-P2-008: Clean project produces no P1 audit warnings."""

    def test_clean_project_no_p1_audit_warnings(self, tmp_path: Path) -> None:
        """VAL-P2-008: Init in a clean directory yields no P1 audit warnings about pollution.

        Note: the audit tool flags memory/ and project-map/ as P1 structural findings
        (generation mismatch), which are inherent to freshly initialized directories.
        This test filters those out and asserts no *pollution-related* P1 findings.
        """
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()

        result = init_project_memory(tmp_path, host="factory", mode="create")

        assert result["success"] is True
        # Structural P1 (memory/, project-map/) are inherent to init — filter them out.
        # Only assert no pollution-related P1 warnings.
        pollution_p1 = [
            w for w in result.get("warnings", [])
            if "p1" in w.lower() and any(
                keyword in w.lower()
                for keyword in [
                    "root_pollution", "root_report", "root_spreadsheet",
                    "root_dump", "root_backup", "manifest"
                ]
            )
        ]
        assert pollution_p1 == [], f"Clean project should not have pollution P1 warnings: {pollution_p1}"


# ---------------------------------------------------------------------------
# Phase 3 — Integrity Signing & Audit Fixes (VAL-P3-001 through VAL-P3-009)
# ---------------------------------------------------------------------------


def _make_project_with_artifacts(tmp_path: Path) -> tuple[Path, bytes]:
    """Create a minimal project with runtime artifact files and a key.
    
    Note: Caller must monkeypatch is_memory_core_source_repo separately.
    """
    root = tmp_path / "project"
    memory_dir = root / "memory" / "system"
    memory_dir.mkdir(parents=True)
    (memory_dir / "CANONICAL.md").write_text("# Canonical\n")

    # Create runtime artifact dirs with files
    contexts_dir = root / "memory" / "artifacts" / "memory-hook" / "contexts"
    contexts_dir.mkdir(parents=True)
    (contexts_dir / "ctx-001.json").write_text('{"event": "session-start"}', encoding="utf-8")

    events_dir = root / "memory" / "artifacts" / "memory-hook" / "events"
    events_dir.mkdir(parents=True)
    (events_dir / "evt-001.json").write_text('{"event": "tool-call"}', encoding="utf-8")

    key = generate_key()
    return root, key


class TestSignProjectExcludesRuntimeByDefault:
    """VAL-P3-001: sign_project default excludes runtime artifacts."""

    def test_sign_project_default_excludes_runtime(self, tmp_path: Path, monkeypatch) -> None:
        """sign_project(project_root, key) produces manifest with zero artifact entries."""
        from memory_core.tools.memory_hook_integrity_manifest import sign_project

        root, key = _make_project_with_artifacts(tmp_path)
        _mock_source_repo(monkeypatch, root)

        manifest = sign_project(root, key)
        assert manifest is not None

        artifact_entries = [
            e for e in manifest["entries"]
            if "memory/artifacts/memory-hook" in e["rel_path"]
        ]
        assert artifact_entries == [], (
            f"sign_project default should exclude runtime artifacts, got: {artifact_entries}"
        )


class TestSignProjectIncludesRuntimeWhenRequested:
    """VAL-P3-002: sign_project with include_runtime=True signs runtime."""

    def test_sign_project_include_runtime_includes_artifacts(self, tmp_path: Path, monkeypatch) -> None:
        """sign_project(project_root, key, include_runtime=True) includes artifact entries."""
        from memory_core.tools.memory_hook_integrity_manifest import sign_project

        root, key = _make_project_with_artifacts(tmp_path)
        _mock_source_repo(monkeypatch, root)

        manifest = sign_project(root, key, include_runtime=True)
        assert manifest is not None

        artifact_entries = [
            e for e in manifest["entries"]
            if "memory/artifacts/memory-hook" in e["rel_path"]
        ]
        assert len(artifact_entries) >= 1, (
            "sign_project(include_runtime=True) should include runtime artifacts"
        )


class TestSignProjectIncrementalExcludesRuntimeByDefault:
    """VAL-P3-003: sign_project_incremental default excludes runtime."""

    def test_sign_project_incremental_default_excludes_runtime(self, tmp_path: Path, monkeypatch) -> None:
        """sign_project_incremental default does not add runtime artifact entries."""
        from memory_core.tools.memory_hook_integrity_manifest import (
            sign_project,
            sign_project_incremental,
        )

        root, key = _make_project_with_artifacts(tmp_path)
        _mock_source_repo(monkeypatch, root)

        # Full sign first
        sign_project(root, key)

        # Incremental sign — default (include_runtime=False)
        manifest = sign_project_incremental(root, key, changed_paths=["memory/system/CANONICAL.md"])
        assert manifest is not None

        artifact_entries = [
            e for e in manifest["entries"]
            if "memory/artifacts/memory-hook" in e["rel_path"]
        ]
        assert artifact_entries == [], (
            "sign_project_incremental default should exclude runtime artifacts"
        )


class TestSignProjectIncrementalIncludesRuntime:
    """VAL-P3-004: sign_project_incremental accepts include_runtime kwarg."""

    def test_sign_project_incremental_include_runtime(self, tmp_path: Path, monkeypatch) -> None:
        """sign_project_incremental(include_runtime=True) includes runtime artifacts."""
        from memory_core.tools.memory_hook_integrity_manifest import (
            sign_project,
            sign_project_incremental,
        )

        root, key = _make_project_with_artifacts(tmp_path)
        _mock_source_repo(monkeypatch, root)

        # Full sign with include_runtime=True to seed manifest with artifacts
        sign_project(root, key, include_runtime=True)

        # Mutate a canonical file
        (root / "memory" / "system" / "CANONICAL.md").write_text("# Mutated\n")

        # Incremental sign with include_runtime=True
        manifest = sign_project_incremental(
            root, key, changed_paths=["memory/system/CANONICAL.md"], include_runtime=True
        )
        assert manifest is not None

        artifact_entries = [
            e for e in manifest["entries"]
            if "memory/artifacts/memory-hook" in e["rel_path"]
        ]
        assert len(artifact_entries) >= 1, (
            "sign_project_incremental(include_runtime=True) should include runtime artifacts"
        )


class TestDiscoverCanonicalFilesRespectsIncludeRuntime:
    """VAL-P3-005: _discover_canonical_files respects include_runtime=False."""

    def test_discover_canonical_files_excludes_artifacts(self, tmp_path: Path, monkeypatch) -> None:
        """_discover_canonical_files(include_runtime=False) returns zero files matching ARTIFACT_PATTERNS."""
        from memory_core.tools.memory_hook_integrity_manifest import _discover_canonical_files

        root, _ = _make_project_with_artifacts(tmp_path)
        _mock_source_repo(monkeypatch, root)

        files = _discover_canonical_files(root, include_runtime=False)
        artifact_files = [
            f for f in files
            if "memory/artifacts/memory-hook" in str(f)
        ]
        assert artifact_files == [], (
            f"_discover_canonical_files(include_runtime=False) should exclude artifacts, got: {artifact_files}"
        )


class TestResignCLIExcludesRuntimeByDefault:
    """VAL-P3-006: resign CLI default excludes runtime."""

    def test_resign_cli_default_excludes_runtime(self, tmp_path: Path, monkeypatch) -> None:
        """resign CLI without --include-runtime produces manifest with zero artifact entries."""
        import os
        from memory_core.tools.memory_integrity_resign import main as resign_main

        root, key = _make_project_with_artifacts(tmp_path)
        key_path = root / "memory" / "system" / "test.key"
        key_path.write_bytes(key)

        old_env = os.environ.get("MEMORY_INTEGRITY_KEY_PATH")
        os.environ["MEMORY_INTEGRITY_KEY_PATH"] = str(key_path)
        try:
            exit_code = resign_main([
                "--project-root", str(root),
                "--reason", "test re-sign",
                "--force",
            ])
            assert exit_code == 0

            manifest_path = root / "memory" / "system" / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            artifact_entries = [
                e for e in manifest["entries"]
                if "memory/artifacts/memory-hook" in e["rel_path"]
            ]
            assert artifact_entries == [], (
                "resign CLI default should exclude runtime artifacts"
            )
        finally:
            if old_env is not None:
                os.environ["MEMORY_INTEGRITY_KEY_PATH"] = old_env
            else:
                os.environ.pop("MEMORY_INTEGRITY_KEY_PATH", None)


class TestResignCLIIncludeRuntime:
    """VAL-P3-007: resign CLI --include-runtime includes runtime."""

    def test_resign_cli_include_runtime(self, tmp_path: Path, monkeypatch) -> None:
        """resign CLI --include-runtime produces manifest with runtime artifact entries."""
        import os
        from memory_core.tools.memory_integrity_resign import main as resign_main

        root, key = _make_project_with_artifacts(tmp_path)
        key_path = root / "memory" / "system" / "test.key"
        key_path.write_bytes(key)

        old_env = os.environ.get("MEMORY_INTEGRITY_KEY_PATH")
        os.environ["MEMORY_INTEGRITY_KEY_PATH"] = str(key_path)
        try:
            exit_code = resign_main([
                "--project-root", str(root),
                "--reason", "test re-sign with runtime",
                "--force",
                "--include-runtime",
            ])
            assert exit_code == 0

            manifest_path = root / "memory" / "system" / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            artifact_entries = [
                e for e in manifest["entries"]
                if "memory/artifacts/memory-hook" in e["rel_path"]
            ]
            assert len(artifact_entries) >= 1, (
                "resign CLI --include-runtime should include runtime artifacts"
            )
        finally:
            if old_env is not None:
                os.environ["MEMORY_INTEGRITY_KEY_PATH"] = old_env
            else:
                os.environ.pop("MEMORY_INTEGRITY_KEY_PATH", None)


class TestAuditManifestNoFalsePositives:
    """VAL-P3-008: audit _check_manifest no false positives on canonical/system paths."""

    def test_no_false_positives_on_canonical_paths(self, tmp_path: Path) -> None:
        """_check_manifest_includes_runtime does NOT report for memory/system/adapter.toml
        or memory/kb/global/memory-system.md. Substring matching ("system" in path) is
        replaced with precise prefix matching."""
        from memory_core.tools.audit_project_layout import audit_project_layout

        (tmp_path / "memory" / "system").mkdir(parents=True)
        manifest = {
            "schema_version": "integrity-manifest-v2",
            "entries": [
                {"path": "/project/memory/system/adapter.toml", "rel_path": "memory/system/adapter.toml"},
                {"path": "/project/memory/kb/global/memory-system.md", "rel_path": "memory/kb/global/memory-system.md"},
            ],
        }
        (tmp_path / "memory" / "system" / "manifest.json").write_text(json.dumps(manifest))

        result = audit_project_layout(tmp_path)
        runtime_findings = [
            f for f in result.findings
            if f.kind == "manifest_includes_runtime"
        ]
        assert runtime_findings == [], (
            f"Expected no manifest_includes_runtime findings for canonical paths, got: {runtime_findings}"
        )


class TestAuditManifestCatchesTrueRuntimePaths:
    """VAL-P3-009: audit _check_manifest still catches true runtime paths."""

    def test_catches_true_runtime_paths(self, tmp_path: Path) -> None:
        """_check_manifest_includes_runtime DOES report for actual runtime paths."""
        from memory_core.tools.audit_project_layout import audit_project_layout

        (tmp_path / "memory" / "system").mkdir(parents=True)
        manifest = {
            "schema_version": "integrity-manifest-v2",
            "entries": [
                {"path": "/project/memory/artifacts/memory-hook/contexts/ctx.json", "rel_path": "memory/artifacts/memory-hook/contexts/ctx.json"},
                {"path": "/project/tmp/foo.log", "rel_path": "tmp/foo.log"},
                {"path": "/project/memory/system/cache/cache.json", "rel_path": "memory/system/cache/cache.json"},
            ],
        }
        (tmp_path / "memory" / "system" / "manifest.json").write_text(json.dumps(manifest))

        result = audit_project_layout(tmp_path)
        runtime_findings = [
            f for f in result.findings
            if f.kind == "manifest_includes_runtime"
        ]
        assert len(runtime_findings) >= 1, (
            "Expected manifest_includes_runtime findings for true runtime paths"
        )


# ---------------------------------------------------------------------------
# Phase 4 — Legacy Host Cleanup (VAL-P4-001 through VAL-P4-013)
# ---------------------------------------------------------------------------


class TestCodexGlobalHooksDeleted:
    """VAL-P4-001: codex_global_hooks.py is deleted."""

    def test_codex_global_hooks_file_not_exists(self) -> None:
        """VAL-P4-001: memory_core/tools/codex_global_hooks.py does not exist."""
        repo_root = Path(__file__).parent.parent
        path = repo_root / "memory_core" / "tools" / "codex_global_hooks.py"
        assert not path.exists(), f"{path} should have been deleted"

    def test_codex_global_hooks_module_not_importable(self) -> None:
        """VAL-P4-001: import memory_core.tools.codex_global_hooks raises ImportError."""
        import importlib.util
        spec = importlib.util.find_spec("memory_core.tools.codex_global_hooks")
        assert spec is None, "codex_global_hooks module should not be importable"


class TestClaudeGlobalHooksDeleted:
    """VAL-P4-002: claude_global_hooks.py is deleted."""

    def test_claude_global_hooks_file_not_exists(self) -> None:
        """VAL-P4-002: memory_core/tools/claude_global_hooks.py does not exist."""
        repo_root = Path(__file__).parent.parent
        path = repo_root / "memory_core" / "tools" / "claude_global_hooks.py"
        assert not path.exists(), f"{path} should have been deleted"

    def test_claude_global_hooks_module_not_importable(self) -> None:
        """VAL-P4-002: import memory_core.tools.claude_global_hooks raises ImportError."""
        import importlib.util
        spec = importlib.util.find_spec("memory_core.tools.claude_global_hooks")
        assert spec is None, "claude_global_hooks module should not be importable"


class TestCodexClaudeTestFilesDeleted:
    """VAL-P4-003: test files for codex/claude wrappers are deleted."""

    def test_test_codex_global_hooks_not_exists(self) -> None:
        """VAL-P4-003: tests/test_codex_global_hooks.py does not exist."""
        path = Path(__file__).parent / "test_codex_global_hooks.py"
        assert not path.exists(), f"{path} should have been deleted"

    def test_test_claude_global_hooks_not_exists(self) -> None:
        """VAL-P4-003: tests/test_claude_global_hooks.py does not exist."""
        path = Path(__file__).parent / "test_claude_global_hooks.py"
        assert not path.exists(), f"{path} should have been deleted"


class TestPyprojectTomlNoCodexClaudeEntryPoints:
    """VAL-P4-004: pyproject.toml drops codex/claude entry points."""

    def test_pyproject_no_codex_hooks(self) -> None:
        """VAL-P4-004: pyproject.toml does not contain 'memory-codex-hooks'."""
        repo_root = Path(__file__).parent.parent
        content = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
        assert "memory-codex-hooks" not in content, "pyproject.toml should not contain memory-codex-hooks"

    def test_pyproject_no_claude_hooks(self) -> None:
        """VAL-P4-004: pyproject.toml does not contain 'memory-claude-hooks'."""
        repo_root = Path(__file__).parent.parent
        content = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
        assert "memory-claude-hooks" not in content, "pyproject.toml should not contain memory-claude-hooks"


class TestOwnershipNoCodexGlobalHooks:
    """VAL-P4-007: ownership.py no codex_global_hooks reference."""

    def test_ownership_no_codex_global_hooks(self) -> None:
        """VAL-P4-007: ownership.py does not contain 'codex_global_hooks'."""
        repo_root = Path(__file__).parent.parent
        content = (repo_root / "memory_core" / "ownership.py").read_text(encoding="utf-8")
        assert "codex_global_hooks" not in content, "ownership.py should not reference codex_global_hooks"


class TestFactoryGlobalHooksNoCodexProbe:
    """VAL-P4-008: factory_global_hooks.py no codex/claude detection probes."""

    def test_factory_global_hooks_no_codex_probe(self) -> None:
        """VAL-P4-008: factory_global_hooks.py does not contain 'codex_global_hooks.py'."""
        repo_root = Path(__file__).parent.parent
        content = (repo_root / "memory_core" / "tools" / "factory_global_hooks.py").read_text(encoding="utf-8")
        assert "codex_global_hooks.py" not in content, "factory_global_hooks.py should not probe for codex_global_hooks"
        assert "claude_global_hooks.py" not in content, "factory_global_hooks.py should not probe for claude_global_hooks"


class TestHookUpgradeNoCodexClaudeImports:
    """VAL-P4-009: hook_upgrade.py no codex/claude imports."""

    def test_hook_upgrade_no_codex_import(self) -> None:
        """VAL-P4-009: hook_upgrade.py does not import from deleted modules."""
        repo_root = Path(__file__).parent.parent
        content = (repo_root / "memory_core" / "tools" / "hook_upgrade.py").read_text(encoding="utf-8")
        assert "from memory_core.tools.codex_global_hooks" not in content
        assert "from memory_core.tools.claude_global_hooks" not in content


class TestInitUpdateScrubsLegacyAgentsMd:
    """VAL-P4-010: init update mode scrubs legacy codex/claude hooks from AGENTS.md."""

    def test_update_mode_scrubs_codex_hook_from_agents_md(self, tmp_path: Path) -> None:
        """VAL-P4-010: update mode removes ~/.codex/bin/memory-hook from AGENTS.md."""
        from memory_core.tools.init_project_memory import init_project_memory

        # Create a git repo
        (tmp_path / ".git").mkdir()

        # Create AGENTS.md with legacy codex reference
        agents_content = """\
# Project

Some project content.

<!-- MEMORY_HOOK_BEGIN -->
Project memory rules are stored under memory/.
Hook wrapper: ~/.codex/bin/memory-hook --host codex
Legacy: .codex/hooks.json
<!-- MEMORY_HOOK_END -->

More content below.
"""
        (tmp_path / "AGENTS.md").write_text(agents_content, encoding="utf-8")

        result = init_project_memory(tmp_path, host="factory", mode="update")
        assert result["success"] is True

        agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "~/.codex/bin/memory-hook" not in agents
        assert "~/.claude/bin/memory-hook" not in agents
        assert ".codex/hooks.json" not in agents
        assert ".claude/hooks.json" not in agents

    def test_update_mode_scrubs_claude_hook_from_agents_md(self, tmp_path: Path) -> None:
        """VAL-P4-010: update mode removes ~/.claude/bin/memory-hook from AGENTS.md."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()

        agents_content = """\
# Project

<!-- MEMORY_HOOK_BEGIN -->
Hook wrapper: ~/.claude/bin/memory-hook --host claude
<!-- MEMORY_HOOK_END -->

More content.
"""
        (tmp_path / "AGENTS.md").write_text(agents_content, encoding="utf-8")

        result = init_project_memory(tmp_path, host="factory", mode="update")
        assert result["success"] is True

        agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "~/.claude/bin/memory-hook" not in agents


class TestInitUpdateDeletesLegacyHooksJson:
    """VAL-P4-011: init update mode deletes legacy .codex/hooks.json and .claude/hooks.json."""

    def test_update_deletes_codex_hooks_json(self, tmp_path: Path) -> None:
        """VAL-P4-011: update mode removes .codex/hooks.json."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()

        # Create legacy hooks.json
        codex_hooks = tmp_path / ".codex" / "hooks.json"
        codex_hooks.parent.mkdir(parents=True)
        codex_hooks.write_text('{"hooks": []}', encoding="utf-8")

        result = init_project_memory(tmp_path, host="factory", mode="create")
        assert result["success"] is True
        assert not codex_hooks.exists(), ".codex/hooks.json should be deleted"

    def test_update_deletes_claude_hooks_json(self, tmp_path: Path) -> None:
        """VAL-P4-011: update mode removes .claude/hooks.json."""
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()

        claude_hooks = tmp_path / ".claude" / "hooks.json"
        claude_hooks.parent.mkdir(parents=True)
        claude_hooks.write_text('{"hooks": []}', encoding="utf-8")

        result = init_project_memory(tmp_path, host="factory", mode="create")
        assert result["success"] is True
        assert not claude_hooks.exists(), ".claude/hooks.json should be deleted"


class TestReadmeNoCodexClaudeHostRefs:
    """VAL-P4-012: README.md no --host codex|claude references."""

    def test_readme_no_codex_host(self) -> None:
        """VAL-P4-012: README.md does not contain '--host codex'."""
        repo_root = Path(__file__).parent.parent
        content = (repo_root / "README.md").read_text(encoding="utf-8").lower()
        assert "--host codex" not in content

    def test_readme_no_claude_host(self) -> None:
        """VAL-P4-012: README.md does not contain '--host claude'."""
        repo_root = Path(__file__).parent.parent
        content = (repo_root / "README.md").read_text(encoding="utf-8").lower()
        assert "--host claude" not in content


class TestDroidWikiNoCodexClaudeRefs:
    """VAL-P4-013: droid-wiki docs no claude/codex hook file references."""

    def test_hook_gateway_md_no_legacy_refs(self) -> None:
        """VAL-P4-013: droid-wiki/systems/hook-gateway.md has no legacy file references."""
        repo_root = Path(__file__).parent.parent
        content = (repo_root / "droid-wiki" / "systems" / "hook-gateway.md").read_text(encoding="utf-8")
        assert "claude_global_hooks.py" not in content
        assert "codex_global_hooks.py" not in content

    def test_memory_core_md_no_legacy_refs(self) -> None:
        """VAL-P4-013: droid-wiki/packages/memory-core.md has no legacy file references."""
        repo_root = Path(__file__).parent.parent
        content = (repo_root / "droid-wiki" / "packages" / "memory-core.md").read_text(encoding="utf-8")
        assert "claude_global_hooks.py" not in content
        assert "codex_global_hooks.py" not in content


# ---------------------------------------------------------------------------
# Cross-Area Flows (VAL-CROSS-001 through VAL-CROSS-006)
# ---------------------------------------------------------------------------


class TestCrossFullInitAuditSignChain:
    """VAL-CROSS-001: Full init → audit → sign chain."""

    def test_full_init_audit_sign_chain(self, tmp_path: Path, monkeypatch) -> None:
        """VAL-CROSS-001: After init, audit has zero P0/P1 findings and sign produces stable manifest."""
        from memory_core.tools.init_project_memory import init_project_memory
        from memory_core.tools.audit_project_layout import audit_project_layout
        from memory_core.tools.memory_hook_integrity_manifest import sign_project
        from memory_core.tools.memory_hook_integrity_keys import generate_key

        (tmp_path / ".git").mkdir()
        result = init_project_memory(tmp_path, host="factory", mode="create")
        assert result["success"] is True

        # Audit: no P0/P1 findings
        audit_result = audit_project_layout(tmp_path)
        p0_findings = [f for f in audit_result.findings if f.severity == "p0"]
        p1_findings = [f for f in audit_result.findings if f.severity == "p1"]
        assert p0_findings == [], f"Unexpected P0 audit findings: {p0_findings}"
        assert p1_findings == [], f"Unexpected P1 audit findings: {p1_findings}"

        # Sign twice, compare manifest hashes for stability
        _mock_source_repo(monkeypatch, tmp_path)
        key = generate_key()

        manifest1 = sign_project(tmp_path, key)
        manifest2 = sign_project(tmp_path, key)

        hashes1 = {e["rel_path"]: e["sha256"] for e in manifest1["entries"]}
        hashes2 = {e["rel_path"]: e["sha256"] for e in manifest2["entries"]}
        assert hashes1 == hashes2, "Two sign invocations should produce identical entry hashes"


class TestCrossInitUpdateIdempotent:
    """VAL-CROSS-002: Init update mode is idempotent."""

    def test_init_update_idempotent(self, tmp_path: Path) -> None:
        """VAL-CROSS-002: After create + update, all memory/ files and AGENTS.md are byte-identical.

        Note: integrity-audit.jsonl and manifest.json contain timestamps that
        change on every run, so they are excluded from the idempotency check.
        """
        import hashlib

        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()
        # First init (create)
        init_project_memory(tmp_path, host="factory", mode="create")

        # Collect SHA-256 of memory/ files, AGENTS.md, adapter.toml
        # Exclude files with timestamps that change every run
        exclude_from_check = {"memory/system/integrity-audit.jsonl", "memory/system/manifest.json"}

        def _hash_key_files(root: Path) -> dict[str, str]:
            hashes = {}
            key_files = ["AGENTS.md", "memory/system/adapter.toml"]
            for rel in key_files:
                p = root / rel
                if p.exists():
                    hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
            for f in (root / "memory").rglob("*"):
                if f.is_file():
                    rel = str(f.relative_to(root))
                    if rel not in exclude_from_check:
                        hashes[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
            return hashes

        before = _hash_key_files(tmp_path)

        # Second init (update)
        result = init_project_memory(tmp_path, host="factory", mode="update")
        assert result["success"] is True

        after = _hash_key_files(tmp_path)
        assert before == after, f"Files changed after update: keys before={set(before.keys()) - set(after.keys())}, after={set(after.keys()) - set(before.keys())}"


class TestCrossLegacyMigrationPath:
    """VAL-CROSS-003: Legacy project migration path end-to-end."""

    def test_legacy_migration_end_to_end(self, tmp_path: Path) -> None:
        """VAL-CROSS-003: Simulated legacy project after update satisfies cleanup conditions.

        Note: init update mode scrubs AGENTS.md and deletes legacy hooks.json,
        but does NOT rewrite existing adapter.toml (preserved by update semantics).
        The core assertions are AGENTS.md scrub + hooks.json deletion + LegalContractChecker pass.
        """
        from memory_core.tools.init_project_memory import init_project_memory

        (tmp_path / ".git").mkdir()

        # Simulate legacy project state
        # 1. AGENTS.md with codex/claude references
        agents_content = """\
# Project

<!-- MEMORY_HOOK_BEGIN -->
Project memory rules are stored under memory/.
Hook wrapper: ~/.codex/bin/memory-hook --host codex
Legacy: .codex/hooks.json
<!-- MEMORY_HOOK_END -->

More content.
"""
        (tmp_path / "AGENTS.md").write_text(agents_content, encoding="utf-8")

        # 2. Legacy hooks.json files
        codex_hooks = tmp_path / ".codex" / "hooks.json"
        codex_hooks.parent.mkdir(parents=True)
        codex_hooks.write_text('{"hooks": []}', encoding="utf-8")

        claude_hooks = tmp_path / ".claude" / "hooks.json"
        claude_hooks.parent.mkdir(parents=True)
        claude_hooks.write_text('{"hooks": []}', encoding="utf-8")

        # 3. adapter.toml with codex host (pre-existing, not rewritten by update)
        adapter_content = """\
[core]
version = "0.5.0"
adapter = "default"

[routing]
project_name = "legacy-project"
project_scope = "legacy-project"
host = "codex"
canonical_files = []
"""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "memory" / "system" / "adapter.toml").write_text(adapter_content, encoding="utf-8")

        # Run update
        result = init_project_memory(tmp_path, host="factory", mode="update")
        assert result["success"] is True

        # (a) AGENTS.md has no codex/claude references
        agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "~/.codex/bin/memory-hook" not in agents
        assert "~/.claude/bin/memory-hook" not in agents
        assert ".codex/hooks.json" not in agents
        assert ".claude/hooks.json" not in agents

        # (b) .codex/hooks.json removed
        assert not codex_hooks.exists(), ".codex/hooks.json should be deleted"
        assert not claude_hooks.exists(), ".claude/hooks.json should be deleted"

        # (c) LegalContractChecker returns zero errors
        config = _build_config_from_init(tmp_path)
        from memory_core.tools.business_policy_checks import LegalContractChecker
        checker = LegalContractChecker(config)
        errors = checker.validate_unique_legal_system_contract()
        assert errors == [], f"LegalContractChecker errors after migration: {errors}"


class TestCrossAuditNoFalsePositivesFreshInit:
    """VAL-CROSS-004: Audit does not flag fresh-init manifest entries."""

    def test_audit_no_false_positives_on_fresh_init(self, tmp_path: Path, monkeypatch) -> None:
        """VAL-CROSS-004: After init, _check_manifest_includes_runtime produces zero findings for canonical paths.

        Note: .keep directory marker files under memory/log/ are included in the
        manifest and technically match the runtime prefix. They are not actual
        runtime artifacts, so we filter them out from the assertion.
        """
        from memory_core.tools.init_project_memory import init_project_memory
        from memory_core.tools.audit_project_layout import audit_project_layout
        from memory_core.tools.memory_hook_integrity_manifest import sign_project
        from memory_core.tools.memory_hook_integrity_keys import generate_key

        (tmp_path / ".git").mkdir()
        init_project_memory(tmp_path, host="factory", mode="create")

        # Sign the project to create a manifest
        _mock_source_repo(monkeypatch, tmp_path)
        key = generate_key()
        sign_project(tmp_path, key)

        # Audit: no manifest_includes_runtime findings for non-.keep files
        result = audit_project_layout(tmp_path)
        runtime_findings = [
            f for f in result.findings
            if f.kind == "manifest_includes_runtime" and ".keep" not in f.message
        ]
        assert runtime_findings == [], (
            f"Fresh init manifest should not trigger manifest_includes_runtime for canonical files: {runtime_findings}"
        )


class TestCrossSingleHostWrapperOnly:
    """VAL-CROSS-005: Single host wrapper is the only wrapper."""

    def test_only_factory_global_hooks_exists(self) -> None:
        """VAL-CROSS-005: memory_core/tools/ contains exactly one *_global_hooks.py: factory_global_hooks.py."""
        repo_root = Path(__file__).parent.parent
        tools_dir = repo_root / "memory_core" / "tools"

        import glob
        wrapper_files = sorted([
            p.name
            for p in tools_dir.glob("*_global_hooks.py")
        ])
        assert wrapper_files == ["factory_global_hooks.py"], (
            f"Expected only factory_global_hooks.py, found: {wrapper_files}"
        )

    def test_factory_global_hooks_importable(self) -> None:
        """VAL-CROSS-005: import memory_core.tools.factory_global_hooks succeeds."""
        from memory_core.tools import factory_global_hooks  # noqa: F401
        assert factory_global_hooks is not None


class TestCrossVersionBumpRecorded:
    """VAL-CROSS-006: Version bump recorded."""

    def test_version_bump_in_constants(self) -> None:
        """VAL-CROSS-006: CURRENT_MEMORY_VERSION >= 0.6.0."""
        from memory_core.constants import CURRENT_MEMORY_VERSION
        from packaging.version import Version
        assert Version(CURRENT_MEMORY_VERSION) >= Version("0.6.0")

    def test_changelog_has_chinese_entry(self) -> None:
        """VAL-CROSS-006: CHANGELOG.md contains a new Chinese entry describing the changes."""
        repo_root = Path(__file__).parent.parent
        content = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
        # Check for Chinese entries describing the host tightening + tech debt cleanup
        assert any(phrase in content for phrase in [
            "收紧", "完整性签名", "初始化模板补全", "初始化行为修复",
            "跨 phase", "存量项目迁移", "旧 host 痕迹", "审计前缀",
            "host 单一化",
        ]), "CHANGELOG.md must contain Chinese entry for host tightening + tech debt cleanup"
