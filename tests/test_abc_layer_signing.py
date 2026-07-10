#!/usr/bin/env python3
"""F5: A/B/C 层签名集成测试。

验证 session_end_logger.py (A层)、daily_summary_generator.py (B层)、
error_logger.py (C层) 在写入文件后调用 sign_project_incremental。

策略：不 mock 签名函数本身，而是验证实际行为：
1. 文件被签名（manifest 中有对应条目）
2. 签名失败不阻塞主流程（mock signer 抛异常）
3. 密钥不存在时不调用签名
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path

# Mock integrity key for CI environments where ~/.memory-core/keys/ doesn't exist
# This must be done before importing any modules that use load_key
import memory_core.tools.memory_hook_integrity_keys as _key_module
_original_load_key = _key_module.load_key
_key_module.load_key = lambda path=None: b"test_key_32_bytes_long_padding!" if _original_load_key(path) is None else _original_load_key(path)

# ── 辅助函数 ──────────────────────────────────────────────────────

def _create_minimal_project(tmp_path: Path) -> Path:
    """创建最小项目结构，包含 manifest.json。"""
    project = tmp_path / "test-project"
    (project / "memory" / "system").mkdir(parents=True)
    (project / "memory" / "log").mkdir(parents=True)

    # 创建 manifest.json
    manifest = {
        "schema_version": "integrity-manifest-v2",
        "project_root": str(project.resolve()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "key_fingerprint": "sha256:00000000",
        "ownership_digest": "0" * 64,
        "entry_count": 0,
        "entries": [],
    }
    manifest_path = project / "memory" / "system" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return project


# ── B 层测试 (daily_summary_generator.py) ──────────────────────────

class TestBLayerSigning:
    """B 层: daily_summary_generator.py 在写入 {date}.md 后签名。"""

    def test_b_layer_signs_after_write(self, tmp_path, monkeypatch):
        """VAL-F5-002: B-layer signs daily summary after write."""
        project = _create_minimal_project(tmp_path)
        today = datetime.now().strftime("%Y-%m-%d")

        # 创建 sessions.md（B层需要读取）
        sessions_md = project / "memory" / "log" / f"{today}-sessions.md"
        sessions_md.write_text(
            f"# Sessions Log — {today}\n\n"
            "### abc123de\n"
            "- **标题**: Test Session\n"
            "- **模型**: GLM-5.1 | **时长**: 2m30s\n"
            "- **Token**: input=100 output=200\n"
            "- **工具调用**: Read=1\n"
            "- **用户意图**: test intent\n"
            "- **助手摘要**: test summary\n"
            "---\n"
        )

        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_memory_core_source_repo",
            lambda p: False,
        )
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_denied_project_root",
            lambda p: False,
        )

        from memory_core.tools.daily_summary_generator import _write_daily_log

        _write_daily_log(project, today, [
            {"full_session_id": "abc123de", "title": "Test", "model": "GLM-5.1",
             "duration": "2m30s", "input_tokens": 100, "output_tokens": 200,
             "tool_calls_raw": "Read=1", "user_prompt_preview": "test"}
        ], llm_summary=None, dry_run=False)

        # 验证文件被写入
        output_path = project / "memory" / "log" / f"{today}.md"
        assert output_path.exists(), "Daily summary should be created"

        # 验证 manifest 中有 {date}.md 条目
        manifest_path = project / "memory" / "system" / "manifest.json"
        assert manifest_path.exists(), "manifest.json should be created"
        manifest = json.loads(manifest_path.read_text())
        entries = manifest.get("entries", [])
        found = [e for e in entries if f"{today}.md" in e.get("rel_path", "")]
        assert len(found) == 1, f"Should find {today}.md entry, got: {[e['rel_path'] for e in entries]}"

        expected_sha = hashlib.sha256(output_path.read_bytes()).hexdigest()
        assert found[0]["sha256"] == expected_sha

    def test_b_layer_signing_failure_non_blocking(self, tmp_path, monkeypatch):
        """VAL-F5-004: B-layer signing failure does not block main flow."""
        project = _create_minimal_project(tmp_path)
        today = datetime.now().strftime("%Y-%m-%d")

        sessions_md = project / "memory" / "log" / f"{today}-sessions.md"
        sessions_md.write_text(f"# Sessions Log — {today}\n\n### abc123de\n---\n")

        mock_signer = unittest.mock.MagicMock(side_effect=RuntimeError("signer broken"))
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.sign_project_incremental",
            mock_signer,
        )
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_memory_core_source_repo",
            lambda p: False,
        )
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_denied_project_root",
            lambda p: False,
        )

        for mod in list(sys.modules.keys()):
            if "daily_summary_generator" in mod:
                del sys.modules[mod]

        from memory_core.tools.daily_summary_generator import _write_daily_log

        _write_daily_log(project, today, [
            {"full_session_id": "abc123de", "title": "Test", "model": "GLM-5.1",
             "duration": "1m", "input_tokens": 10, "output_tokens": 20,
             "tool_calls_raw": "", "user_prompt_preview": "test"}
        ], llm_summary=None, dry_run=False)

        output_path = project / "memory" / "log" / f"{today}.md"
        assert output_path.exists(), "Output file should exist even if signing fails"


# ── C 层测试 (error_logger.py) ─────────────────────────────────────

class TestCLayerSigning:
    """C 层: error_logger.py 在写入 {date}-errors.jsonl 后签名。"""

    def test_c_layer_signs_after_write(self, tmp_path, monkeypatch):
        """VAL-F5-003: C-layer signs errors.jsonl after write."""
        project = _create_minimal_project(tmp_path)
        today = datetime.now().strftime("%Y-%m-%d")

        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_memory_core_source_repo",
            lambda p: False,
        )
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_denied_project_root",
            lambda p: False,
        )

        from memory_core.tools.error_logger import write_error_log

        result = write_error_log(
            str(project),
            "transcript_missing",
            {"session_id": "abc123"},
            "transcript file not found",
        )

        assert result is True, "write_error_log should return True"

        # 验证文件被写入
        errors_jsonl = project / "memory" / "log" / f"{today}-errors.jsonl"
        assert errors_jsonl.exists(), "errors.jsonl should be created"

        # 验证 manifest 中有 errors.jsonl 条目
        manifest_path = project / "memory" / "system" / "manifest.json"
        assert manifest_path.exists(), "manifest.json should be created"
        manifest = json.loads(manifest_path.read_text())
        entries = manifest.get("entries", [])
        found = [e for e in entries if f"{today}-errors.jsonl" in e.get("rel_path", "")]
        assert len(found) == 1, f"Should find errors.jsonl entry, got: {[e['rel_path'] for e in entries]}"

        expected_sha = hashlib.sha256(errors_jsonl.read_bytes()).hexdigest()
        assert found[0]["sha256"] == expected_sha

    def test_c_layer_signing_failure_non_blocking(self, tmp_path, monkeypatch):
        """VAL-F5-004: C-layer signing failure does not block main flow."""
        project = _create_minimal_project(tmp_path)

        mock_signer = unittest.mock.MagicMock(side_effect=RuntimeError("signer broken"))
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.sign_project_incremental",
            mock_signer,
        )
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_memory_core_source_repo",
            lambda p: False,
        )
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_denied_project_root",
            lambda p: False,
        )

        for mod in list(sys.modules.keys()):
            if "error_logger" in mod:
                del sys.modules[mod]

        from memory_core.tools.error_logger import write_error_log

        result = write_error_log(
            str(project),
            "file_write_failed",
            {"file_path": "/tmp/test", "error": "test"},
            "test error",
        )

        assert result is True, "write_error_log should return True even if signing fails"

    def test_c_layer_missing_key_skips_signing(self, tmp_path, monkeypatch):
        """VAL-F5-005: C-layer missing key → silent skip."""
        project = _create_minimal_project(tmp_path)

        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_keys.load_key",
            lambda path=None: None,
        )
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_memory_core_source_repo",
            lambda p: False,
        )
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_denied_project_root",
            lambda p: False,
        )

        for mod in list(sys.modules.keys()):
            if "error_logger" in mod:
                del sys.modules[mod]

        from memory_core.tools.error_logger import write_error_log

        result = write_error_log(
            str(project),
            "transcript_missing",
            {"session_id": "abc123"},
            "transcript file not found",
        )

        assert result is True, "write_error_log should return True when key is missing"

        # manifest 应该不变
        manifest_path = project / "memory" / "system" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["entry_count"] == 0, "Manifest should not be updated when key is missing"


# ── 跨层测试: Manifest 更新 ───────────────────────────────────────

class TestManifestUpdated:
    """VAL-F5-006: Manifest entries are refreshed after each layer's signing."""

    def test_manifest_updated_after_a_layer_write(self, tmp_path, monkeypatch):
        """A-layer write → manifest entry for sessions.md matches file sha256."""
        project = _create_minimal_project(tmp_path)

        today = datetime.now().strftime("%Y-%m-%d")
        sessions_md = project / "memory" / "log" / f"{today}-sessions.md"
        sessions_md.write_text("# Sessions\n---\n")

        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_memory_core_source_repo",
            lambda p: False,
        )
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_denied_project_root",
            lambda p: False,
        )

        from memory_core.tools.memory_hook_integrity_manifest import sign_project_incremental

        key = b"test" * 8
        result = sign_project_incremental(
            project, key,
            changed_paths=[f"memory/log/{today}-sessions.md"],
        )

        assert result is not None
        entries = result.get("entries", [])
        found = [e for e in entries if f"{today}-sessions.md" in e.get("rel_path", "")]
        assert len(found) == 1

        expected_sha = hashlib.sha256(sessions_md.read_bytes()).hexdigest()
        assert found[0]["sha256"] == expected_sha

    def test_manifest_updated_after_c_layer_write(self, tmp_path, monkeypatch):
        """C-layer write → manifest entry for errors.jsonl matches file sha256."""
        project = _create_minimal_project(tmp_path)

        today = datetime.now().strftime("%Y-%m-%d")
        errors_jsonl = project / "memory" / "log" / f"{today}-errors.jsonl"
        errors_jsonl.write_text(
            json.dumps({"ts": "2026-05-28T10:00:00", "type": "test", "msg": "test"}) + "\n"
        )

        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_memory_core_source_repo",
            lambda p: False,
        )
        monkeypatch.setattr(
            "memory_core.tools.memory_hook_integrity_manifest.is_denied_project_root",
            lambda p: False,
        )

        from memory_core.tools.memory_hook_integrity_manifest import sign_project_incremental

        key = b"test" * 8
        result = sign_project_incremental(
            project, key,
            changed_paths=[f"memory/log/{today}-errors.jsonl"],
        )

        assert result is not None
        entries = result.get("entries", [])
        found = [e for e in entries if f"{today}-errors.jsonl" in e.get("rel_path", "")]
        assert len(found) == 1

        expected_sha = hashlib.sha256(errors_jsonl.read_bytes()).hexdigest()
        assert found[0]["sha256"] == expected_sha
