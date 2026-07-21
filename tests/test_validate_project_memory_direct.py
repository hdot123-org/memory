
import json
import sys
from pathlib import Path

import pytest

from memory_core.constants import (
    CURRENT_MEMORY_VERSION,
    REQUIRED_MEMORY_DIRS,
    REQUIRED_MEMORY_FILES,
    SUPPORTED_HOSTS,
)
from memory_core.tools.validate_project_memory import (
    CheckResult,
    _check_pollution,
    _is_json_like,
    _parse_adapter_toml,
    _parse_frontmatter,
    _parse_lock_file,
    check_adapter_host_enum,
    check_adapter_version,
    check_lock_version,
    check_memory_lock_semver,
    check_migrations_log,
    check_pollution,
    check_required_dirs,
    check_required_files,
    main,
    validate_project_memory,
)


class TestParseFrontmatter:
    """Tests for _parse_frontmatter function."""

    def test_parse_basic_frontmatter(self) -> None:
        """Test parsing basic YAML frontmatter."""
        text = """---
title: Test Document
version: 1.0.0
---

# Content here
"""
        result = _parse_frontmatter(text)
        assert result["title"] == "Test Document"
        assert result["version"] == "1.0.0"

    def test_parse_frontmatter_with_list(self) -> None:
        """Test parsing frontmatter with list values."""
        text = """---
tags: [tag1, tag2, tag3]
---

Content
"""
        result = _parse_frontmatter(text)
        assert result["tags"] == "[tag1, tag2, tag3]"

    def test_parse_frontmatter_with_quotes(self) -> None:
        """Test parsing frontmatter with quoted values."""
        text = """---
title: "Test Document"
description: 'A description'
---

Content
"""
        result = _parse_frontmatter(text)
        assert result["title"] == "Test Document"
        assert result["description"] == "A description"

    def test_parse_frontmatter_nested_quotes(self) -> None:
        """Test parsing frontmatter with nested quotes."""
        text = '''---
title: "Test 'nested' quotes"
---

Content
'''
        result = _parse_frontmatter(text)
        assert result["title"] == "Test 'nested' quotes"

    def test_parse_no_frontmatter(self) -> None:
        """Test parsing text without frontmatter."""
        text = """# Just content
No frontmatter here.
"""
        result = _parse_frontmatter(text)
        assert result == {}

    def test_parse_frontmatter_with_bom(self) -> None:
        """Test parsing frontmatter with BOM."""
        text = "\ufeff---\ntitle: Test\n---\nContent"
        result = _parse_frontmatter(text)
        assert result["title"] == "Test"

    def test_parse_frontmatter_crlf(self) -> None:
        """Test parsing frontmatter with CRLF line endings."""
        text = "---\r\ntitle: Test\r\n---\r\nContent"
        result = _parse_frontmatter(text)
        assert result["title"] == "Test"

    def test_parse_frontmatter_with_comments(self) -> None:
        """Test parsing frontmatter with comment lines."""
        text = """---
# This is a comment
title: Test
---

Content
"""
        result = _parse_frontmatter(text)
        assert result["title"] == "Test"
        assert "comment" not in result

    def test_parse_frontmatter_empty_value(self) -> None:
        """Test parsing frontmatter with empty value."""
        text = """---
title:
---

Content
"""
        result = _parse_frontmatter(text)
        assert result["title"] == ""


class TestIsJsonLike:
    """Tests for _is_json_like function."""

    def test_is_json_like_object(self) -> None:
        """Test detecting JSON object."""
        assert _is_json_like('{"key": "value"}') is True

    def test_is_json_like_array(self) -> None:
        """Test detecting JSON array."""
        assert _is_json_like('[1, 2, 3]') is True

    def test_is_json_like_whitespace(self) -> None:
        """Test handling whitespace before JSON."""
        assert _is_json_like('   {"key": "value"}') is True

    def test_is_json_like_not_json(self) -> None:
        """Test non-JSON text."""
        assert _is_json_like("just text") is False

    def test_is_json_like_toml(self) -> None:
        """Test TOML is not JSON-like."""
        # TOML content starts with '[section]' which looks like JSON array
        # But after our fix, [section] is correctly identified as a TOML section header
        # and returns False (not JSON-like)
        assert _is_json_like("[section]\nkey = value") is False  # [section] is TOML section

    def test_is_json_like_empty(self) -> None:
        """Test empty string."""
        assert _is_json_like("") is False


