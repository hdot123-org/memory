"""Tests for sync configuration: SyncConfig, template_sync, init --sync."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools.adapter_toml_schema import (
    SyncConfig,
    dump_sync_toml,
    load_sync_config,
)
from memory_core.tools.template_sync import (
    generate_agents_md_sync_block,
    generate_contributing_sync_block,
    generate_gitlab_ci_yml,
    generate_skill_workflow_yaml,
)


class TestSyncConfigParsing:
    def test_no_sync_section_returns_default(self, tmp_path: Path) -> None:
        adapter = tmp_path / "adapter.toml"
        adapter.write_text('[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n', encoding="utf-8")
        cfg = load_sync_config(adapter)
        assert cfg.enabled is False
        assert cfg.source_remote == "origin"

    def test_enabled_true(self, tmp_path: Path) -> None:
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[sync]\nenabled = true\nsource_remote = "gitlab"\nmirror_remote = "github"\nmirror_url = "github.com/org/repo"\n',
            encoding="utf-8",
        )
        cfg = load_sync_config(adapter)
        assert cfg.enabled is True
        assert cfg.source_remote == "gitlab"
        assert cfg.mirror_remote == "github"
        assert cfg.mirror_url == "github.com/org/repo"

    def test_strict_rejects_unknown_keys(self, tmp_path: Path) -> None:
        adapter = tmp_path / "adapter.toml"
        adapter.write_text('[sync]\nenabled = true\nbogus = "x"\n', encoding="utf-8")
        with pytest.raises(ValueError, match="unknown key"):
            load_sync_config(adapter, strict=True)

    def test_nonexistent_file_returns_default(self, tmp_path: Path) -> None:
        cfg = load_sync_config(tmp_path / "nope.toml")
        assert cfg.enabled is False


# ---------------------------------------------------------------------------
# SyncConfig serialization
# ---------------------------------------------------------------------------

class TestSyncConfigDump:
    def test_roundtrip(self) -> None:
        original = SyncConfig(enabled=True, source_remote="gitlab", mirror_remote="github", mirror_url="github.com/a/b")
        text = dump_sync_toml(original)
        assert "[sync]" in text
        assert "enabled = true" in text
        assert 'mirror_url = "github.com/a/b"' in text

    def test_disabled_omits_mirror_fields(self) -> None:
        cfg = SyncConfig(enabled=False)
        text = dump_sync_toml(cfg)
        assert "enabled = false" in text
        assert "mirror_remote" not in text
        assert "mirror_url" not in text


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------

class TestGitlabCiTemplate:
    def test_includes_sync_job(self) -> None:
        sync = SyncConfig(enabled=True, source_remote="gitlab", mirror_remote="github", mirror_url="github.com/o/r")
        ci = generate_gitlab_ci_yml(sync)
        assert "sync-to-github" in ci
        assert "github.com/o/r" in ci
        assert "GITHUB_TOKEN" in ci
        assert "health-check" in ci
        assert "needs: [test, health-check]" in ci

    def test_uses_custom_mirror_remote(self) -> None:
        sync = SyncConfig(enabled=True, mirror_remote="gitlab-mirror", mirror_url="gitlab.com/o/r")
        ci = generate_gitlab_ci_yml(sync)
        assert "sync-to-gitlab-mirror" in ci


class TestSkillWorkflowTemplate:
    def test_enabled_produces_three_skill_flow(self) -> None:
        sync = SyncConfig(enabled=True, source_remote="gitlab", mirror_remote="github")
        workflow = generate_skill_workflow_yaml(sync)
        assert "submit_gitlab" in workflow
        assert "merge_after_ci" in workflow
        assert "sync_github" in workflow
        assert "require_pipeline_jobs: [\"test\", \"health-check\"]" in workflow

    def test_disabled_returns_empty(self) -> None:
        sync = SyncConfig(enabled=False)
        assert generate_skill_workflow_yaml(sync) == ""


class TestAgentsMdSyncBlock:
    def test_enabled_produces_block(self) -> None:
        sync = SyncConfig(enabled=True, source_remote="gitlab", mirror_remote="github")
        block = generate_agents_md_sync_block(sync)
        assert "SYNC_IRON_RULE_BEGIN" in block
        assert "gitlab" in block
        assert "github" in block

    def test_disabled_returns_empty(self) -> None:
        sync = SyncConfig(enabled=False)
        assert generate_agents_md_sync_block(sync) == ""


class TestContributingSyncBlock:
    def test_enabled_produces_section(self) -> None:
        sync = SyncConfig(enabled=True, source_remote="gitlab", mirror_remote="github")
        block = generate_contributing_sync_block(sync)
        assert "Sync Rule" in block
        assert "gitlab" in block

    def test_disabled_returns_empty(self) -> None:
        sync = SyncConfig(enabled=False)
        assert generate_contributing_sync_block(sync) == ""


# ---------------------------------------------------------------------------
# Integration: memory-init --sync
# ---------------------------------------------------------------------------

class TestInitWithSync:
    def _make_target(self, tmp_path: Path) -> Path:
        target = tmp_path / "project"
        target.mkdir()
        (target / ".claude").mkdir()
        return target

    def test_sync_generates_ci_file(self, tmp_path: Path) -> None:
        from memory_core.tools.init_project_memory import init_project_memory

        target = self._make_target(tmp_path)
        result = init_project_memory(
            target,
            host="factory",
            sync_enabled=True,
            sync_source_remote="gitlab",
            sync_mirror_remote="github",
            sync_mirror_url="github.com/test/proj",
        )
        assert result["success"], result.get("errors")
        ci_path = target / ".gitlab-ci.yml"
        assert ci_path.is_file()
        ci = ci_path.read_text(encoding="utf-8")
        assert "sync-to-github" in ci
        assert "github.com/test/proj" in ci
        skill_path = target / "memory" / "system" / "skills" / "gitlab_sync_workflow.yaml"
        assert skill_path.is_file()
        skill_content = skill_path.read_text(encoding="utf-8")
        assert "submit_gitlab" in skill_content

    def test_sync_writes_adapter_section(self, tmp_path: Path) -> None:
        from memory_core.tools.init_project_memory import init_project_memory

        target = self._make_target(tmp_path)
        result = init_project_memory(
            target,
            host="factory",
            sync_enabled=True,
            sync_source_remote="gitlab",
            sync_mirror_remote="github",
            sync_mirror_url="github.com/test/proj",
        )
        assert result["success"]
        adapter = target / "memory" / "system" / "adapter.toml"
        assert adapter.is_file()
        content = adapter.read_text(encoding="utf-8")
        assert "[sync]" in content
        assert "enabled = true" in content

    def test_no_sync_skips_ci(self, tmp_path: Path) -> None:
        from memory_core.tools.init_project_memory import init_project_memory

        target = self._make_target(tmp_path)
        result = init_project_memory(target, host="factory")
        assert result["success"]
        assert not (target / ".gitlab-ci.yml").exists()
        assert not (target / "memory" / "system" / "skills" / "gitlab_sync_workflow.yaml").exists()
