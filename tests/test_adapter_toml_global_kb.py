"""Tests for adapter.toml [global_kb] section schema support.

Covers VAL-CONFIG-001 through VAL-CONFIG-005:
- [global_kb] section correctly parsed into AdapterConfig fields
- Default values when section is absent (backward compat)
- enabled=false correctly read
- root with ~ expanded to absolute path
- strict mode rejects unknown keys, non-strict ignores
- dump_adapter_toml serializes [global_kb] section
"""


import textwrap
from pathlib import Path

import pytest

from memory_core.tools.adapter_toml_schema import (
    AdapterConfig,
    dump_adapter_toml,
    load_adapter_toml,
)

# ── helpers ──────────────────────────────────────────────────────


def _write_toml(tmp_path: Path, content: str) -> Path:
    """Write *content* to a temporary adapter.toml and return its path."""
    toml_path = tmp_path / "adapter.toml"
    toml_path.write_text(content, encoding="utf-8")
    return toml_path


# ── VAL-CONFIG-001: [global_kb] 段被正确解析 ──────────────────────


class TestGlobalKbSectionParsed:
    """[global_kb] section is correctly parsed into AdapterConfig fields."""

    def test_global_kb_section_parsed(self, tmp_path: Path) -> None:
        """[global_kb] 段正确解析为 AdapterConfig 字段,root 含 ~ 展开为绝对路径。"""
        toml = textwrap.dedent("""\
            [core]
            version = "0.7.0"
            adapter = "default"

            [policy]
            legality_source_policy = "map-only"
            registration_commit_policy = "same-commit"
            registration_commit_phase = "post"

            [routing]
            project_name = "test-proj"
            project_scope = "test-scope"
            host = "factory"
            canonical_files = []

            [global_kb]
            enabled = true
            root = "~/.memory/global-kb"
        """)
        path = _write_toml(tmp_path, toml)
        cfg = load_adapter_toml(path)

        assert cfg.global_kb_enabled is True
        # ~ should be expanded to absolute path
        assert cfg.global_kb_root == str(Path("~/.memory/global-kb").expanduser())
        assert "~" not in cfg.global_kb_root

    def test_global_kb_enabled_false_parsed(self, tmp_path: Path) -> None:
        """enabled=false 被正确读取。"""
        toml = textwrap.dedent("""\
            [core]
            version = "0.7.0"
            adapter = "default"

            [routing]
            project_name = "test-proj"
            project_scope = "test-scope"
            host = "factory"
            canonical_files = []

            [global_kb]
            enabled = false
            root = "~/.memory/global-kb"
        """)
        path = _write_toml(tmp_path, toml)
        cfg = load_adapter_toml(path)

        assert cfg.global_kb_enabled is False


# ── VAL-CONFIG-002: 无段时用默认值 ────────────────────────────────


class TestGlobalKbDefaults:
    """Default values when [global_kb] section is absent (backward compat)."""

    def test_global_kb_defaults_when_absent(self, tmp_path: Path) -> None:
        """无 [global_kb] 段时用默认值不报错。"""
        toml = textwrap.dedent("""\
            [core]
            version = "0.7.0"
            adapter = "default"

            [routing]
            project_name = "test-proj"
            project_scope = "test-scope"
            host = "factory"
            canonical_files = []
        """)
        path = _write_toml(tmp_path, toml)
        cfg = load_adapter_toml(path)

        assert cfg.global_kb_enabled is True
        assert cfg.global_kb_root == str(Path("~/.memory/global-kb").expanduser())

    def test_global_kb_defaults_for_empty_toml(self, tmp_path: Path) -> None:
        """Empty adapter.toml also gets defaults for global_kb fields."""
        path = _write_toml(tmp_path, "")
        cfg = load_adapter_toml(path)

        assert cfg.global_kb_enabled is True
        assert cfg.global_kb_root == str(Path("~/.memory/global-kb").expanduser())

    def test_global_kb_partial_section_uses_defaults(self, tmp_path: Path) -> None:
        """[global_kb] with only enabled, root should use default."""
        toml = textwrap.dedent("""\
            [core]
            version = "0.7.0"
            adapter = "default"

            [routing]
            project_name = "test-proj"
            project_scope = "test-scope"
            host = "factory"
            canonical_files = []

            [global_kb]
            enabled = false
        """)
        path = _write_toml(tmp_path, toml)
        cfg = load_adapter_toml(path)

        assert cfg.global_kb_enabled is False
        # root not specified, should use default
        assert cfg.global_kb_root == str(Path("~/.memory/global-kb").expanduser())


# ── VAL-CONFIG-003: enabled=false 禁用 ────────────────────────────


class TestGlobalKbDisabled:
    """enabled=false is correctly read (covered by parsing tests above)."""

    def test_global_kb_disabled_when_false(self, tmp_path: Path) -> None:
        """enabled=false 被正确读取,全局 KB 禁用。"""
        toml = textwrap.dedent("""\
            [core]
            version = "0.7.0"
            adapter = "default"

            [routing]
            project_name = "test-proj"
            project_scope = "test-scope"
            host = "factory"
            canonical_files = []

            [global_kb]
            enabled = false
            root = "/custom/path"
        """)
        path = _write_toml(tmp_path, toml)
        cfg = load_adapter_toml(path)

        assert cfg.global_kb_enabled is False
        assert cfg.global_kb_root == "/custom/path"


# ── VAL-CONFIG-004: root 含 ~ 展开 ────────────────────────────────