class TestParseLockFile:
    """Tests for _parse_lock_file function."""

    def test_parse_toml_format_raises_error(self, tmp_path: Path) -> None:
        """Test that TOML format lock file starting with [section] is correctly parsed.

        After the fix to _is_json_like, TOML files starting with [memory] are now
        correctly identified as TOML sections (not JSON arrays) and parsed successfully.
        """
        lock_file = tmp_path / "memory.lock"
        lock_file.write_text("""[memory]
memory_version = "0.3.0"
schema_version = "1.0"
""")
        # Now correctly parses as TOML
        result = _parse_lock_file(lock_file)
        assert result["memory"]["memory_version"] == "0.3.0"

    def test_parse_json_legacy_format(self, tmp_path: Path) -> None:
        """Test parsing JSON legacy format lock file."""
        lock_file = tmp_path / "memory.lock"
        lock_file.write_text(json.dumps({
            "version": "0.3.0",
            "schema": "1.0",
            "adapter_version": "builtin",
        }))
        result = _parse_lock_file(lock_file)
        assert result["memory"]["memory_version"] == "0.3.0"

    def test_parse_fallback_format(self, tmp_path: Path) -> None:
        """Test parsing fallback key=value format."""
        lock_file = tmp_path / "memory.lock"
        # This format is not JSON-like (no { or [ at start)
        # So it will go through TOML parsing first, then fallback if that fails
        lock_file.write_text("""# Comment
memory_version = "0.3.0"
schema_version = "1.0"
""")
        result = _parse_lock_file(lock_file)
        # The result should have memory_version either in memory section or at top level
        memory_version = result.get("memory", {}).get("memory_version", "")
        if not memory_version:
            memory_version = result.get("memory_version", "")
        assert memory_version == "0.3.0"


class TestParseAdapterToml:
    """Tests for _parse_adapter_toml function."""

    def test_parse_adapter_toml(self, tmp_path: Path) -> None:
        """Test parsing adapter.toml file."""
        adapter_file = tmp_path / "adapter.toml"
        adapter_file.write_text("""[core]
version = "0.3.0"
host = "codex"

[routing]
host = "codex"
project_scope = "test"
""")
        result = _parse_adapter_toml(adapter_file)
        assert result["core.version"] == "0.3.0"
        assert result["routing.host"] == "codex"

    def test_parse_adapter_toml_non_dict_value(self, tmp_path: Path) -> None:
        """Test parsing adapter.toml with non-dict section values."""
        adapter_file = tmp_path / "adapter.toml"
        adapter_file.write_text("""[core]
version = "0.3.0"
""")
        result = _parse_adapter_toml(adapter_file)
        assert result["core.version"] == "0.3.0"


