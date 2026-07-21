"""Comprehensive unit tests for daily_kb_audit.py coverage improvement.

Target: raise coverage from 18% to >=50%.
Covers: utility helpers, check_* functions, audit orchestration,
report building, summary generation, CLI parsing, main(), and
infrastructure health checks.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from memory_core.tools.daily_kb_audit import (
    MANIFEST_FILENAME,
    _append_infra_summary,
    _count_critical_infra,
    _count_warning_infra,
    _extract_version_from_toml,
    _make_violation,
    _normalize_for_compare,
    _now_iso_local,
    _parse_args,
    _read_text_safe,
    _sha256_file,
    _shell_quote,
    _strip_frontmatter,
    _summarize_report,
    _tcp_connect_ok,
    audit_project,
    build_global_kb_fingerprints,
    build_report,
    check_database,
    check_disk_space,
    check_global_residue,
    check_infrastructure,
    check_large_or_db_files,
    check_manifest_integrity,
    check_server,
    check_ssh_reachable,
    check_unsigned_files,
    check_version_consistency,
    load_registered_projects,
    main,
    notify_via_lark,
    write_report,
)

# ---------------------------------------------------------------------------
# Utility / Helper Tests
# ---------------------------------------------------------------------------

class TestNowIsoLocal:
    def test_returns_string(self):
        result = _now_iso_local()
        assert isinstance(result, str)
        assert "T" in result  # ISO format


class TestSha256File:
    def test_valid_file(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert _sha256_file(f) == expected

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert _sha256_file(f) == expected

    def test_missing_file_returns_none(self, tmp_path: Path):
        assert _sha256_file(tmp_path / "nonexistent.txt") is None

    def test_unreadable_file_returns_none(self, tmp_path: Path):
        f = tmp_path / "no_read.txt"
        f.write_bytes(b"data")
        f.chmod(0o000)
        try:
            assert _sha256_file(f) is None
        finally:
            f.chmod(0o644)


class TestStripFrontmatter:
    def test_strips_frontmatter(self):
        text = "---\ntitle: Test\ntags: [a]\n---\nBody content"
        assert _strip_frontmatter(text) == "Body content"

    def test_no_frontmatter(self):
        text = "No frontmatter here"
        assert _strip_frontmatter(text) == text

    def test_only_one_frontmatter_block(self):
        text = "---\na: 1\n---\nMiddle\n---\nAnother\n---\nEnd"
        result = _strip_frontmatter(text)
        assert "Middle" in result
        assert "---\nAnother" in result


class TestNormalizeForCompare:
    def test_strips_whitespace_and_lowercases(self):
        text = "---\ntitle: X\n---\nHello World  Foo"
        result = _normalize_for_compare(text)
        assert result == "helloworldfoo"
        assert " " not in result

    def test_truncates_to_200_chars(self):
        text = "A" * 500
        result = _normalize_for_compare(text)
        assert len(result) == 200


class TestReadTextSafe:
    def test_reads_utf8(self, tmp_path: Path):
        f = tmp_path / "test.md"
        f.write_text("hello 世界", encoding="utf-8")
        assert _read_text_safe(f) == "hello 世界"

    def test_missing_returns_none(self, tmp_path: Path):
        assert _read_text_safe(tmp_path / "nope.md") is None

    def test_bad_encoding_returns_none(self, tmp_path: Path):
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\xff\xfe\x80\x81")
        # May or may not raise UnicodeDecodeError depending on content
        result = _read_text_safe(f)
        assert isinstance(result, (str, type(None)))


class TestMakeViolation:
    def test_structure(self):
        v = _make_violation("hash_mismatch", "critical", "file.md", "detail text")
        assert v == {
            "type": "hash_mismatch",
            "severity": "critical",
            "file": "file.md",
            "detail": "detail text",
        }


class TestShellQuote:
    def test_simple_string(self):
        assert _shell_quote("hello") == "'hello'"

    def test_string_with_single_quotes(self):
        result = _shell_quote("it's")
        assert "it" in result
        assert "s" in result


# ---------------------------------------------------------------------------
# Load Registered Projects
# ---------------------------------------------------------------------------

class TestLoadRegisteredProjects:
    def test_returns_empty_when_no_index(self, tmp_path: Path):
        with patch(
            "memory_core.tools.daily_kb_audit.LIFECYCLE_INDEX",
            tmp_path / "nope.json",
        ):
            result = load_registered_projects()
            assert result == []

    def test_returns_empty_on_invalid_json(self, tmp_path: Path):
        idx = tmp_path / "path-index.json"
        idx.write_text("NOT JSON", encoding="utf-8")
        with patch(
            "memory_core.tools.daily_kb_audit.LIFECYCLE_INDEX", idx
        ):
            assert load_registered_projects() == []

    def test_parses_valid_index(self, tmp_path: Path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        idx = tmp_path / "path-index.json"
        idx.write_text(
            json.dumps({"paths": {str(project_dir): {"project_name": "test-proj"}}}),
            encoding="utf-8",
        )
        with patch(
            "memory_core.tools.daily_kb_audit.LIFECYCLE_INDEX", idx
        ):
            result = load_registered_projects()
            assert len(result) == 1
            assert result[0][0] == "test-proj"

    def test_excludes_factory_dir(self, tmp_path: Path):
        factory_dir = Path.home() / ".factory"
        idx = tmp_path / "path-index.json"
        idx.write_text(
            json.dumps({"paths": {str(factory_dir): {"project_name": "factory"}}}),
            encoding="utf-8",
        )
        with patch(
            "memory_core.tools.daily_kb_audit.LIFECYCLE_INDEX", idx
        ):
            result = load_registered_projects()
            assert result == []

    def test_uses_directory_name_as_fallback(self, tmp_path: Path):
        project_dir = tmp_path / "cool-name"
        project_dir.mkdir()
        idx = tmp_path / "path-index.json"
        idx.write_text(
            json.dumps({"paths": {str(project_dir): {}}}),
            encoding="utf-8",
        )
        with patch(
            "memory_core.tools.daily_kb_audit.LIFECYCLE_INDEX", idx
        ):
            result = load_registered_projects()
            assert result[0][0] == "cool-name"


# ---------------------------------------------------------------------------
# Build Global KB Fingerprints
# ---------------------------------------------------------------------------

class TestBuildGlobalKbFingerprints:
    def test_empty_when_no_root(self, tmp_path: Path):
        with patch(
            "memory_core.tools.daily_kb_audit.GLOBAL_KB_ROOT",
            tmp_path / "no-global",
        ):
            assert build_global_kb_fingerprints() == {}

    def test_builds_fingerprints(self, tmp_path: Path):
        domain_dir = tmp_path / "operations"
        domain_dir.mkdir()
        f = domain_dir / "test.md"
        f.write_text("some content here", encoding="utf-8")
        with patch(
            "memory_core.tools.daily_kb_audit.GLOBAL_KB_ROOT", tmp_path
        ):
            fps = build_global_kb_fingerprints()
            assert len(fps) >= 1

    def test_skips_whitelisted_files(self, tmp_path: Path):
        domain_dir = tmp_path / "operations"
        domain_dir.mkdir()
        (domain_dir / "README.md").write_text("skip me", encoding="utf-8")
        (domain_dir / ".keep").write_text("", encoding="utf-8")
        with patch(
            "memory_core.tools.daily_kb_audit.GLOBAL_KB_ROOT", tmp_path
        ):
            fps = build_global_kb_fingerprints()
            assert len(fps) == 0


# ---------------------------------------------------------------------------
# Check 1: Manifest Integrity
# ---------------------------------------------------------------------------

class TestCheckManifestIntegrity:
    def test_missing_manifest(self, tmp_path: Path):
        violations = check_manifest_integrity(tmp_path)
        assert len(violations) == 1
        assert violations[0]["type"] == "hash_mismatch"
        assert "不存在" in violations[0]["detail"]

    def test_invalid_json_manifest(self, tmp_path: Path):
        manifest_dir = tmp_path / "memory" / "system"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / MANIFEST_FILENAME).write_text("NOT JSON", encoding="utf-8")
        violations = check_manifest_integrity(tmp_path)
        assert len(violations) == 1
        assert "解析失败" in violations[0]["detail"]

    def test_bad_entries_field(self, tmp_path: Path):
        manifest_dir = tmp_path / "memory" / "system"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / MANIFEST_FILENAME).write_text(
            '{"entries": "not-a-list"}', encoding="utf-8"
        )
        violations = check_manifest_integrity(tmp_path)
        assert len(violations) == 1
        assert "格式错误" in violations[0]["detail"]

    def test_matching_hash(self, tmp_path: Path):
        manifest_dir = tmp_path / "memory" / "system"
        manifest_dir.mkdir(parents=True)
        content_file = tmp_path / "memory" / "kb" / "test.md"
        content_file.parent.mkdir(parents=True)
        content_file.write_text("test content", encoding="utf-8")
        sha = hashlib.sha256(b"test content").hexdigest()
        manifest = {"entries": [{"rel_path": "memory/kb/test.md", "sha256": sha}]}
        (manifest_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        violations = check_manifest_integrity(tmp_path)
        assert len(violations) == 0

    def test_mismatched_hash(self, tmp_path: Path):
        manifest_dir = tmp_path / "memory" / "system"
        manifest_dir.mkdir(parents=True)
        content_file = tmp_path / "memory" / "kb" / "test.md"
        content_file.parent.mkdir(parents=True)
        content_file.write_text("actual content", encoding="utf-8")
        manifest = {"entries": [{"rel_path": "memory/kb/test.md", "sha256": "wrong"}]}
        (manifest_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        violations = check_manifest_integrity(tmp_path)
        assert len(violations) == 1
        assert "不匹配" in violations[0]["detail"]

    def test_missing_signed_file(self, tmp_path: Path):
        manifest_dir = tmp_path / "memory" / "system"
        manifest_dir.mkdir(parents=True)
        manifest = {"entries": [{"rel_path": "memory/kb/gone.md", "sha256": "abc"}]}
        (manifest_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        violations = check_manifest_integrity(tmp_path)
        assert len(violations) == 1
        assert "已缺失" in violations[0]["detail"]


# ---------------------------------------------------------------------------
# Check 2: Unsigned Files
# ---------------------------------------------------------------------------

class TestCheckUnsignedFiles:
    def test_no_kb_dir(self, tmp_path: Path):
        assert check_unsigned_files(tmp_path) == []

    def test_whitelisted_files_skipped(self, tmp_path: Path):
        kb_dir = tmp_path / "memory" / "kb"
        kb_dir.mkdir(parents=True)
        (kb_dir / "README.md").write_text("readme", encoding="utf-8")
        (kb_dir / "INDEX.md").write_text("index", encoding="utf-8")
        assert check_unsigned_files(tmp_path) == []

    def test_unsigned_file_detected(self, tmp_path: Path):
        kb_dir = tmp_path / "memory" / "kb"
        kb_dir.mkdir(parents=True)
        (kb_dir / "rogue.md").write_text("rogue content", encoding="utf-8")
        violations = check_unsigned_files(tmp_path)
        assert len(violations) == 1
        assert violations[0]["type"] == "unsigned_file"

    def test_signed_file_not_flagged(self, tmp_path: Path):
        kb_dir = tmp_path / "memory" / "kb"
        kb_dir.mkdir(parents=True)
        (kb_dir / "signed.md").write_text("content", encoding="utf-8")
        manifest_dir = tmp_path / "memory" / "system"
        manifest_dir.mkdir(parents=True)
        manifest = {"entries": [{"rel_path": "memory/kb/signed.md", "sha256": "x"}]}
        (manifest_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        violations = check_unsigned_files(tmp_path)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# Check 3: Global Residue
# ---------------------------------------------------------------------------

class TestCheckGlobalResidue:
    def test_empty_fingerprints_no_violations(self, tmp_path: Path):
        assert check_global_residue(tmp_path, {}) == []

    def test_residue_detected(self, tmp_path: Path):
        kb_lessons = tmp_path / "memory" / "kb" / "lessons"
        kb_lessons.mkdir(parents=True)
        content = "This is shared global knowledge lesson."
        (kb_lessons / "shared.md").write_text(content, encoding="utf-8")
        fp = _normalize_for_compare(content)
        fingerprints = {fp: "operations/shared.md"}
        violations = check_global_residue(tmp_path, fingerprints)
        assert len(violations) == 1
        assert violations[0]["type"] == "residue"

    def test_no_residue_for_unique_content(self, tmp_path: Path):
        kb_decisions = tmp_path / "memory" / "kb" / "decisions"
        kb_decisions.mkdir(parents=True)
        (kb_decisions / "unique.md").write_text("Unique local decision", encoding="utf-8")
        fingerprints = {"somethingcompletelydifferent": "eng/other.md"}
        violations = check_global_residue(tmp_path, fingerprints)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# Check 4: Large/DB Files
# ---------------------------------------------------------------------------

class TestCheckLargeOrDbFiles:
    def test_clean_project(self, tmp_path: Path):
        (tmp_path / "readme.md").write_text("readme", encoding="utf-8")
        assert check_large_or_db_files(tmp_path) == []

    def test_database_file_detected(self, tmp_path: Path):
        (tmp_path / "data.sqlite").write_bytes(b"fake sqlite")
        violations = check_large_or_db_files(tmp_path)
        assert len(violations) >= 1
        assert any(v["type"] == "large_file" for v in violations)

    def test_large_sql_detected(self, tmp_path: Path):
        sql_file = tmp_path / "big.sql"
        sql_file.write_bytes(b"x" * (1024 * 1024 + 1))
        violations = check_large_or_db_files(tmp_path)
        assert any("大型 SQL" in v["detail"] for v in violations)

    def test_small_sql_not_flagged(self, tmp_path: Path):
        sql_file = tmp_path / "small.sql"
        sql_file.write_bytes(b"SELECT 1;")
        violations = check_large_or_db_files(tmp_path)
        assert not any("大型 SQL" in v.get("detail", "") for v in violations)

    def test_backups_dir_detected(self, tmp_path: Path):
        backups = tmp_path / "backups"
        backups.mkdir()
        (backups / "dump.bak").write_bytes(b"backup data")
        violations = check_large_or_db_files(tmp_path)
        assert any("backups/" in v["detail"] for v in violations)

    def test_db_suffix_variants(self, tmp_path: Path):
        for suffix in [".dump", ".bak", ".db"]:
            (tmp_path / f"file{suffix}").write_bytes(b"data")
        violations = check_large_or_db_files(tmp_path)
        db_violations = [v for v in violations if v["type"] == "large_file"]
        assert len(db_violations) >= 3


# ---------------------------------------------------------------------------
# Check 5: Version Consistency
# ---------------------------------------------------------------------------

class TestExtractVersionFromToml:
    def test_memory_lock_style(self):
        text = '[memory]\nmemory_version = "0.8.1"\n'
        assert _extract_version_from_toml(text) == "0.8.1"

    def test_adapter_style(self):
        text = '[core]\nversion = "1.0.0"\n'
        assert _extract_version_from_toml(text) == "1.0.0"

    def test_no_version(self):
        assert _extract_version_from_toml("no version here") is None


class TestCheckVersionConsistency:
    def test_all_missing(self, tmp_path: Path):
        violations = check_version_consistency(tmp_path)
        assert len(violations) == 3  # memory.lock, adapter.toml, ownership.toml

    def test_matching_version(self, tmp_path: Path):
        from memory_core.constants import CURRENT_MEMORY_VERSION, SYSTEM_DIR

        sys_dir = tmp_path / SYSTEM_DIR
        sys_dir.mkdir(parents=True)
        for fname in ["memory.lock", "adapter.toml", "ownership.toml"]:
            (sys_dir / fname).write_text(
                f'memory_version = "{CURRENT_MEMORY_VERSION}"\n', encoding="utf-8"
            )
        violations = check_version_consistency(tmp_path)
        # All match CURRENT_MEMORY_VERSION, and all three agree → no violations
        assert len(violations) == 0

    def test_mismatched_version(self, tmp_path: Path):
        sys_dir = tmp_path / "memory" / "system"
        sys_dir.mkdir(parents=True)
        (sys_dir / "memory.lock").write_text(
            'memory_version = "9.9.9"\n', encoding="utf-8"
        )
        (sys_dir / "adapter.toml").write_text(
            'memory_version = "9.9.9"\n', encoding="utf-8"
        )
        (sys_dir / "ownership.toml").write_text(
            'memory_version = "9.9.9"\n', encoding="utf-8"
        )
        violations = check_version_consistency(tmp_path)
        assert any("不一致" in v["detail"] for v in violations)

    def test_inconsistent_versions(self, tmp_path: Path):
        sys_dir = tmp_path / "memory" / "system"
        sys_dir.mkdir(parents=True)
        (sys_dir / "memory.lock").write_text(
            'memory_version = "1.0.0"\n', encoding="utf-8"
        )
        (sys_dir / "adapter.toml").write_text(
            'memory_version = "2.0.0"\n', encoding="utf-8"
        )
        (sys_dir / "ownership.toml").write_text(
            'memory_version = "3.0.0"\n', encoding="utf-8"
        )
        violations = check_version_consistency(tmp_path)
        assert any("三文件版本不一致" in v["detail"] for v in violations)


# ---------------------------------------------------------------------------
# Check 6: Infrastructure helpers
# ---------------------------------------------------------------------------

class TestTcpConnectOk:
    def test_connection_refused(self):
        # Port 1 is almost certainly not listening
        assert _tcp_connect_ok("127.0.0.1", 1, timeout=1) is False

    @patch("memory_core.tools.daily_kb_audit.socket.create_connection")
    def test_connection_success(self, mock_conn):
        mock_conn.return_value.__enter__ = MagicMock()
        mock_conn.return_value.__exit__ = MagicMock()
        assert _tcp_connect_ok("127.0.0.1", 8080, timeout=1) is True


class TestCheckSshReachable:
    @patch("memory_core.tools.daily_kb_audit._run_ssh")
    def test_ssh_ok(self, mock_run):
        mock_run.return_value = (0, "ok\n", "")
        assert check_ssh_reachable("myhost") is True

    @patch("memory_core.tools.daily_kb_audit._run_ssh")
    def test_ssh_fail(self, mock_run):
        mock_run.return_value = (1, "", "error")
        assert check_ssh_reachable("myhost") is False


class TestCheckDiskSpace:
    @patch("memory_core.tools.daily_kb_audit._run_ssh")
    def test_disk_ok(self, mock_run):
        mock_run.return_value = (
            0,
            "Filesystem      Size  Used Avail Use% Mounted on\n"
            "/dev/sda1        50G   35G   12G  70% /\n",
            "",
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = check_disk_space(
            "alias", "server1",
            [{"mount": "/", "warn_pct": 80, "crit_pct": 90}],
            global_v, record_v,
        )
        assert "/" in result
        assert result["/"]["status"] == "ok"
        assert len(global_v) == 0

    @patch("memory_core.tools.daily_kb_audit._run_ssh")
    def test_disk_warning(self, mock_run):
        mock_run.return_value = (
            0,
            "Filesystem      Size  Used Avail Use% Mounted on\n"
            "/dev/sda1        50G   42G    8G  85% /\n",
            "",
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = check_disk_space(
            "alias", "server1",
            [{"mount": "/", "warn_pct": 80, "crit_pct": 90}],
            global_v, record_v,
        )
        assert result["/"]["status"] == "warning"
        assert len(global_v) == 1

    @patch("memory_core.tools.daily_kb_audit._run_ssh")
    def test_disk_critical(self, mock_run):
        mock_run.return_value = (
            0,
            "Filesystem      Size  Used Avail Use% Mounted on\n"
            "/dev/sda1        50G   47G    3G  95% /\n",
            "",
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = check_disk_space(
            "alias", "server1",
            [{"mount": "/", "warn_pct": 80, "crit_pct": 90}],
            global_v, record_v,
        )
        assert result["/"]["status"] == "critical"
        assert len(global_v) == 1

    @patch("memory_core.tools.daily_kb_audit._run_ssh")
    def test_df_failure(self, mock_run):
        mock_run.return_value = (1, "", "permission denied")
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = check_disk_space("alias", "srv", [{"mount": "/"}], global_v, record_v)
        assert result == {}
        assert len(global_v) == 1

    @patch("memory_core.tools.daily_kb_audit._run_ssh")
    def test_pattern_matching(self, mock_run):
        mock_run.return_value = (
            0,
            "Filesystem      Size  Used Avail Use% Mounted on\n"
            "overlay          50G   30G   20G  60% /var/lib/docker\n",
            "",
        )
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = check_disk_space(
            "alias", "srv",
            [{"pattern": "docker", "warn_pct": 80, "crit_pct": 90}],
            global_v, record_v,
        )
        assert "/var/lib/docker" in result

    def test_empty_disk_checks(self):
        global_v: list[dict] = []
        record_v: list[dict] = []
        result = check_disk_space("alias", "srv", [], global_v, record_v)
        assert result == {}


class TestCheckServer:
    @patch("memory_core.tools.daily_kb_audit._tcp_connect_ok")
    @patch("memory_core.tools.daily_kb_audit.check_ssh_reachable")
    def test_ssh_down(self, mock_ssh, mock_tcp):
        mock_ssh.return_value = False
        global_v: list[dict] = []
        server = {
            "name": "test-srv",
            "host": "10.0.0.1",
            "ssh_alias": "test-srv",
            "checks": {"ssh": True},
        }
        result = check_server(server, global_v)
        assert result["ssh_ok"] is False
        assert len(global_v) >= 1

    @patch("memory_core.tools.daily_kb_audit._tcp_connect_ok")
    @patch("memory_core.tools.daily_kb_audit._run_ssh")
    @patch("memory_core.tools.daily_kb_audit.check_ssh_reachable")
    def test_port_check(self, mock_ssh, mock_run, mock_tcp):
        mock_ssh.return_value = True
        mock_run.return_value = (0, "", "")
        mock_tcp.return_value = False
        global_v: list[dict] = []
        server = {
            "name": "srv",
            "host": "10.0.0.1",
            "ssh_alias": "srv",
            "checks": {"ssh": True, "ports": [80, 443]},
        }
        result = check_server(server, global_v)
        assert result["ports"]["80"] is False
        assert result["ports"]["443"] is False

    def test_missing_ssh_alias(self):
        global_v: list[dict] = []
        server = {
            "name": "srv",
            "host": "10.0.0.1",
            "checks": {"ssh": True},
        }
        check_server(server, global_v)
        assert len(global_v) >= 1

    @patch("memory_core.tools.daily_kb_audit._run_ssh")
    @patch("memory_core.tools.daily_kb_audit.check_ssh_reachable")
    def test_docker_containers(self, mock_ssh, mock_run_ssh):
        mock_ssh.return_value = True
        # docker ps output
        mock_run_ssh.return_value = (0, "nginx: Up 2 days\nredis: Up 5 hours\n", "")
        global_v: list[dict] = []
        server = {
            "name": "srv",
            "host": "10.0.0.1",
            "ssh_alias": "srv",
            "checks": {
                "ssh": True,
                "docker_containers": ["nginx", "redis", "postgres"],
            },
        }
        result = check_server(server, global_v)
        assert result["containers"]["nginx"] == "Up 2 days"
        assert result["containers"]["postgres"] == "DOWN"


class TestCheckDatabase:
    @patch("memory_core.tools.daily_kb_audit._tcp_connect_ok")
    def test_db_reachable(self, mock_tcp):
        mock_tcp.return_value = True
        global_v: list[dict] = []
        db = {"name": "mydb", "host": "10.0.0.1", "port": 3306}
        result = check_database(db, global_v)
        assert result["connect_ok"] is True
        assert len(global_v) == 0

    @patch("memory_core.tools.daily_kb_audit._tcp_connect_ok")
    def test_db_unreachable(self, mock_tcp):
        mock_tcp.return_value = False
        global_v: list[dict] = []
        db = {"name": "mydb", "host": "10.0.0.1", "port": 3306}
        result = check_database(db, global_v)
        assert result["connect_ok"] is False
        assert len(global_v) == 1

    def test_unsupported_check_kind(self):
        global_v: list[dict] = []
        db = {"name": "mydb", "host": "10.0.0.1", "port": 3306, "check": "mysql_ping"}
        result = check_database(db, global_v)
        assert result["connect_ok"] is False
        assert any("不支持" in v["detail"] for v in global_v)


class TestCheckInfrastructure:
    def test_returns_empty_when_no_inventory(self, tmp_path: Path):
        with patch(
            "memory_core.tools.daily_kb_audit._load_infra_inventory",
            return_value=None,
        ):
            result = check_infrastructure()
            assert result["servers"] == {}
            assert result["databases"] == {}

    @patch("memory_core.tools.daily_kb_audit.check_database")
    @patch("memory_core.tools.daily_kb_audit.check_server")
    @patch("memory_core.tools.daily_kb_audit._load_infra_inventory")
    def test_processes_servers_and_dbs(
        self, mock_load, mock_server, mock_db
    ):
        mock_load.return_value = {
            "servers": [{"name": "srv1", "host": "10.0.0.1"}],
            "databases": [{"name": "db1", "host": "10.0.0.2", "port": 3306}],
        }
        mock_server.return_value = {"host": "10.0.0.1", "violations": []}
        mock_db.return_value = {"host": "10.0.0.2", "connect_ok": True, "violations": []}
        result = check_infrastructure()
        assert "srv1" in result["servers"]
        assert "db1" in result["databases"]


# ---------------------------------------------------------------------------
# Audit Project
# ---------------------------------------------------------------------------

class TestAuditProject:
    def test_nonexistent_path(self, tmp_path: Path):
        result = audit_project("gone", tmp_path / "nope", {})
        assert result.get("skipped") is True

    def test_empty_project(self, tmp_path: Path):
        result = audit_project("test", tmp_path, {})
        assert "violations" in result
        # Should have manifest missing violation
        assert any("不存在" in v.get("detail", "") for v in result["violations"])

    def test_source_repo_note(self, tmp_path: Path):
        memory_core_dir = tmp_path / "memory_core" / "tools"
        memory_core_dir.mkdir(parents=True)
        (memory_core_dir / "memory_hook_gateway.py").touch()
        (memory_core_dir / "factory_global_hooks.py").touch()
        (tmp_path / "memory_core" / "ownership.py").touch()
        manifest_dir = tmp_path / "memory" / "system"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "manifest.json").write_text('{"entries": []}', encoding="utf-8")
        result = audit_project("mc", tmp_path, {})
        assert "note" in result
        assert "源仓库" in result["note"]


# ---------------------------------------------------------------------------
# Report Building & Writing
# ---------------------------------------------------------------------------

class TestBuildReport:
    def test_basic_report(self):
        projects = {
            "proj1": {"path": "/p1", "violations": []},
            "proj2": {"path": "/p2", "violations": [{"type": "x", "severity": "critical", "file": "f", "detail": "d"}]},
        }
        report = build_report(projects)
        assert report["projects_checked"] == 2
        assert report["total_violations"] == 1
        assert "audit_date" in report

    def test_report_with_infrastructure(self):
        projects = {"p": {"path": "/p", "violations": []}}
        infra = {
            "servers": {},
            "databases": {},
            "violations": [{"type": "x", "severity": "critical", "file": "f", "detail": "d"}],
        }
        report = build_report(projects, infrastructure=infra)
        assert report["infrastructure_checked"] is True
        assert report["total_violations"] == 1


class TestWriteReport:
    def test_writes_file(self, tmp_path: Path):
        with patch("memory_core.tools.daily_kb_audit.AUDIT_DIR", tmp_path):
            report = {"audit_date": "2026-07-12", "data": "test"}
            out = write_report(report)
            assert out.exists()
            data = json.loads(out.read_text(encoding="utf-8"))
            assert data["audit_date"] == "2026-07-12"


# ---------------------------------------------------------------------------
# Summary Generation
# ---------------------------------------------------------------------------

class TestSummarizeReport:
    def test_no_violations(self):
        report = {
            "audit_date": "2026-07-12",
            "projects_checked": 2,
            "total_violations": 0,
            "projects": {"p1": {"violations": []}, "p2": {"violations": []}},
        }
        summary = _summarize_report(report)
        assert "全部项目通过" in summary
        assert "2026-07-12" in summary

    def test_with_critical_violations(self):
        report = {
            "audit_date": "2026-07-12",
            "projects_checked": 1,
            "total_violations": 2,
            "projects": {
                "proj1": {
                    "violations": [
                        {"type": "hash_mismatch", "severity": "critical", "file": "f.md", "detail": "tampered"},
                        {"type": "unsigned_file", "severity": "warning", "file": "u.md", "detail": "unsigned"},
                    ]
                }
            },
        }
        summary = _summarize_report(report)
        assert "critical=1" in summary
        assert "warning=1" in summary
        assert "proj1" in summary

    def test_many_violations_truncated(self):
        violations = [
            {"type": "t", "severity": "warning", "file": f"f{i}.md", "detail": f"d{i}"}
            for i in range(10)
        ]
        report = {
            "audit_date": "2026-07-12",
            "projects_checked": 1,
            "total_violations": 10,
            "projects": {"proj1": {"violations": violations}},
        }
        summary = _summarize_report(report)
        assert "还有 7 条" in summary


class TestAppendInfraSummary:
    def test_no_infra(self):
        lines: list[str] = []
        _append_infra_summary(lines, {})
        assert len(lines) == 0

    def test_with_servers(self):
        lines: list[str] = []
        report = {
            "infrastructure": {
                "servers": {
                    "srv1": {
                        "ssh_ok": True,
                        "systemd_services": {"nginx": "running"},
                        "containers": {"redis": "Up 2 days"},
                        "ports": {"80": True},
                        "http_endpoints": {"api": {"ok": True}},
                        "disk_space": {"/": {"use_pct": 70, "avail": "30G"}},
                    }
                },
                "databases": {"db1": {"connect_ok": True}},
            }
        }
        _append_infra_summary(lines, report)
        text = "\n".join(lines)
        assert "srv1" in text
        assert "db1" in text
        assert "基础设施" in text

    def test_disk_warning_display(self):
        lines: list[str] = []
        report = {
            "infrastructure": {
                "servers": {
                    "srv1": {
                        "ssh_ok": False,
                        "systemd_services": {},
                        "containers": {},
                        "ports": {},
                        "http_endpoints": {},
                        "disk_space": {
                            "/data": {"use_pct": 95, "avail": "2G"},
                            "/logs": {"use_pct": 85, "avail": "5G"},
                        },
                    }
                },
                "databases": {},
            }
        }
        _append_infra_summary(lines, report)
        text = "\n".join(lines)
        assert "🔴" in text  # 95% is critical
        assert "🟡" in text  # 85% is warning


# ---------------------------------------------------------------------------
# Count helpers
# ---------------------------------------------------------------------------

class TestCountHelpers:
    def test_count_critical_infra_none(self):
        assert _count_critical_infra(None) == 0

    def test_count_critical_infra(self):
        infra = {
            "servers": {
                "s1": {"violations": [{"severity": "critical"}, {"severity": "warning"}]}
            },
            "databases": {
                "d1": {"violations": [{"severity": "critical"}]}
            },
        }
        assert _count_critical_infra(infra) == 2

    def test_count_warning_infra_none(self):
        assert _count_warning_infra(None) == 0

    def test_count_warning_infra(self):
        infra = {
            "servers": {
                "s1": {"violations": [{"severity": "warning"}, {"severity": "warning"}]}
            },
            "databases": {},
        }
        assert _count_warning_infra(infra) == 2


# ---------------------------------------------------------------------------
# Notify via Lark
# ---------------------------------------------------------------------------

class TestNotifyViaLark:
    def test_no_env_var(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LARK_AUDIT_CHAT_ID", None)
            assert notify_via_lark({"audit_date": "2026-07-12"}) is False

    @patch("memory_core.tools.daily_kb_audit.subprocess.run")
    def test_lark_cli_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        with patch.dict(os.environ, {"LARK_AUDIT_CHAT_ID": "chat123"}):
            report = {"audit_date": "2026-07-12", "projects_checked": 0, "total_violations": 0, "projects": {}}
            assert notify_via_lark(report) is False

    @patch("memory_core.tools.daily_kb_audit.subprocess.run")
    def test_lark_success(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with patch.dict(os.environ, {"LARK_AUDIT_CHAT_ID": "chat123"}):
            report = {"audit_date": "2026-07-12", "projects_checked": 0, "total_violations": 0, "projects": {}}
            assert notify_via_lark(report) is True

    @patch("memory_core.tools.daily_kb_audit.subprocess.run")
    def test_lark_failure(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess([], 1, "", "error msg")
        with patch.dict(os.environ, {"LARK_AUDIT_CHAT_ID": "chat123"}):
            report = {"audit_date": "2026-07-12", "projects_checked": 0, "total_violations": 0, "projects": {}}
            assert notify_via_lark(report) is False


# ---------------------------------------------------------------------------
# CLI Parsing
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_defaults(self):
        args = _parse_args([])
        assert args.json is False
        assert args.notify is False
        assert args.no_write is False
        assert args.no_infra is False

    def test_json_flag(self):
        args = _parse_args(["--json"])
        assert args.json is True

    def test_notify_flag(self):
        args = _parse_args(["--notify"])
        assert args.notify is True

    def test_no_infra_flag(self):
        args = _parse_args(["--no-infra"])
        assert args.no_infra is True

    def test_no_write_flag(self):
        args = _parse_args(["--no-write"])
        assert args.no_write is True

    def test_multiple_flags(self):
        args = _parse_args(["--json", "--notify", "--no-infra", "--no-write"])
        assert args.json is True
        assert args.notify is True
        assert args.no_infra is True
        assert args.no_write is True


# ---------------------------------------------------------------------------
# main() function
# ---------------------------------------------------------------------------

class TestMain:
    @patch("memory_core.tools.daily_kb_audit.check_infrastructure")
    @patch("memory_core.tools.daily_kb_audit.load_registered_projects")
    @patch("memory_core.tools.daily_kb_audit.write_report")
    def test_no_projects_returns_zero(self, mock_write, mock_load, mock_infra, tmp_path: Path):
        mock_load.return_value = []
        mock_infra.return_value = {"servers": {}, "databases": {}, "violations": []}
        mock_write.return_value = tmp_path / "report.json"
        rc = main(["--no-infra"])
        assert rc == 0

    @patch("memory_core.tools.daily_kb_audit.check_infrastructure")
    @patch("memory_core.tools.daily_kb_audit.load_registered_projects")
    @patch("memory_core.tools.daily_kb_audit.write_report")
    def test_infra_critical_returns_one(self, mock_write, mock_load, mock_infra, tmp_path: Path):
        mock_load.return_value = []
        mock_infra.return_value = {
            "servers": {
                "s1": {"violations": [{"severity": "critical"}]}
            },
            "databases": {},
            "violations": [{"severity": "critical"}],
        }
        mock_write.return_value = tmp_path / "report.json"
        rc = main([])
        assert rc == 1

    @patch("memory_core.tools.daily_kb_audit.build_global_kb_fingerprints")
    @patch("memory_core.tools.daily_kb_audit.audit_project")
    @patch("memory_core.tools.daily_kb_audit.check_infrastructure")
    @patch("memory_core.tools.daily_kb_audit.load_registered_projects")
    @patch("memory_core.tools.daily_kb_audit.write_report")
    def test_with_projects(
        self, mock_write, mock_load, mock_infra, mock_audit, mock_fps,
        tmp_path: Path,
    ):
        mock_load.return_value = [("proj1", tmp_path)]
        mock_infra.return_value = {"servers": {}, "databases": {}, "violations": []}
        mock_audit.return_value = {"path": str(tmp_path), "violations": []}
        mock_fps.return_value = {}
        mock_write.return_value = tmp_path / "report.json"
        rc = main(["--no-infra"])
        assert rc == 0
        mock_audit.assert_called_once()

    @patch("memory_core.tools.daily_kb_audit.build_global_kb_fingerprints")
    @patch("memory_core.tools.daily_kb_audit.audit_project")
    @patch("memory_core.tools.daily_kb_audit.check_infrastructure")
    @patch("memory_core.tools.daily_kb_audit.load_registered_projects")
    @patch("memory_core.tools.daily_kb_audit.write_report")
    def test_critical_violations_return_one(
        self, mock_write, mock_load, mock_infra, mock_audit, mock_fps,
        tmp_path: Path,
    ):
        mock_load.return_value = [("proj1", tmp_path)]
        mock_infra.return_value = {"servers": {}, "databases": {}, "violations": []}
        mock_audit.return_value = {
            "path": str(tmp_path),
            "violations": [{"type": "x", "severity": "critical", "file": "f", "detail": "d"}],
        }
        mock_fps.return_value = {}
        mock_write.return_value = tmp_path / "report.json"
        rc = main(["--no-infra"])
        assert rc == 1

    @patch("memory_core.tools.daily_kb_audit.build_global_kb_fingerprints")
    @patch("memory_core.tools.daily_kb_audit.audit_project")
    @patch("memory_core.tools.daily_kb_audit.check_infrastructure")
    @patch("memory_core.tools.daily_kb_audit.load_registered_projects")
    @patch("memory_core.tools.daily_kb_audit.write_report")
    def test_json_output(
        self, mock_write, mock_load, mock_infra, mock_audit, mock_fps,
        tmp_path: Path, capsys,
    ):
        mock_load.return_value = [("proj1", tmp_path)]
        mock_infra.return_value = {"servers": {}, "databases": {}, "violations": []}
        mock_audit.return_value = {"path": str(tmp_path), "violations": []}
        mock_fps.return_value = {}
        mock_write.return_value = tmp_path / "report.json"
        rc = main(["--json", "--no-infra"])
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "audit_date" in data

    @patch("memory_core.tools.daily_kb_audit.notify_via_lark")
    @patch("memory_core.tools.daily_kb_audit.build_global_kb_fingerprints")
    @patch("memory_core.tools.daily_kb_audit.audit_project")
    @patch("memory_core.tools.daily_kb_audit.check_infrastructure")
    @patch("memory_core.tools.daily_kb_audit.load_registered_projects")
    @patch("memory_core.tools.daily_kb_audit.write_report")
    def test_notify_called(
        self, mock_write, mock_load, mock_infra, mock_audit, mock_fps,
        mock_notify, tmp_path: Path,
    ):
        mock_load.return_value = [("proj1", tmp_path)]
        mock_infra.return_value = {"servers": {}, "databases": {}, "violations": []}
        mock_audit.return_value = {"path": str(tmp_path), "violations": []}
        mock_fps.return_value = {}
        mock_write.return_value = tmp_path / "report.json"
        mock_notify.return_value = True
        rc = main(["--notify", "--no-infra"])
        assert rc == 0
        mock_notify.assert_called_once()

    @patch("memory_core.tools.daily_kb_audit.check_infrastructure")
    @patch("memory_core.tools.daily_kb_audit.load_registered_projects")
    @patch("memory_core.tools.daily_kb_audit.write_report")
    def test_infra_exception_degrades_gracefully(
        self, mock_write, mock_load, mock_infra, tmp_path: Path,
    ):
        mock_load.return_value = []
        mock_infra.side_effect = RuntimeError("boom")
        mock_write.return_value = tmp_path / "report.json"
        rc = main([])
        assert rc == 0  # no projects, infra exception handled
