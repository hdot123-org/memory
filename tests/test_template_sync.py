"""Tests for ShowDoc template generation functions."""
from __future__ import annotations

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools.adapter_toml_schema import ShowdocSyncConfig, SyncConfig
from memory_core.tools.template_sync import (
    generate_agents_md_showdoc_block,
    generate_contributing_showdoc_block,
    generate_gitlab_ci_showdoc_job,
    generate_skill_memory_init_fill_yaml,
    generate_skill_showdoc_workflow_yaml,
)

# ---------------------------------------------------------------------------
# generate_gitlab_ci_showdoc_job tests (VAL-TMPL-001, VAL-TMPL-002)
# ---------------------------------------------------------------------------

class TestGenerateGitlabCiShowdocJob:
    """Tests for generate_gitlab_ci_showdoc_job() CI YAML generation."""

    def test_produces_sync_to_showdoc_job(self) -> None:
        """VAL-TMPL-001: Produces YAML with sync-to-showdoc job in sync stage."""
        sync = SyncConfig(enabled=True, source_remote="gitlab")
        showdoc = ShowdocSyncConfig(enabled=True, item_id=123)
        yaml_text = generate_gitlab_ci_showdoc_job(sync, showdoc)
        assert "sync-to-showdoc" in yaml_text
        assert "stage: sync" in yaml_text

    def test_has_needs_test_health_check(self) -> None:
        """VAL-TMPL-001: Job depends on test and health-check."""
        sync = SyncConfig(enabled=True)
        showdoc = ShowdocSyncConfig(enabled=True)
        yaml = generate_gitlab_ci_showdoc_job(sync, showdoc)
        assert "needs: [test, health-check]" in yaml

    def test_main_branch_rule(self) -> None:
        """VAL-TMPL-001: Job restricted to main branch."""
        sync = SyncConfig(enabled=True)
        showdoc = ShowdocSyncConfig(enabled=True)
        yaml = generate_gitlab_ci_showdoc_job(sync, showdoc)
        assert '$CI_COMMIT_BRANCH == "main"' in yaml
        assert '$CI_PIPELINE_SOURCE == "push"' in yaml

    def test_script_installs_requests_and_runs_sync(self) -> None:
        """VAL-TMPL-001: Script contains pip install requests + python scripts/sync_to_showdoc.py."""
        sync = SyncConfig(enabled=True)
        showdoc = ShowdocSyncConfig(enabled=True)
        yaml = generate_gitlab_ci_showdoc_job(sync, showdoc)
        assert "pip install requests" in yaml
        assert "python scripts/sync_to_showdoc.py" in yaml

    def test_references_required_ci_variables(self) -> None:
        """VAL-TMPL-002: CI job YAML references SHOWDOC_API_KEY, SHOWDOC_API_TOKEN, SHOWDOC_URL."""
        sync = SyncConfig(enabled=True)
        showdoc = ShowdocSyncConfig(enabled=True)
        yaml = generate_gitlab_ci_showdoc_job(sync, showdoc)
        assert "SHOWDOC_API_KEY" in yaml
        assert "SHOWDOC_API_TOKEN" in yaml
        assert "SHOWDOC_URL" in yaml

    def test_returns_empty_when_showdoc_disabled(self) -> None:
        """VAL-TMPL-005: Returns empty string when showdoc.enabled=False."""
        sync = SyncConfig(enabled=True)
        showdoc = ShowdocSyncConfig(enabled=False)
        assert generate_gitlab_ci_showdoc_job(sync, showdoc) == ""


# ---------------------------------------------------------------------------
# generate_agents_md_showdoc_block tests (VAL-TMPL-003)
# ---------------------------------------------------------------------------