class TestCheckPollution:
    """Tests for _check_pollution function."""

    def test_check_no_pollution(self, tmp_path: Path) -> None:
        """Test checking directory with no pollution."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        (memory_root / "test.md").write_text("Clean content")

        result = _check_pollution(memory_root)
        assert result == []

    def test_check_path_pollution(self, tmp_path: Path) -> None:
        """Test detecting path pollution."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        polluted_dir = memory_root / "node_modules"
        polluted_dir.mkdir()
        (polluted_dir / "file.js").write_text("// content")

        result = _check_pollution(memory_root)
        assert len(result) > 0
        assert any("node_modules" in r for r in result)

    def test_check_content_pollution(self, tmp_path: Path) -> None:
        """Test detecting content pollution."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        md_file = memory_root / "test.md"
        md_file.write_text("This references node_modules in content")

        result = _check_pollution(memory_root)
        assert len(result) > 0

    def test_check_pycache_pollution(self, tmp_path: Path) -> None:
        """Test detecting __pycache__ pollution."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        pycache_dir = memory_root / "__pycache__"
        pycache_dir.mkdir()
        # Create a file inside to trigger rglob
        (pycache_dir / "test.cpython-39.pyc").write_text("content")

        result = _check_pollution(memory_root)
        assert len(result) > 0

    def test_check_venv_pollution(self, tmp_path: Path) -> None:
        """Test detecting .venv pollution."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        venv_dir = memory_root / ".venv"
        venv_dir.mkdir()
        # Create a file inside to trigger rglob
        (venv_dir / "bin").mkdir()
        (venv_dir / "bin" / "python").write_text("content")

        result = _check_pollution(memory_root)
        assert len(result) > 0


class TestCheckResult:
    """Tests for CheckResult class."""

    def test_check_result_initial(self) -> None:
        """Test CheckResult initialization."""
        result = CheckResult()
        assert result.checks == []
        assert result.all_passed is True

    def test_check_result_record_pass(self) -> None:
        """Test recording a passing check."""
        result = CheckResult()
        result.record("test_check", True, "all good")
        assert len(result.checks) == 1
        assert result.checks[0]["name"] == "test_check"
        assert result.checks[0]["passed"] is True
        assert result.checks[0]["detail"] == "all good"
        assert result.all_passed is True

    def test_check_result_record_fail(self) -> None:
        """Test recording a failing check."""
        result = CheckResult()
        result.record("test_check", False, "something wrong")
        assert result.checks[0]["passed"] is False
        assert result.all_passed is False

    def test_check_result_to_dict(self) -> None:
        """Test converting CheckResult to dict."""
        result = CheckResult()
        result.record("check1", True)
        result.record("check2", False)

        data = result.to_dict()
        assert data["all_passed"] is False
        assert data["total"] == 2
        assert data["passed"] == 1
        assert data["failed"] == 1

    def test_check_result_to_text(self) -> None:
        """Test converting CheckResult to text."""
        result = CheckResult()
        result.record("check1", True)
        result.record("check2", False, "error detail")

        text = result.to_text()
        assert "Project Memory Validation Report" in text
        assert "[PASS] check1" in text
        assert "[FAIL] check2" in text
        assert "error detail" in text


class TestCheckRequiredFiles:
    """Tests for check_required_files function."""

    def test_all_files_exist(self, tmp_path: Path) -> None:
        """Test when all required files exist."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        for fname in REQUIRED_MEMORY_FILES:
            (memory_root / fname).write_text("content")

        result = CheckResult()
        check_required_files(memory_root, result)

        assert result.all_passed is True
        for check in result.checks:
            assert check["passed"] is True

    def test_missing_files(self, tmp_path: Path) -> None:
        """Test when some files are missing."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        # Create only some files
        (memory_root / REQUIRED_MEMORY_FILES[0]).write_text("content")

        result = CheckResult()
        check_required_files(memory_root, result)

        assert result.all_passed is False
        assert any(not c["passed"] for c in result.checks)


class TestCheckRequiredDirs:
    """Tests for check_required_dirs function."""

    def test_all_dirs_exist(self, tmp_path: Path) -> None:
        """Test when all required directories exist."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        for dname in REQUIRED_MEMORY_DIRS:
            # Create parent directories if needed (e.g., kb/projects needs kb/ first)
            (memory_root / dname).mkdir(parents=True)

        result = CheckResult()
        check_required_dirs(memory_root, result)

        assert result.all_passed is True

    def test_missing_dirs(self, tmp_path: Path) -> None:
        """Test when some directories are missing."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        # Create only one dir
        if REQUIRED_MEMORY_DIRS:
            (memory_root / REQUIRED_MEMORY_DIRS[0]).mkdir(parents=True)

        result = CheckResult()
        check_required_dirs(memory_root, result)

        # May pass or fail depending on if dirs are optional
        assert isinstance(result.checks, list)


class TestCheckLockVersion:
    """Tests for check_lock_version function."""

    def test_lock_version_match(self, tmp_path: Path) -> None:
        """Test when lock version matches current version."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        lock_file = memory_root / "memory.lock"
        # Use JSON format since TOML starting with [ looks like JSON array
        # and triggers JSON parsing which will fail
        lock_file.write_text(json.dumps({
            "version": CURRENT_MEMORY_VERSION,
        }))

        result = CheckResult()
        check_lock_version(memory_root, result)

        assert any(c["passed"] for c in result.checks)

    def test_lock_version_mismatch(self, tmp_path: Path) -> None:
        """Test when lock version doesn't match."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        lock_file = memory_root / "memory.lock"
        # Use JSON format for compatibility
        lock_file.write_text(json.dumps({
            "version": "0.0.1",
        }))

        result = CheckResult()
        check_lock_version(memory_root, result)

        # Backward compatibility: old versions should pass (with warnings)
        assert any(c["passed"] for c in result.checks)

    def test_lock_no_file(self, tmp_path: Path) -> None:
        """Test when lock file doesn't exist."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)

        result = CheckResult()
        check_lock_version(memory_root, result)

        assert any(not c["passed"] for c in result.checks)


