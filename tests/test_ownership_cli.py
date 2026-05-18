"""Tests for ownership_cli.py (M6 step 6.1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_core.ownership import (
    MemoryOwnership,
    ProtectionLevel,
)
from memory_core.tools.ownership_cli import (
    _build_default_ownership,
    _diff_ownership,
    _format_protection_level,
    _ownership_file_path,
    _render_ownership,
    _write_ownership_toml,
    cmd_apply_update,
    cmd_plan_update,
    cmd_show,
    cmd_validate,
    main,
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Create a temporary project root with .memory/ directory."""
    mem = tmp_path / ".memory"
    mem.mkdir()
    return tmp_path


@pytest.fixture
def project_with_ownership(project_root: Path) -> Path:
    """Create a project root with a default ownership.toml."""
    ownership = _build_default_ownership()
    _write_ownership_toml(project_root, ownership)
    return project_root


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_ownership_file_path(self, project_root: Path) -> None:
        result = _ownership_file_path(project_root)
        assert result == project_root / ".memory" / "ownership.toml"

    def test_format_protection_level(self) -> None:
        assert "CRITICAL" in _format_protection_level(ProtectionLevel.CRITICAL)
        assert "STANDARD" in _format_protection_level(ProtectionLevel.STANDARD)
        assert "RECOMMENDED" in _format_protection_level(ProtectionLevel.RECOMMENDED)

    def test_render_ownership(self) -> None:
        ownership = _build_default_ownership()
        text = _render_ownership(ownership)
        assert "Ownership Configuration" in text
        assert "memory_docs" in text
        assert "agents_md" in text

    def test_build_default_ownership(self) -> None:
        ownership = _build_default_ownership()
        assert len(ownership.domains) > 0
        assert len(ownership.resources) > 0
        assert ownership.memory_version != ""


# ---------------------------------------------------------------------------
# show command tests
# ---------------------------------------------------------------------------

class TestCmdShow:
    def test_show_defaults(self, project_root: Path) -> None:
        """Show with no ownership.toml should display defaults."""
        rc = cmd_show(project_root)
        assert rc == 0

    def test_show_with_ownership(self, project_with_ownership: Path) -> None:
        rc = cmd_show(project_with_ownership)
        assert rc == 0

    def test_show_json(self, project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd_show(project_root, json_output=True)
        assert rc == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "domains" in data
        assert "resources" in data

    def test_show_nonexistent_root(self, tmp_path: Path) -> None:
        """Should fail gracefully if project root doesn't exist."""
        nonexistent = tmp_path / "nope"
        # cmd_show doesn't validate root exists, but main does
        rc = main(["show", "--project-root", str(nonexistent)])
        assert rc == 2


# ---------------------------------------------------------------------------
# validate command tests
# ---------------------------------------------------------------------------

class TestCmdValidate:
    def test_validate_defaults(self, project_root: Path) -> None:
        """Default ownership should validate clean."""
        rc = cmd_validate(project_root)
        assert rc == 0

    def test_validate_with_file(self, project_with_ownership: Path) -> None:
        rc = cmd_validate(project_with_ownership)
        assert rc == 0

    def test_validate_json(self, project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd_validate(project_root, json_output=True)
        assert rc == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data["valid"] is True

    def test_validate_no_file_gives_warning(
        self, project_root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = cmd_validate(project_root, json_output=True)
        assert rc == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert any("not found" in w for w in data["warnings"])


# ---------------------------------------------------------------------------
# plan-update command tests
# ---------------------------------------------------------------------------

class TestCmdPlanUpdate:
    def test_plan_no_changes(self, project_with_ownership: Path) -> None:
        """Plan against defaults when file has defaults should show no changes."""
        rc = cmd_plan_update(project_with_ownership, use_defaults=True)
        assert rc == 0

    def test_plan_json(self, project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd_plan_update(project_root, json_output=True, use_defaults=True)
        assert rc == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "has_changes" in data


class TestDiffOwnership:
    def test_diff_identical(self) -> None:
        ownership = _build_default_ownership()
        plan = _diff_ownership(ownership, ownership)
        assert plan["has_changes"] is False

    def test_diff_domain_added(self) -> None:
        current = MemoryOwnership(domains=[], resources=[])
        proposed = _build_default_ownership()
        plan = _diff_ownership(current, proposed)
        assert plan["has_changes"] is True
        assert len(plan["domains_added"]) > 0

    def test_diff_domain_removed(self) -> None:
        current = _build_default_ownership()
        proposed = MemoryOwnership(domains=[], resources=[])
        plan = _diff_ownership(current, proposed)
        assert plan["has_changes"] is True
        assert len(plan["domains_removed"]) > 0

    def test_diff_schema_version_change(self) -> None:
        current = MemoryOwnership(schema_version="v1")
        proposed = MemoryOwnership(schema_version="v2")
        plan = _diff_ownership(current, proposed)
        assert plan["has_changes"] is True
        assert plan["schema_version_change"] is not None


# ---------------------------------------------------------------------------
# apply-update command tests
# ---------------------------------------------------------------------------

class TestCmdApplyUpdate:
    def test_apply_no_changes(self, project_with_ownership: Path) -> None:
        rc = cmd_apply_update(project_with_ownership, yes=True, use_defaults=True)
        assert rc == 0

    def test_apply_generates_file(self, project_root: Path) -> None:
        """Applying to a bare project should create ownership.toml."""
        rc = cmd_apply_update(project_root, yes=True, use_defaults=True)
        assert rc == 0
        ownership_path = project_root / ".memory" / "ownership.toml"
        assert ownership_path.exists()

    def test_apply_json(self, project_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd_apply_update(
            project_root, yes=True, json_output=True, use_defaults=True
        )
        assert rc == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data.get("applied") is True


# ---------------------------------------------------------------------------
# write_ownership_toml tests
# ---------------------------------------------------------------------------

class TestWriteOwnershipToml:
    def test_writes_file(self, project_root: Path) -> None:
        ownership = _build_default_ownership()
        path = _write_ownership_toml(project_root, ownership)
        assert path.exists()
        content = path.read_text()
        assert "ownership.toml" in content
        assert "domains" in content
        assert "resources" in content

    def test_written_toml_is_loadable(self, project_root: Path) -> None:
        from memory_core.ownership import load_memory_ownership

        ownership = _build_default_ownership()
        _write_ownership_toml(project_root, ownership)
        loaded = load_memory_ownership(project_root)
        assert len(loaded.domains) == len(ownership.domains)
        assert len(loaded.resources) == len(ownership.resources)


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestCLI:
    def test_main_show(self, project_root: Path) -> None:
        rc = main(["show", "--project-root", str(project_root)])
        assert rc == 0

    def test_main_validate(self, project_root: Path) -> None:
        rc = main(["validate", "--project-root", str(project_root)])
        assert rc == 0

    def test_main_plan_update(self, project_root: Path) -> None:
        rc = main(["plan-update", "--project-root", str(project_root)])
        assert rc == 0

    def test_main_apply_update_yes(self, project_root: Path) -> None:
        rc = main(["apply-update", "--project-root", str(project_root), "--yes"])
        assert rc == 0

    def test_main_apply_update_json(self, project_root: Path) -> None:
        rc = main(
            ["apply-update", "--project-root", str(project_root), "--yes", "--json"]
        )
        assert rc == 0

    def test_main_no_command(self) -> None:
        with pytest.raises(SystemExit):
            main([])