class TestGenerateAgentsMdShowdocBlock:
    """Tests for generate_agents_md_showdoc_block() AGENTS.md iron rule block."""

    def test_produces_content_with_markers(self) -> None:
        """VAL-TMPL-003: Content wrapped in SYNC_SHOWDOC_BEGIN/END markers."""
        showdoc = ShowdocSyncConfig(enabled=True, item_id=123)
        block = generate_agents_md_showdoc_block(showdoc)
        assert "<!-- SYNC_SHOWDOC_BEGIN -->" in block
        assert "<!-- SYNC_SHOWDOC_END -->" in block

    def test_mentions_showdoc_as_readonly_mirror(self) -> None:
        """VAL-TMPL-003: Content mentions ShowDoc as read-only mirror."""
        showdoc = ShowdocSyncConfig(enabled=True)
        block = generate_agents_md_showdoc_block(showdoc)
        assert "只读镜像" in block

    def test_includes_item_id(self) -> None:
        """Block includes the configured item_id."""
        showdoc = ShowdocSyncConfig(enabled=True, item_id=664858316)
        block = generate_agents_md_showdoc_block(showdoc)
        assert "664858316" in block

    def test_returns_empty_when_disabled(self) -> None:
        """VAL-TMPL-005: Returns empty string when showdoc.enabled=False."""
        showdoc = ShowdocSyncConfig(enabled=False)
        assert generate_agents_md_showdoc_block(showdoc) == ""


# ---------------------------------------------------------------------------
# generate_contributing_showdoc_block tests (VAL-TMPL-004)
# ---------------------------------------------------------------------------

class TestGenerateContributingShowdocBlock:
    """Tests for generate_contributing_showdoc_block() CONTRIBUTING.md section."""

    def test_produces_markdown_section(self) -> None:
        """VAL-TMPL-004: Produces a markdown section about ShowDoc sync rules."""
        showdoc = ShowdocSyncConfig(enabled=True, item_id=456)
        block = generate_contributing_showdoc_block(showdoc)
        assert "ShowDoc" in block
        assert "同步" in block
        assert "item_id" in block or "456" in block

    def test_has_rules_table(self) -> None:
        """Section contains a rules table."""
        showdoc = ShowdocSyncConfig(enabled=True)
        block = generate_contributing_showdoc_block(showdoc)
        assert "| 规则 |" in block or "| Rule" in block or "| 规则" in block

    def test_returns_empty_when_disabled(self) -> None:
        """VAL-TMPL-005: Returns empty string when showdoc.enabled=False."""
        showdoc = ShowdocSyncConfig(enabled=False)
        assert generate_contributing_showdoc_block(showdoc) == ""


# ---------------------------------------------------------------------------
# generate_skill_showdoc_workflow_yaml tests (VAL-TMPL-006)
# ---------------------------------------------------------------------------

class TestGenerateSkillShowdocWorkflowYaml:
    """Tests for generate_skill_showdoc_workflow_yaml() skill workflow template."""

    def test_produces_yaml_structure(self) -> None:
        """VAL-TMPL-006: Produces YAML defining a ShowDoc sync skill."""
        showdoc = ShowdocSyncConfig(enabled=True, item_id=789)
        yaml_text = generate_skill_showdoc_workflow_yaml(showdoc)
        assert "workflow: showdoc-sync" in yaml_text
        assert "sync_to_showdoc" in yaml_text

    def test_has_correct_parameters(self) -> None:
        """VAL-TMPL-006: YAML contains correct parameters."""
        showdoc = ShowdocSyncConfig(enabled=True, item_id=789)
        yaml_text = generate_skill_showdoc_workflow_yaml(showdoc)
        assert "showdoc_item_id: 789" in yaml_text
        assert "ci_job: \"sync-to-showdoc\"" in yaml_text
        assert "require_pipeline_jobs" in yaml_text

    def test_has_sync_configuration(self) -> None:
        """YAML contains sync configuration details."""
        showdoc = ShowdocSyncConfig(enabled=True)
        yaml_text = generate_skill_showdoc_workflow_yaml(showdoc)
        assert "scripts/sync_to_showdoc.py" in yaml_text
        assert "pip install requests" in yaml_text
        assert "incremental: true" in yaml_text
        assert ".showdoc-manifest.json" in yaml_text

    def test_has_retry_config(self) -> None:
        """YAML contains retry and backoff configuration."""
        showdoc = ShowdocSyncConfig(enabled=True)
        yaml_text = generate_skill_showdoc_workflow_yaml(showdoc)
        assert "retry: 3" in yaml_text
        assert "backoff" in yaml_text

    def test_returns_empty_when_disabled(self) -> None:
        """VAL-TMPL-005: Returns empty string when showdoc.enabled=False."""
        showdoc = ShowdocSyncConfig(enabled=False)
        assert generate_skill_showdoc_workflow_yaml(showdoc) == ""

    def test_includes_core_files_when_provided(self) -> None:
        """YAML includes core_files when showdoc has them configured."""
        showdoc = ShowdocSyncConfig(
            enabled=True,
            item_id=123,
            core_files=["docs/**/*.md", "CHANGELOG.md"],
        )
        yaml_text = generate_skill_showdoc_workflow_yaml(showdoc)
        assert "docs/**/*.md" in yaml_text
        assert "CHANGELOG.md" in yaml_text

    def test_has_default_core_files_when_not_configured(self) -> None:
        """YAML includes default core_files when showdoc has none configured."""
        showdoc = ShowdocSyncConfig(enabled=True, item_id=123)
        yaml_text = generate_skill_showdoc_workflow_yaml(showdoc)
        assert "memory_core/memory/docs/system/**/*.md" in yaml_text
        assert "CHANGELOG.md" in yaml_text