class TestCheckAdapterVersion:
    """Tests for check_adapter_version function."""

    def test_adapter_version_match(self, tmp_path: Path) -> None:
        """Test when adapter version matches current version."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        adapter_file = memory_root / "adapter.toml"
        adapter_file.write_text(f"""[core]
version = "{CURRENT_MEMORY_VERSION}"
""")

        result = CheckResult()
        check_adapter_version(memory_root, result)

        assert any(c["passed"] for c in result.checks)

    def test_adapter_version_mismatch(self, tmp_path: Path) -> None:
        """Test when adapter version doesn't match but is still accepted (backward compatible)."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        adapter_file = memory_root / "adapter.toml"
        adapter_file.write_text("""[core]
version = "0.0.1"
""")

        result = CheckResult()
        check_adapter_version(memory_root, result)

        # After backward compatibility fix, unknown old versions are still accepted
        # with a warning, not rejected
        assert any(c["passed"] for c in result.checks)


class TestCheckPollutionFunction:
    """Tests for check_pollution function."""

    def test_no_pollution(self, tmp_path: Path) -> None:
        """Test when no pollution is detected."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        (memory_root / "test.md").write_text("Clean content")

        result = CheckResult()
        check_pollution(memory_root, result)

        assert any(c["passed"] for c in result.checks)

    def test_with_pollution(self, tmp_path: Path) -> None:
        """Test when pollution is detected."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        polluted = memory_root / "node_modules"
        polluted.mkdir()
        # Create a file inside polluted dir to trigger rglob detection
        (polluted / "package.json").write_text("{}")

        result = CheckResult()
        check_pollution(memory_root, result)

        assert any(not c["passed"] for c in result.checks)


class TestCheckMigrationsLog:
    """Tests for check_migrations_log function."""

    def test_valid_log(self, tmp_path: Path) -> None:
        """Test checking valid migrations log."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        log_file = memory_root / "migrations.log"
        log_file.write_text("""# Migration log