class TestGlobalKbTildeExpansion:
    """root with ~ is expanded to absolute path."""

    def test_global_kb_root_expands_tilde(self, tmp_path: Path) -> None:
        """root 含 ~ 时展开为绝对路径。"""
        toml = textwrap.dedent("""\
            [core]
            version = "0.7.0"
            adapter = "default"

            [routing]
            project_name = "test-proj"
            project_scope = "test-scope"
            host = "factory"
            canonical_files = []

            [global_kb]
            enabled = true
            root = "~/custom/global-kb"
        """)
        path = _write_toml(tmp_path, toml)
        cfg = load_adapter_toml(path)

        expected = str(Path("~/custom/global-kb").expanduser())
        assert cfg.global_kb_root == expected
        assert "~" not in cfg.global_kb_root

    def test_global_kb_root_absolute_path_unchanged(self, tmp_path: Path) -> None:
        """Absolute path (no ~) is kept as-is."""
        toml = textwrap.dedent("""\
            [core]
            version = "0.7.0"
            adapter = "default"

            [routing]
            project_name = "test-proj"
            project_scope = "test-scope"
            host = "factory"
            canonical_files = []

            [global_kb]
            enabled = true
            root = "/absolute/path/to/kb"
        """)
        path = _write_toml(tmp_path, toml)
        cfg = load_adapter_toml(path)

        assert cfg.global_kb_root == "/absolute/path/to/kb"


# ── VAL-CONFIG-004 (strict): 严格模式拒绝未知字段 ─────────────────


class TestGlobalKbStrictMode:
    """Strict mode rejects unknown keys in [global_kb]; non-strict ignores."""

    def test_global_kb_unknown_key_strict(self, tmp_path: Path) -> None:
        """strict 模式拒绝未知字段。"""
        toml = textwrap.dedent("""\
            [core]
            version = "0.7.0"
            adapter = "default"

            [routing]
            project_name = "test-proj"
            project_scope = "test-scope"
            host = "factory"
            canonical_files = []

            [global_kb]
            enabled = true
            root = "~/.memory/global-kb"
            unknown_field = "bad"
        """)
        path = _write_toml(tmp_path, toml)
        with pytest.raises(ValueError, match=r"unknown key in \[global_kb\]: unknown_field"):
            load_adapter_toml(path, strict=True)

    def test_global_kb_unknown_key_non_strict_ignored(self, tmp_path: Path) -> None:
        """非 strict 模式忽略未知字段。"""
        toml = textwrap.dedent("""\
            [core]
            version = "0.7.0"
            adapter = "default"

            [routing]
            project_name = "test-proj"
            project_scope = "test-scope"
            host = "factory"
            canonical_files = []

            [global_kb]
            enabled = true
            root = "~/.memory/global-kb"
            unknown_field = "ignored"
        """)
        path = _write_toml(tmp_path, toml)
        cfg = load_adapter_toml(path, strict=False)

        assert cfg.global_kb_enabled is True
        # unknown field silently ignored


# ── VAL-CONFIG-005: dump 序列化 ────────────────────────────────────


class TestDumpGlobalKbSection:
    """dump_adapter_toml correctly serializes [global_kb] section."""

    def test_dump_global_kb_section(self) -> None:
        """dump_adapter_toml 正确序列化 [global_kb] 段。"""
        cfg = AdapterConfig(
            project_name="test",
            project_scope="scope",
            global_kb_enabled=True,
            global_kb_root=str(Path("~/.memory/global-kb").expanduser()),
        )
        text = dump_adapter_toml(cfg)

        assert "[global_kb]" in text
        assert "enabled = true" in text
        assert "root =" in text

    def test_dump_global_kb_disabled(self) -> None:
        """dump_adapter_toml serializes enabled=false correctly."""
        cfg = AdapterConfig(
            project_name="test",
            project_scope="scope",
            global_kb_enabled=False,
            global_kb_root="/custom/path",
        )
        text = dump_adapter_toml(cfg)

        assert "[global_kb]" in text
        assert "enabled = false" in text
        assert 'root = "/custom/path"' in text

    def test_dump_global_kb_roundtrip(self, tmp_path: Path) -> None:
        """Dump then load preserves global_kb fields."""
        original = AdapterConfig(
            project_name="rt",
            project_scope="test",
            global_kb_enabled=True,
            global_kb_root="/tmp/global-kb",
        )
        text = dump_adapter_toml(original)

        p = tmp_path / "adapter.toml"
        p.write_text(text)
        loaded = load_adapter_toml(p)

        assert loaded.global_kb_enabled == original.global_kb_enabled
        assert loaded.global_kb_root == original.global_kb_root


# ── AdapterConfig dataclass: new fields ──────────────────────────


class TestAdapterConfigGlobalKbFields:
    """AdapterConfig dataclass has global_kb_enabled and global_kb_root."""

    def test_default_global_kb_enabled(self) -> None:
        """Default global_kb_enabled is True."""
        cfg = AdapterConfig(project_name="n", project_scope="s")
        assert cfg.global_kb_enabled is True

    def test_default_global_kb_root(self) -> None:
        """Default global_kb_root is ~/.memory/global-kb (expanded)."""
        cfg = AdapterConfig(project_name="n", project_scope="s")
        expected = str(Path("~/.memory/global-kb").expanduser())
        assert cfg.global_kb_root == expected

    def test_global_kb_fields_in_constructor(self) -> None:
        """Constructor accepts global_kb fields."""
        cfg = AdapterConfig(
            project_name="n",
            project_scope="s",
            global_kb_enabled=False,
            global_kb_root="/custom",
        )
        assert cfg.global_kb_enabled is False
        assert cfg.global_kb_root == "/custom"
