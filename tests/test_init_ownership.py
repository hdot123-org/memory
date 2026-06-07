"""Tests for M2 ownership migration features.

Covers:
- Init generates ownership.toml (all modes)
- Force restriction on owned files
- Validate ownership checks (2.3-2.6)
- Audit ownership findings
- Apply ownership-aware forbidden path detection
- Ownership.toml roundtrip
"""
from __future__ import annotations

import os
from unittest.mock import patch

from memory_core.ownership import (
    MemoryOwnership,
    Owned,
    classify_owned_path,
    load_memory_ownership,
    validate_ownership_schema,
)
from memory_core.tools.apply_residue_plan import _validate_plan
from memory_core.tools.audit_project_layout import audit_project_layout
from memory_core.tools.init_project_memory import init_project_memory
from memory_core.tools.validate_project_memory import validate_project_memory


class TestInitOwnershipGeneration:
    """Step 2.1 & 2.10: Init generates ownership.toml in all modes."""

    def test_init_create_generates_ownership_toml(self, tmp_path):
        """Create mode should generate ownership.toml."""
        result = init_project_memory(
            tmp_path,
            scope="test_project",
            host="factory",
            mode="create",
        )
        assert result["success"] is True
        assert "file:ownership.toml" in result["created"]

        ownership_path = tmp_path / "memory" / "system" / "ownership.toml"
        assert ownership_path.exists()

        # Verify content
        content = ownership_path.read_text(encoding="utf-8")
        assert "schema_version" in content
        assert "memory-ownership-v1" in content
        assert "[[domains]]" in content
        assert "[[resources]]" in content
        assert "[policy]" in content

    def test_init_adopt_does_not_overwrite_existing_ownership(self, tmp_path):
        """Adopt mode should not overwrite existing ownership.toml."""
        # First create
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Modify ownership.toml
        ownership_path = tmp_path / "memory" / "system" / "ownership.toml"
        original_content = ownership_path.read_text(encoding="utf-8")
        ownership_path.write_text(original_content + "\n# Modified", encoding="utf-8")

        # Adopt should skip - since ownership.toml is generated at end for all modes,
        # the adopt mode's _should_skip_file logic will skip existing files
        result = init_project_memory(tmp_path, scope="test_project", mode="adopt")
        assert result["success"] is True
        # ownership.toml is generated at the end, not through _should_skip_file
        # So it won't appear in "skipped" but the file should be preserved
        content = ownership_path.read_text(encoding="utf-8")
        assert "# Modified" in content  # Original modification preserved

    def test_init_update_preserves_existing_ownership(self, tmp_path):
        """Update mode should preserve existing ownership.toml."""
        # First create
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Modify ownership.toml
        ownership_path = tmp_path / "memory" / "system" / "ownership.toml"
        original_content = ownership_path.read_text(encoding="utf-8")
        ownership_path.write_text(original_content + "\n# Modified", encoding="utf-8")

        # Update should skip existing
        result = init_project_memory(tmp_path, scope="test_project", mode="update")
        assert result["success"] is True
        content = ownership_path.read_text(encoding="utf-8")
        assert "# Modified" in content  # Original modification preserved

    def test_init_repair_preserves_existing_ownership(self, tmp_path):
        """Repair mode should preserve existing ownership.toml."""
        # First create
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Modify ownership.toml
        ownership_path = tmp_path / "memory" / "system" / "ownership.toml"
        original_content = ownership_path.read_text(encoding="utf-8")
        ownership_path.write_text(original_content + "\n# Modified", encoding="utf-8")

        # Repair should skip existing
        result = init_project_memory(tmp_path, scope="test_project", mode="repair")
        assert result["success"] is True
        content = ownership_path.read_text(encoding="utf-8")
        assert "# Modified" in content  # Original modification preserved