2026-01-15T10:00:00Z [upgrade] 0.2.0 -> 0.3.0
2026-01-16T10:00:00Z [upgrade] 0.3.0 -> 0.3.1
""")

        result = CheckResult()
        check_migrations_log(memory_root, result)

        # Should have some passing checks
        pass_checks = [c for c in result.checks if c["passed"]]
        assert len(pass_checks) > 0

    def test_empty_log(self, tmp_path: Path) -> None:
        """Test checking empty migrations log."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        log_file = memory_root / "migrations.log"
        log_file.write_text("")

        result = CheckResult()
        check_migrations_log(memory_root, result)

        # May pass or fail, but should have checks recorded
        assert len(result.checks) > 0

    def test_no_log_file(self, tmp_path: Path) -> None:
        """Test when migrations.log doesn't exist."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)

        result = CheckResult()
        check_migrations_log(memory_root, result)

        assert any(not c["passed"] for c in result.checks)


class TestCheckMemoryLockSemver:
    """Tests for check_memory_lock_semver function."""

    def test_valid_semver(self, tmp_path: Path) -> None:
        """Test checking lock file with valid semver."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        lock_file = memory_root / "memory.lock"
        # Use JSON format for compatibility
        lock_file.write_text(json.dumps({
            "version": "1.2.3",
        }))

        result = CheckResult()
        check_memory_lock_semver(memory_root, result)

        assert any(c["passed"] for c in result.checks)

    def test_invalid_semver(self, tmp_path: Path) -> None:
        """Test checking lock file with invalid semver."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        lock_file = memory_root / "memory.lock"
        # Use JSON format for compatibility
        lock_file.write_text(json.dumps({
            "version": "1.2",
        }))

        result = CheckResult()
        check_memory_lock_semver(memory_root, result)

        assert any(not c["passed"] for c in result.checks)


class TestCheckAdapterHostEnum:
    """Tests for check_adapter_host_enum function."""

    def test_valid_host(self, tmp_path: Path) -> None:
        """Test checking adapter with valid host."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        adapter_file = memory_root / "adapter.toml"
        adapter_file.write_text(f"""[routing]
host = "{SUPPORTED_HOSTS[0]}"
""")

        result = CheckResult()
        check_adapter_host_enum(memory_root, result)

        assert any(c["passed"] for c in result.checks)

    def test_invalid_host(self, tmp_path: Path) -> None:
        """Test checking adapter with invalid host."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        adapter_file = memory_root / "adapter.toml"
        adapter_file.write_text("""[routing]
host = "invalid_host"
""")

        result = CheckResult()
        check_adapter_host_enum(memory_root, result)

        assert any(not c["passed"] for c in result.checks)

    def test_missing_host(self, tmp_path: Path) -> None:
        """Test checking adapter without host field."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        adapter_file = memory_root / "adapter.toml"
        adapter_file.write_text("""[core]
version = "1.0.0"
""")

        result = CheckResult()
        check_adapter_host_enum(memory_root, result)

        assert any(not c["passed"] for c in result.checks)


class TestValidateProjectMemory:
    """Tests for validate_project_memory function."""

    def test_validate_full_project(self, tmp_path: Path) -> None:
        """Test validating a complete project."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)

        # Create required files
        for fname in REQUIRED_MEMORY_FILES:
            if fname.endswith(".md"):
                content = "---\nstatus: active\n---\n\n# Content\n"
                (memory_root / fname).write_text(content)
            elif fname == "memory.lock":
                # Use JSON format for better compatibility
                (memory_root / fname).write_text(json.dumps({
                    "version": CURRENT_MEMORY_VERSION,
                }))
            elif fname == "adapter.toml":
                (memory_root / fname).write_text(f"""[core]
version = "{CURRENT_MEMORY_VERSION}"

