"""Tests for canonical template schema alignment.

Verifies that workspace/templates/.memory/adapter.toml uses the canonical
[core] + [policy] + [routing] layout, and that init_project_memory correctly
renders placeholders into actual values.

Test cases:
1. test_template_adapter_toml_uses_canonical_layout
2. test_template_version_is_placeholder_not_hardcoded
3. test_init_writes_current_memory_version_into_adapter_toml
4. test_init_writes_user_scope_into_adapter_toml
5. test_init_writes_user_host_into_adapter_toml
6. test_init_default_host_is_codex_when_unspecified
"""
from __future__ import annotations

from pathlib import Path

from memory_core.constants import CURRENT_MEMORY_VERSION
from memory_core.tools.init_project_memory import (
    init_project_memory,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE_PATH = _REPO_ROOT / "workspace" / "templates" / ".memory" / "adapter.toml"


def _read_template_raw() -> str:
    """Read the raw adapter.toml template (before placeholder substitution)."""
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests: Template file uses canonical layout
# ---------------------------------------------------------------------------

class TestTemplateCanonicalLayout:
    """Step 3 Test 1: Template file contains canonical sections, no legacy."""

    def test_template_adapter_toml_uses_canonical_layout(self) -> None:
        """Template raw content must contain [core]/[policy]/[routing] sections
        and must NOT contain the legacy [adapter] section or legacy fields."""
        raw = _read_template_raw()

        # Canonical sections must be present
        assert "[core]" in raw, "Template missing [core] section"
        assert "[policy]" in raw, "Template missing [policy] section"
        assert "[routing]" in raw, "Template missing [routing] section"

        # Legacy section must NOT be present
        # Match exactly [adapter] but not [adapter.policy] etc.
        for line in raw.splitlines():
            stripped = line.strip()
            assert stripped != "[adapter]", (
                "Template still contains legacy [adapter] section header"
            )

        # Legacy field names must NOT be present anywhere
        assert "read_scope" not in raw, "Template contains legacy read_scope field"
        assert "write_scope" not in raw, "Template contains legacy write_scope field"
        assert "deny_write" not in raw, "Template contains legacy deny_write field"
        assert "max_context_tokens" not in raw, "Template contains legacy max_context_tokens"
        assert "cache_enabled" not in raw, "Template contains legacy cache_enabled"


class TestTemplatePlaceholder:
    """Step 3 Test 2: Template uses placeholder, not hardcoded version."""

    def test_template_version_is_placeholder_not_hardcoded(self) -> None:
        """Template raw content must contain {{memory_version}} placeholder
        and must NOT contain a hardcoded version number like '0.2.0'."""
        raw = _read_template_raw()

        assert "{{memory_version}}" in raw, (
            "Template must use {{memory_version}} placeholder"
        )

        # The version line should be the placeholder, not a concrete version
        # Check that the [core] section doesn't have a hardcoded version
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("version = "):
                # Should be the placeholder form, not a quoted version number
                assert "{{memory_version}}" in stripped, (
                    f"Version should use placeholder, found: {stripped}"
                )


# ---------------------------------------------------------------------------
# Tests: init writes correct values into adapter.toml
# ---------------------------------------------------------------------------

class TestInitWritesAdapterToml:
    """Step 3 Tests 3-6: init_project_memory renders correct values."""

    def test_init_writes_current_memory_version_into_adapter_toml(
        self, tmp_path: Path,
    ) -> None:
        """After init, adapter.toml core.version == CURRENT_MEMORY_VERSION."""
        result = init_project_memory(tmp_path, scope="version-test")
        assert result["success"] is True

        adapter_path = tmp_path / ".memory" / "adapter.toml"
        assert adapter_path.exists()
        content = adapter_path.read_text(encoding="utf-8")

        # core.version should match CURRENT_MEMORY_VERSION
        assert f'version = "{CURRENT_MEMORY_VERSION}"' in content

    def test_init_writes_user_scope_into_adapter_toml(
        self, tmp_path: Path,
    ) -> None:
        """Init with --scope my-test-proj should set routing.project_scope."""
        result = init_project_memory(tmp_path, scope="my-test-proj")
        assert result["success"] is True

        adapter_path = tmp_path / ".memory" / "adapter.toml"
        assert adapter_path.exists()
        content = adapter_path.read_text(encoding="utf-8")

        # project_scope should be the slugified version
        assert 'project_scope = "my_test_proj"' in content
        assert 'project_name = "my_test_proj"' in content

    def test_init_writes_user_host_into_adapter_toml(
        self, tmp_path: Path,
    ) -> None:
        """Init with --host claude should set routing.host = claude."""
        result = init_project_memory(tmp_path, scope="host-test", host="claude")
        assert result["success"] is True

        adapter_path = tmp_path / ".memory" / "adapter.toml"
        assert adapter_path.exists()
        content = adapter_path.read_text(encoding="utf-8")

        assert 'host = "claude"' in content

    def test_init_default_host_is_codex_when_unspecified(
        self, tmp_path: Path,
    ) -> None:
        """When --host is not provided, host should default to codex."""
        result = init_project_memory(tmp_path, scope="default-host-test")
        assert result["success"] is True

        adapter_path = tmp_path / ".memory" / "adapter.toml"
        assert adapter_path.exists()
        content = adapter_path.read_text(encoding="utf-8")

        assert 'host = "codex"' in content