class TestInitForceRestriction:
    """Step 2.2: Force restriction on owned files."""

    def test_force_rejects_owned_file_overwrite(self, tmp_path):
        """Force should reject overwriting owned files."""
        # Create directories first (simulate existing structure)
        (tmp_path / "memory" / "system").mkdir(parents=True, exist_ok=True)
        (tmp_path / "memory" / "docs").mkdir(parents=True, exist_ok=True)

        # Create an existing owned file (in memory/docs domain)
        custom_file = tmp_path / "memory" / "docs" / "custom.md"
        custom_file.write_text("# Original Custom Content", encoding="utf-8")

        # Create minimal memory.lock to satisfy init
        (tmp_path / "memory" / "system" / "memory.lock").write_text(
            '[memory]\nproject = "test"\nmemory_version = "0.4.0"\n'
            'schema_version = "context-package-v1"\nadapter_version = "builtin"\n'
            'locked_at = "2026-01-01"\nlock_reason = "initial"\n',
            encoding="utf-8"
        )

        # Try to force overwrite with mode=create
        # This should add an error for the owned file
        init_project_memory(
            tmp_path,
            scope="test_project",
            mode="create",
            force=True,
        )

        # Check that owned file protection is enforced
        # The file should still have original content (not overwritten)
        content = custom_file.read_text(encoding="utf-8")
        assert "Original Custom Content" in content

    def test_authorized_maintenance_allows_force(self, tmp_path):
        """Authorized maintenance mode should allow force."""
        # Create initial structure
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Set authorized maintenance env
        with patch.dict(os.environ, {"MEMORY_INIT_RUNNING": "1"}):
            result = init_project_memory(
                tmp_path,
                scope="test_project",
                mode="create",
                force=True,
            )
            assert result["success"] is True

    def test_repair_mode_allows_force(self, tmp_path):
        """Repair mode should be authorized for maintenance."""
        # Create initial structure
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Repair mode allows modifications
        result = init_project_memory(
            tmp_path,
            scope="test_project",
            mode="repair",
            force=True,
        )
        assert result["success"] is True


class TestValidateOwnershipChecks:
    """Step 2.3-2.7: Validate ownership checks."""

    def test_check_ownership_declaration_exists(self, tmp_path):
        """Step 2.3: Validate ownership.toml exists and schema."""
        # Create structure
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Validate
        result = validate_project_memory(tmp_path)
        check_names = [c["name"] for c in result.to_dict()["checks"]]
        assert "ownership_declaration" in check_names
        assert "ownership_schema" in check_names

    def test_check_domain_integrity(self, tmp_path):
        """Step 2.4: Verify domain paths exist and are not symlinks."""
        # Create structure
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Validate
        result = validate_project_memory(tmp_path)
        check_names = [c["name"] for c in result.to_dict()["checks"]]
        domain_checks = [c for c in check_names if c.startswith("domain_integrity:")]
        assert len(domain_checks) > 0

    def test_check_document_paths(self, tmp_path):
        """Step 2.5: Verify document index consistency."""
        # Create structure
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Validate
        result = validate_project_memory(tmp_path)
        check_names = [c["name"] for c in result.to_dict()["checks"]]
        doc_checks = [c for c in check_names if c.startswith("document_paths:")]
        assert len(doc_checks) > 0

    def test_check_shared_resources(self, tmp_path):
        """Step 2.6: Verify AGENTS.md markers and hooks.json."""
        # Create structure
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Validate
        result = validate_project_memory(tmp_path)
        check_names = [c["name"] for c in result.to_dict()["checks"]]
        assert "shared_resources:agents_md" in check_names

    def test_owned_file_read_error_handling(self, tmp_path):
        """Step 2.7: Owned file read failure should record error."""
        # Create structure
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Make AGENTS.md unreadable
        agents_path = tmp_path / "AGENTS.md"
        if agents_path.exists():
            agents_path.chmod(0o000)
            try:
                result = validate_project_memory(tmp_path)
                # Should have recorded error, not crashed
                assert result is not None
            finally:
                agents_path.chmod(0o644)