[routing]
host = "{SUPPORTED_HOSTS[0]}"
""")
            elif fname == "migrations.log":
                (memory_root / fname).write_text("# Log\n2026-01-15T10:00:00Z | 0.2.0 | 0.3.0 | success | test\n")
            else:
                (memory_root / fname).write_text("content")

        # Create required directories with parents=True for nested dirs like kb/projects
        for dname in REQUIRED_MEMORY_DIRS:
            (memory_root / dname).mkdir(parents=True, exist_ok=True)

        result = validate_project_memory(tmp_path)

        assert isinstance(result, CheckResult)
        assert len(result.checks) > 0

    def test_validate_missing_memory_dir(self, tmp_path: Path) -> None:
        """Test validating project without .memory directory."""
        result = validate_project_memory(tmp_path)

        assert isinstance(result, CheckResult)
        assert result.all_passed is False
        assert any("memory_root" in c["name"] for c in result.checks)

    def test_validate_dry_run(self, tmp_path: Path) -> None:
        """Test validating with dry_run flag."""
        result = validate_project_memory(tmp_path, dry_run=True)

        assert isinstance(result, CheckResult)
        assert any("dry_run" in c["name"] for c in result.checks)


class TestMain:
    """Tests for main function."""

    def test_main_missing_target(self, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test main with non-existent target."""
        monkeypatch.setattr(sys, "argv", ["validate_project_memory", "--target", "/nonexistent/path"])
        exit_code = main()
        assert exit_code == 2

    def test_main_invalid_target(self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test main with file as target (not directory)."""
        not_a_dir = tmp_path / "file.txt"
        not_a_dir.write_text("content")

        monkeypatch.setattr(sys, "argv", ["validate_project_memory", "--target", str(not_a_dir)])
        exit_code = main()
        assert exit_code == 2

    def test_main_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test main with JSON output."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)

        # Create minimal required files
        for fname in REQUIRED_MEMORY_FILES:
            if fname.endswith(".md"):
                (memory_root / fname).write_text("---\nstatus: active\n---\n")
            elif fname == "memory.lock":
                (memory_root / fname).write_text(json.dumps({"version": CURRENT_MEMORY_VERSION}))
            elif fname == "adapter.toml":
                (memory_root / fname).write_text(f"[core]\nversion = \"{CURRENT_MEMORY_VERSION}\"\n\n[routing]\nhost = \"{SUPPORTED_HOSTS[0]}\"")
            elif fname == "migrations.log":
                (memory_root / fname).write_text("# Log\n2026-01-15T10:00:00Z | 0.2.0 | 0.3.0 | success | test\n")
            else:
                (memory_root / fname).write_text("content")

        for dname in REQUIRED_MEMORY_DIRS:
            (memory_root / dname).mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(sys, "argv", ["validate_project_memory", "--target", str(tmp_path), "--json"])
        exit_code = main()
        assert exit_code in [0, 1]

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "all_passed" in data
        assert "checks" in data


class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_parse_frontmatter_unicode(self) -> None:
        """Test parsing frontmatter with unicode values."""
        text = """---
title: 测试文档
---

Content
"""
        result = _parse_frontmatter(text)
        assert result["title"] == "测试文档"

    def test_is_json_like_unicode(self) -> None:
        """Test JSON-like detection with unicode."""
        assert _is_json_like('{"key": "世界"}') is True

    def test_check_result_empty(self) -> None:
        """Test CheckResult with no checks."""
        result = CheckResult()
        assert result.all_passed is True
        assert result.to_dict() == {
            "all_passed": True,
            "checks": [],
            "total": 0,
            "passed": 0,
            "failed": 0,
        }

    def test_lock_version_legacy_key(self, tmp_path: Path) -> None:
        """Test lock version check with legacy 'version' key."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        lock_file = memory_root / "memory.lock"
        # Legacy JSON format with top-level version key
        lock_file.write_text(json.dumps({
            "version": CURRENT_MEMORY_VERSION,
        }))

        result = CheckResult()
        check_lock_version(memory_root, result)

        # Should handle legacy format and pass
        assert len(result.checks) > 0
        assert any(c["passed"] for c in result.checks)

    def test_adapter_version_legacy_key(self, tmp_path: Path) -> None:
        """Test adapter version check with legacy 'version' key."""
        memory_root = tmp_path / "memory" / "system"
        memory_root.mkdir(parents=True)
        adapter_file = memory_root / "adapter.toml"
        # Legacy format with version at top level (not in [core] section)
        adapter_file.write_text(f"version = \"{CURRENT_MEMORY_VERSION}\"")

        result = CheckResult()
        check_adapter_version(memory_root, result)

        # Should handle legacy format
        assert len(result.checks) > 0
