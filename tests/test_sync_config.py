"""Tests for sync configuration: SyncConfig, template_sync, init --sync."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools.adapter_toml_schema import (
    ShowdocSyncConfig,
    SyncConfig,
    dump_showdoc_toml,
    dump_sync_toml,
    load_showdoc_sync_config,
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


# ---------------------------------------------------------------------------
# ShowDoc sync configuration parsing (VAL-SCHEMA-001..006)
# ---------------------------------------------------------------------------

class TestShowdocConfigParsing:
    """Tests for ShowdocSyncConfig parsing from [sync.showdoc] section."""

    def test_showdoc_enabled_true(self, tmp_path: Path) -> None:
        """VAL-SCHEMA-001: Parse [sync.showdoc] with all fields."""
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n'
            '[sync]\nenabled = true\n'
            '[sync.showdoc]\n'
            'enabled = true\n'
            'item_id = 123\n'
            'api_url = "http://REDACTED_IP"\n'
            'core_files = ["docs/**/*.md"]\n'
            'extra_patterns = ["README.md"]\n'
            '[sync.showdoc.cat_name_mapping]\n'
            '"docs/design" = "设计文档"\n',
            encoding="utf-8",
        )
        cfg = load_sync_config(adapter)
        assert cfg.showdoc.enabled is True
        assert cfg.showdoc.item_id == 123
        assert cfg.showdoc.api_url == "http://REDACTED_IP"
        assert cfg.showdoc.core_files == ["docs/**/*.md"]
        assert cfg.showdoc.extra_patterns == ["README.md"]
        assert cfg.showdoc.cat_name_mapping == {"docs/design": "设计文档"}

    def test_showdoc_defaults_when_absent(self, tmp_path: Path) -> None:
        """VAL-SCHEMA-002: Returns ShowdocSyncConfig(enabled=False) when section missing."""
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n'
            '[sync]\nenabled = true\n',
            encoding="utf-8",
        )
        cfg = load_sync_config(adapter)
        assert cfg.showdoc.enabled is False
        assert cfg.showdoc.item_id == 0
        assert cfg.showdoc.api_url == ""
        assert cfg.showdoc.core_files == []

    def test_showdoc_strict_rejects_unknown_keys(self, tmp_path: Path) -> None:
        """VAL-SCHEMA-003: Strict mode rejects unknown keys with ValueError."""
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n'
            '[sync]\n'
            '[sync.showdoc]\n'
            'enabled = true\n'
            'bogus = "x"\n',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="unknown key"):
            load_sync_config(adapter, strict=True)

    def test_showdoc_strict_rejects_unknown_keys_via_load_showdoc(self, tmp_path: Path) -> None:
        """VAL-SCHEMA-003 variant: strict rejection via load_showdoc_sync_config."""
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n'
            '[sync]\n'
            '[sync.showdoc]\n'
            'enabled = true\n'
            'unknown_field = 42\n',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="unknown key"):
            load_showdoc_sync_config(adapter, strict=True)


class TestShowdocConfigRoundtrip:
    """Tests for ShowdocSyncConfig serialization and roundtrip."""

    def test_showdoc_roundtrip(self, tmp_path: Path) -> None:
        """VAL-SCHEMA-004: Roundtrip through dump_sync_toml -> parse preserves all fields."""
        original = ShowdocSyncConfig(
            enabled=True,
            item_id=456,
            api_url="http://REDACTED_IP",
            core_files=["docs/**/*.md", "CHANGELOG.md"],
            extra_patterns=["README.md"],
            cat_name_mapping={"docs/design": "设计文档"},
        )
        toml_text = dump_showdoc_toml(original)
        assert "[sync.showdoc]" in toml_text
        assert "enabled = true" in toml_text
        assert "item_id = 456" in toml_text
        assert 'api_url = "http://REDACTED_IP"' in toml_text

        # Write to temp file and parse back
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n'
            + toml_text,
            encoding="utf-8",
        )
        parsed = load_showdoc_sync_config(adapter)
        assert parsed.enabled is True
        assert parsed.item_id == 456
        assert parsed.api_url == "http://REDACTED_IP"
        assert parsed.core_files == ["docs/**/*.md", "CHANGELOG.md"]
        assert parsed.extra_patterns == ["README.md"]
        assert parsed.cat_name_mapping == {"docs/design": "设计文档"}

    def test_showdoc_api_url_defaults_empty(self, tmp_path: Path) -> None:
        """VAL-SCHEMA-005: api_url defaults to empty string when not set."""
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n'
            '[sync]\n'
            '[sync.showdoc]\n'
            'enabled = true\n'
            'item_id = 789\n',
            encoding="utf-8",
        )
        cfg = load_showdoc_sync_config(adapter)
        assert cfg.api_url == ""

    def test_showdoc_dataclass_defaults(self) -> None:
        """api_url defaults to empty string, core_files defaults to empty list."""
        cfg = ShowdocSyncConfig()
        assert cfg.enabled is False
        assert cfg.item_id == 0
        assert cfg.api_url == ""
        assert cfg.core_files == []
        assert cfg.extra_patterns == []
        assert cfg.cat_name_mapping == {}


class TestShowdocCoexistence:
    """VAL-SCHEMA-006: [sync] and [sync.showdoc] parse independently."""

    def test_both_sections_parse_independently(self, tmp_path: Path) -> None:
        """Both [sync] and [sync.showdoc] populated correctly."""
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n'
            '[sync]\n'
            'enabled = true\n'
            'source_remote = "gitlab"\n'
            'mirror_remote = "github"\n'
            'mirror_url = "github.com/org/repo"\n'
            '[sync.showdoc]\n'
            'enabled = true\n'
            'item_id = 664858316\n'
            'core_files = ["docs/**/*.md"]\n',
            encoding="utf-8",
        )
        cfg = load_sync_config(adapter)
        # [sync] section
        assert cfg.enabled is True
        assert cfg.source_remote == "gitlab"
        assert cfg.mirror_remote == "github"
        assert cfg.mirror_url == "github.com/org/repo"
        # [sync.showdoc] section
        assert cfg.showdoc.enabled is True
        assert cfg.showdoc.item_id == 664858316
        assert cfg.showdoc.core_files == ["docs/**/*.md"]

    def test_sync_enabled_without_showdoc(self, tmp_path: Path) -> None:
        """[sync] enabled but [sync.showdoc] absent - showdoc gets defaults."""
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n'
            '[sync]\n'
            'enabled = true\n'
            'source_remote = "origin"\n',
            encoding="utf-8",
        )
        cfg = load_sync_config(adapter)
        assert cfg.enabled is True
        assert cfg.source_remote == "origin"
        assert cfg.showdoc.enabled is False
        assert cfg.showdoc.item_id == 0

    def test_showdoc_enabled_without_sync(self, tmp_path: Path) -> None:
        """[sync.showdoc] present but [sync] disabled - both parse independently."""
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n'
            '[sync]\n'
            '[sync.showdoc]\n'
            'enabled = true\n'
            'item_id = 100\n',
            encoding="utf-8",
        )
        cfg = load_sync_config(adapter)
        assert cfg.enabled is False  # sync disabled
        assert cfg.showdoc.enabled is True  # showdoc enabled
        assert cfg.showdoc.item_id == 100


class TestLoadShowdocSyncConfigStandalone:
    """Tests for load_showdoc_sync_config standalone function."""

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Returns default when file doesn't exist."""
        cfg = load_showdoc_sync_config(tmp_path / "nope.toml")
        assert cfg.enabled is False
        assert cfg.item_id == 0
        assert cfg.api_url == ""

    def test_no_sync_section(self, tmp_path: Path) -> None:
        """Returns default when [sync] section is absent."""
        adapter = tmp_path / "adapter.toml"
        adapter.write_text('[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n', encoding="utf-8")
        cfg = load_showdoc_sync_config(adapter)
        assert cfg.enabled is False

    def test_no_showdoc_subsection(self, tmp_path: Path) -> None:
        """Returns default when [sync] exists but showdoc subsection absent."""
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n'
            '[sync]\nenabled = true\n',
            encoding="utf-8",
        )
        cfg = load_showdoc_sync_config(adapter)
        assert cfg.enabled is False
        assert cfg.item_id == 0

    def test_full_parse(self, tmp_path: Path) -> None:
        """Full parse with all fields populated."""
        adapter = tmp_path / "adapter.toml"
        adapter.write_text(
            '[core]\nversion = "0.4.0"\n[routing]\nproject_name = "x"\n'
            '[sync]\n'
            '[sync.showdoc]\n'
            'enabled = true\n'
            'item_id = 999\n'
            'api_url = "http://showdoc.local"\n'
            'core_files = ["docs/**/*.md", "README.md"]\n'
            'extra_patterns = ["*.txt"]\n',
            encoding="utf-8",
        )
        cfg = load_showdoc_sync_config(adapter)
        assert cfg.enabled is True
        assert cfg.item_id == 999
        assert cfg.api_url == "http://showdoc.local"
        assert cfg.core_files == ["docs/**/*.md", "README.md"]
        assert cfg.extra_patterns == ["*.txt"]