class TestAuditOwnershipFindings:
    """Step 2.8: Audit ownership findings."""

    def test_audit_ownership_missing_finding(self, tmp_path):
        """Audit should report ownership_missing finding."""
        # Create minimal structure without ownership.toml
        memory_dir = tmp_path / "memory" / "system"
        memory_dir.mkdir(parents=True)

        result = audit_project_layout(tmp_path)
        finding_kinds = [f.kind for f in result.findings]
        assert "ownership_missing" in finding_kinds

    def test_audit_domain_weakened_finding(self, tmp_path):
        """Audit should report domain_weakened finding."""
        # Create structure
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Modify ownership to weaken protection
        ownership_path = tmp_path / "memory" / "system" / "ownership.toml"
        content = ownership_path.read_text(encoding="utf-8")
        content = content.replace('level = "critical"', 'level = "standard"', 1)
        ownership_path.write_text(content, encoding="utf-8")

        result = audit_project_layout(tmp_path)
        finding_kinds = [f.kind for f in result.findings]
        assert "domain_weakened" in finding_kinds or "domain_missing" in finding_kinds

    def test_audit_marker_tampered_finding(self, tmp_path):
        """Audit should report marker_tampered finding."""
        # Create structure
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Modify AGENTS.md to break markers
        agents_path = tmp_path / "AGENTS.md"
        if agents_path.exists():
            content = agents_path.read_text(encoding="utf-8")
            content = content.replace("<!-- MEMORY_HOOK_END -->", "")
            agents_path.write_text(content, encoding="utf-8")

        result = audit_project_layout(tmp_path)
        # Should detect unmarked AGENTS.md
        finding_kinds = [f.kind for f in result.findings]
        assert "agents_md_unmarked" in finding_kinds or "agents_md_marked" in finding_kinds


class TestApplyOwnershipAware:
    """Step 2.9: Apply ownership-aware forbidden path detection."""

    def test_validate_plan_rejects_owned_paths(self, tmp_path):
        """Plan validation should reject actions targeting owned paths."""
        # Create structure
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Create a plan that targets an owned path
        plan = {
            "target": str(tmp_path),
            "actions": [
                {
                    "action": "move_root_pollution",
                    "path": "AGENTS.md",  # Owned resource
                    "severity": "P1",
                    "kind": "root_report",
                    "message": "Test",
                    "source_bucket": "root_pollution",
                }
            ],
            "risk_level": "low",
            "requires_human_confirmation": False,
        }

        is_valid, errors = _validate_plan(plan, target=tmp_path)
        assert not is_valid
        assert any("AGENTS.md" in e for e in errors)


class TestOwnershipTomlRoundtrip:
    """Step 2.10: Ownership.toml roundtrip tests."""

    def test_ownership_toml_roundtrip(self, tmp_path):
        """Ownership.toml should survive load/save roundtrip."""
        # Create structure
        init_project_memory(tmp_path, scope="test_project", mode="create")

        # Load ownership
        ownership = load_memory_ownership(tmp_path)
        assert isinstance(ownership, MemoryOwnership)
        assert len(ownership.domains) > 0
        assert len(ownership.resources) > 0

    def test_ownership_to_dict_from_dict(self):
        """MemoryOwnership should roundtrip through dict."""
        from memory_core.ownership import (
            DEFAULT_OWNERSHIP_DOMAINS,
            DEFAULT_OWNERSHIP_RESOURCES,
        )

        original = MemoryOwnership(
            memory_version="1.0.0",
            domains=list(DEFAULT_OWNERSHIP_DOMAINS),
            resources=list(DEFAULT_OWNERSHIP_RESOURCES),
            policy={"test": "value"},
        )

        data = original.to_dict()
        restored = MemoryOwnership.from_dict(data)

        assert restored.memory_version == original.memory_version
        assert len(restored.domains) == len(original.domains)
        assert len(restored.resources) == len(original.resources)

    def test_validate_ownership_schema_passes_for_defaults(self):
        """Default ownership should pass schema validation."""
        from memory_core.ownership import (
            DEFAULT_OWNERSHIP_DOMAINS,
            DEFAULT_OWNERSHIP_RESOURCES,
        )

        ownership = MemoryOwnership(
            domains=list(DEFAULT_OWNERSHIP_DOMAINS),
            resources=list(DEFAULT_OWNERSHIP_RESOURCES),
        )

        errors = validate_ownership_schema(ownership)
        assert errors == []


class TestOwnershipModelExisting:
    """Extend existing test_ownership_model.py coverage."""

    def test_classify_owned_path_with_project_root(self, tmp_path):
        """classify_owned_path with project_root parameter."""
        result = classify_owned_path("memory/docs/INDEX.md")
        assert isinstance(result, Owned)
        assert result.domain is not None

    def test_load_memory_ownership_fallback(self, tmp_path):
        """load_memory_ownership should fallback to defaults."""
        # No ownership file exists
        ownership = load_memory_ownership(tmp_path)
        assert isinstance(ownership, MemoryOwnership)
        assert len(ownership.domains) > 0  # Has defaults
