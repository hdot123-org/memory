"""Tests for template generation functions."""

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools.template_sync import generate_skill_memory_init_fill_yaml

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
