"""Tests for evidence_ref_validator module."""
from __future__ import annotations

from pathlib import Path

from memory_core.tools.evidence_ref_validator import (
    extract_section_bullets,
    validate_evidence_refs_on_disk,
)

# ---------------------------------------------------------------------------
# extract_section_bullets
# ---------------------------------------------------------------------------

class TestExtractSectionBullets:
    def test_extracts_evidence_refs(self):
        text = """\
## Truth Basis

### Source Refs
- `INDEX.md`

### Authority Refs
- `project-map/INDEX.md`

### Evidence Refs
- `tools/memory_hook_gateway.py`
- `tools/validate_memory_system.py`

### Conflict Status
- resolved
"""
        result = extract_section_bullets(text, "### Evidence Refs")
        assert result == ["tools/memory_hook_gateway.py", "tools/validate_memory_system.py"]

    def test_empty_section(self):
        text = """\
### Evidence Refs

### Conflict Status
- resolved
"""
        result = extract_section_bullets(text, "### Evidence Refs")
        assert result == []

    def test_no_section(self):
        text = "## No Evidence Refs Here\n"
        result = extract_section_bullets(text, "### Evidence Refs")
        assert result == []

    def test_strips_backticks(self):
        text = "### Evidence Refs\n- `path/to/file.py`\n"
        result = extract_section_bullets(text, "### Evidence Refs")
        assert result == ["path/to/file.py"]


# ---------------------------------------------------------------------------
# validate_evidence_refs_on_disk
# ---------------------------------------------------------------------------

class TestValidateEvidenceRefsOnDisk:
    def test_all_refs_exist(self, tmp_path: Path):
        # Create KB file with valid refs
        kb_dir = tmp_path / "memory" / "kb" / "global"
        kb_dir.mkdir(parents=True)

        # Create referenced files
        (tmp_path / "tools").mkdir()
        (tmp_path / "tools" / "gateway.py").write_text("# ok")

        kb_file = kb_dir / "truth-model.md"
        kb_file.write_text(
            "### Evidence Refs\n"
            "- `tools/gateway.py`\n"
        )

        errors = validate_evidence_refs_on_disk(tmp_path)
        assert errors == []

    def test_missing_ref_detected(self, tmp_path: Path):
        kb_dir = tmp_path / "memory" / "kb" / "global"
        kb_dir.mkdir(parents=True)

        kb_file = kb_dir / "truth-model.md"
        kb_file.write_text(
            "### Evidence Refs\n"
            "- `tools/nonexistent.py`\n"
            "- `tools/also_missing.py`\n"
        )

        errors = validate_evidence_refs_on_disk(tmp_path)
        assert len(errors) == 1
        assert errors[0].kb_file.endswith("truth-model.md")
        assert "tools/nonexistent.py" in errors[0].missing_refs
        assert "tools/also_missing.py" in errors[0].missing_refs

    def test_url_refs_skipped(self, tmp_path: Path):
        kb_dir = tmp_path / "memory" / "kb" / "global"
        kb_dir.mkdir(parents=True)

        kb_file = kb_dir / "test.md"
        kb_file.write_text(
            "### Evidence Refs\n"
            "- https://example.com/doc\n"
            "- http://example.com/other\n"
        )

        errors = validate_evidence_refs_on_disk(tmp_path)
        assert errors == []

    def test_glob_refs_skipped(self, tmp_path: Path):
        kb_dir = tmp_path / "memory" / "kb" / "global"
        kb_dir.mkdir(parents=True)

        kb_file = kb_dir / "test.md"
        kb_file.write_text(
            "### Evidence Refs\n"
            "- `tools/*.py`\n"
        )

        errors = validate_evidence_refs_on_disk(tmp_path)
        assert errors == []

    def test_no_kb_dir(self, tmp_path: Path):
        errors = validate_evidence_refs_on_disk(tmp_path)
        assert errors == []

    def test_file_without_evidence_refs_section(self, tmp_path: Path):
        kb_dir = tmp_path / "memory" / "kb" / "global"
        kb_dir.mkdir(parents=True)

        kb_file = kb_dir / "plain.md"
        kb_file.write_text("# Just a plain file\n")

        errors = validate_evidence_refs_on_disk(tmp_path)
        assert errors == []

    def test_mixed_valid_and_invalid(self, tmp_path: Path):
        kb_dir = tmp_path / "memory" / "kb" / "global"
        kb_dir.mkdir(parents=True)

        (tmp_path / "tools").mkdir()
        (tmp_path / "tools" / "exists.py").write_text("# ok")

        kb_file = kb_dir / "test.md"
        kb_file.write_text(
            "### Evidence Refs\n"
            "- `tools/exists.py`\n"
            "- `tools/missing.py`\n"
        )

        errors = validate_evidence_refs_on_disk(tmp_path)
        assert len(errors) == 1
        assert errors[0].missing_refs == ["tools/missing.py"]

    def test_dot_memory_kb_dir_scanned(self, tmp_path: Path):
        kb_dir = tmp_path / "memory" / "system" / "kb" / "projects"
        kb_dir.mkdir(parents=True)

        kb_file = kb_dir / "project.md"
        kb_file.write_text(
            "### Evidence Refs\n"
            "- `nonexistent/file.py`\n"
        )

        errors = validate_evidence_refs_on_disk(tmp_path)
        assert len(errors) == 1