# ---------------------------------------------------------------------------
# ShowDoc CLI integration (VAL-CLI-001..005, VAL-CI-001..003)
# ---------------------------------------------------------------------------

class TestShowdocCliIntegration:
    """Tests for --sync-showdoc CLI flag integration (VAL-CLI-*)."""

    def _make_target(self, tmp_path: Path) -> Path:
        target = tmp_path / "project"
        target.mkdir()
        (target / ".claude").mkdir()
        return target

    def test_sync_showdoc_flag_accepted(self, tmp_path: Path) -> None:
        """VAL-CLI-001: --sync-showdoc --sync-showdoc-item-id exits 0."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = self._make_target(tmp_path)
        result = init_project_memory(
            target,
            host="factory",
            sync_showdoc_enabled=True,
            sync_showdoc_item_id=123,
            sync_showdoc_url="http://REDACTED_IP",
        )
        assert result["success"], result.get("errors")

    def test_adapter_toml_gets_showdoc_section(self, tmp_path: Path) -> None:
        """VAL-CLI-002: adapter.toml contains [sync.showdoc] with enabled=true and item_id."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = self._make_target(tmp_path)
        result = init_project_memory(
            target,
            host="factory",
            sync_showdoc_enabled=True,
            sync_showdoc_item_id=123,
        )
        assert result["success"]
        adapter = target / "memory" / "system" / "adapter.toml"
        content = adapter.read_text(encoding="utf-8")
        assert "[sync.showdoc]" in content
        assert "enabled = true" in content
        assert "item_id = 123" in content

    def test_ci_yaml_includes_showdoc_job(self, tmp_path: Path) -> None:
        """VAL-CLI-003: .gitlab-ci.yml contains sync-to-showdoc job."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = self._make_target(tmp_path)
        result = init_project_memory(
            target,
            host="factory",
            sync_showdoc_enabled=True,
            sync_showdoc_item_id=456,
        )
        assert result["success"]
        ci_path = target / ".gitlab-ci.yml"
        assert ci_path.is_file()
        ci = ci_path.read_text(encoding="utf-8")
        assert "sync-to-showdoc" in ci
        assert "stage: sync" in ci
        assert "pip install requests" in ci
        assert "python scripts/sync_to_showdoc.py" in ci

    def test_skipped_without_showdoc_flag(self, tmp_path: Path) -> None:
        """VAL-CLI-004: No ShowDoc files or sections generated without --sync-showdoc."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = self._make_target(tmp_path)
        # Only sync_enabled, NOT sync_showdoc_enabled
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
        content = adapter.read_text(encoding="utf-8")
        assert "[sync.showdoc]" not in content

        ci_path = target / ".gitlab-ci.yml"
        if ci_path.exists():
            ci = ci_path.read_text(encoding="utf-8")
            assert "sync-to-showdoc" not in ci

        showdoc_skill = target / "memory" / "system" / "skills" / "showdoc_sync_workflow.yaml"
        assert not showdoc_skill.exists()

    def test_skill_workflow_file_created(self, tmp_path: Path) -> None:
        """VAL-CLI-005: memory/system/skills/showdoc_sync_workflow.yaml created with valid content."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = self._make_target(tmp_path)
        result = init_project_memory(
            target,
            host="factory",
            sync_showdoc_enabled=True,
            sync_showdoc_item_id=789,
            sync_showdoc_url="http://showdoc.local",
        )
        assert result["success"]
        skill_path = target / "memory" / "system" / "skills" / "showdoc_sync_workflow.yaml"
        assert skill_path.is_file()
        skill_content = skill_path.read_text(encoding="utf-8")
        assert "showdoc-sync" in skill_content
        assert "showdoc_item_id: 789" in skill_content
        assert "sync_to_showdoc" in skill_content
        assert "scripts/sync_to_showdoc.py" in skill_content


class TestShowdocCliCiIntegration:
    """Tests for CI job assertions (VAL-CI-001..003)."""

    def _make_target(self, tmp_path: Path) -> Path:
        target = tmp_path / "project"
        target.mkdir()
        (target / ".claude").mkdir()
        return target

    def test_showdoc_job_in_sync_stage(self, tmp_path: Path) -> None:
        """VAL-CI-001: sync-to-showdoc job is in the sync stage."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = self._make_target(tmp_path)
        result = init_project_memory(
            target,
            host="factory",
            sync_showdoc_enabled=True,
            sync_showdoc_item_id=100,
        )
        assert result["success"]
        ci_path = target / ".gitlab-ci.yml"
        ci = ci_path.read_text(encoding="utf-8")
        # Check the sync-to-showdoc job references sync stage
        assert "sync-to-showdoc:" in ci
        assert "stage: sync" in ci

    def test_showdoc_job_has_needs(self, tmp_path: Path) -> None:
        """VAL-CI-002: sync-to-showdoc has needs: [test, health-check]."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = self._make_target(tmp_path)
        result = init_project_memory(
            target,
            host="factory",
            sync_showdoc_enabled=True,
            sync_showdoc_item_id=100,
        )
        assert result["success"]
        ci_path = target / ".gitlab-ci.yml"
        ci = ci_path.read_text(encoding="utf-8")
        assert "needs: [test, health-check]" in ci

    def test_showdoc_job_restricted_to_main(self, tmp_path: Path) -> None:
        """VAL-CI-003: Job restricted to main branch with push pipeline."""
        from memory_core.tools.init_project_memory import init_project_memory

        target = self._make_target(tmp_path)
        result = init_project_memory(
            target,
            host="factory",
            sync_showdoc_enabled=True,
            sync_showdoc_item_id=100,
        )
        assert result["success"]
        ci_path = target / ".gitlab-ci.yml"
        ci = ci_path.read_text(encoding="utf-8")
        assert '$CI_COMMIT_BRANCH == "main"' in ci
        assert '$CI_PIPELINE_SOURCE == "push"' in ci