# ---------------------------------------------------------------------------
# generate_skill_memory_init_fill_yaml tests (VAL-SKILL-001, VAL-SKILL-002)
# ---------------------------------------------------------------------------

class TestGenerateSkillMemoryInitFillYaml:
    """Tests for generate_skill_memory_init_fill_yaml() function."""

    def test_returns_non_empty_yaml(self) -> None:
        """VAL-SKILL-002: Function returns non-empty YAML string."""
        result = generate_skill_memory_init_fill_yaml("test_project")
        assert result  # non-empty
        assert len(result) > 0

    def test_contains_workflow_identifier(self) -> None:
        """VAL-SKILL-002: YAML contains memory-init-fill workflow identifier."""
        result = generate_skill_memory_init_fill_yaml("test_project")
        assert "memory-init-fill" in result
        assert "version: 1" in result

    def test_contains_probe_project_skill(self) -> None:
        """VAL-SKILL-002: YAML contains probe_project skill definition."""
        result = generate_skill_memory_init_fill_yaml("test_project")
        assert "probe_project" in result
        assert "探测项目元信息" in result

    def test_contains_fill_templates_skill(self) -> None:
        """VAL-SKILL-002: YAML contains fill_templates skill definition."""
        result = generate_skill_memory_init_fill_yaml("test_project")
        assert "fill_templates" in result
        assert "将探测结果写入模板文件" in result

    def test_contains_verify_skill(self) -> None:
        """YAML contains verify skill definition."""
        result = generate_skill_memory_init_fill_yaml("test_project")
        assert "verify" in result
        assert "填充后验证文件完整性" in result

    def test_contains_probe_steps(self) -> None:
        """YAML contains all probe step definitions."""
        result = generate_skill_memory_init_fill_yaml("test_project")
        for step in ["git_info", "primary_language", "framework",
                     "project_type", "database", "toolchain", "readme_summary"]:
            assert step in result

    def test_contains_fill_rules(self) -> None:
        """YAML contains fill template rules with confidence levels."""
        result = generate_skill_memory_init_fill_yaml("test_project")
        assert "confidence: \"high\"" in result
        assert "confidence: \"low\"" in result
        assert "auto_fill" in result
        assert "keep_placeholder" in result

    def test_project_name_parameter_unused(self) -> None:
        """Function returns same content regardless of project_name parameter."""
        result_a = generate_skill_memory_init_fill_yaml("project_a")
        result_b = generate_skill_memory_init_fill_yaml("project_b")
        assert result_a == result_b  # static content, no variable substitution