# ---------------------------------------------------------------------------
# New test cases for extract_section_bullets bug fix
# ---------------------------------------------------------------------------

class TestExtractSectionBulletsBugFix:
    """Tests for VAL-BUG-001 and VAL-BUG-002: sub-heading termination bug."""

    def test_sub_heading_in_section(self):
        """VAL-BUG-001: Sub-heading does not terminate section parsing."""
        text = """\
### Evidence Refs
- `tools/memory_hook_gateway.py`
- `tools/validate_memory_system.py`

#### Note
- `docs/architecture.md`
- `docs/design.md`

### Next Section
- should not be included
"""
        result = extract_section_bullets(text, "### Evidence Refs")
        assert result == [
            "tools/memory_hook_gateway.py",
            "tools/validate_memory_system.py",
            "docs/architecture.md",
            "docs/design.md",
        ]

    def test_different_heading_level(self):
        """VAL-BUG-002: H2 target heading with H3 sub-sections."""
        text = """\
## Evidence Refs
- `tools/core.py`
- `tools/utils.py`

### Sub-section
- `docs/guide.md`

## Another H2 Section
- should not be included
"""
        result = extract_section_bullets(text, "## Evidence Refs")
        assert result == ["tools/core.py", "tools/utils.py", "docs/guide.md"]


# ---------------------------------------------------------------------------
# New test cases for validate_evidence_refs_on_disk coverage
# ---------------------------------------------------------------------------

class TestValidateEvidenceRefsCoverage:
    """Tests for VAL-TEST-001 through VAL-TEST-005."""

    def test_path_traversal_skipped(self, tmp_path: Path):
        """VAL-TEST-001: Path traversal refs are silently skipped."""
        kb_dir = tmp_path / "memory" / "kb" / "global"
        kb_dir.mkdir(parents=True)

        kb_file = kb_dir / "test.md"
        kb_file.write_text(
            "### Evidence Refs\n"
            "- `../../etc/passwd`\n"
            "- `/etc/shadow`\n"
        )

        errors = validate_evidence_refs_on_disk(tmp_path)
        assert errors == []

    def test_custom_kb_dirs_parameter(self, tmp_path: Path):
        """VAL-TEST-002: Custom kb_dirs parameter works correctly."""
        # Create default kb dir (should be ignored)
        default_kb = tmp_path / "memory" / "kb" / "global"
        default_kb.mkdir(parents=True)
        (default_kb / "default.md").write_text(
            "### Evidence Refs\n- `nonexistent/default.py`\n"
        )

        # Create custom kb dir
        custom_kb = tmp_path / "custom" / "kb"
        custom_kb.mkdir(parents=True)
        (tmp_path / "tools").mkdir()
        (tmp_path / "tools" / "exists.py").write_text("# ok")
        (custom_kb / "custom.md").write_text(
            "### Evidence Refs\n- `tools/exists.py`\n"
        )

        # Only scan custom_kb, not default dirs
        errors = validate_evidence_refs_on_disk(tmp_path, kb_dirs=[custom_kb])
        assert errors == []

    def test_section_at_end_of_file(self, tmp_path: Path):
        """VAL-TEST-003: Evidence Refs section at EOF parsed correctly."""
        kb_dir = tmp_path / "memory" / "kb" / "global"
        kb_dir.mkdir(parents=True)

        (tmp_path / "tools").mkdir()
        (tmp_path / "tools" / "exists.py").write_text("# ok")

        # Section is at EOF with no following heading
        kb_file = kb_dir / "test.md"
        kb_file.write_text(
            "## Overview\n"
            "Some content here.\n\n"
            "### Evidence Refs\n"
            "- `tools/exists.py`\n"
        )

        errors = validate_evidence_refs_on_disk(tmp_path)
        assert errors == []

    def test_wildcard_prefix_refs_skipped(self, tmp_path: Path):
        """VAL-TEST-004: Wildcard and question-mark prefix refs skipped."""
        kb_dir = tmp_path / "memory" / "kb" / "global"
        kb_dir.mkdir(parents=True)

        kb_file = kb_dir / "test.md"
        kb_file.write_text(
            "### Evidence Refs\n"
            "- `*.py`\n"
            "- `**/config.py`\n"
            "- `??.py`\n"
        )

        errors = validate_evidence_refs_on_disk(tmp_path)
        assert errors == []

    def test_non_utf8_file_skipped(self, tmp_path: Path):
        """VAL-TEST-005: Non-UTF-8 files silently skipped."""
        kb_dir = tmp_path / "memory" / "kb" / "global"
        kb_dir.mkdir(parents=True)

        # Write binary content
        kb_file = kb_dir / "binary.md"
        kb_file.write_bytes(b"\x80\x81\x82\xff\xfe### Evidence Refs\n- `tools/gateway.py`\n")

        errors = validate_evidence_refs_on_disk(tmp_path)
        assert errors == []
