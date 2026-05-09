"""Tests for adapter.toml schema and loader (P4a)."""

from __future__ import annotations

import textwrap
from pathlib import Path

from memory_core.constants import CURRENT_MEMORY_VERSION
from memory_core.tools.adapter_toml_schema import (
    AdapterConfig,
    dump_adapter_toml,
    load_adapter_toml,
)

# ── load_adapter_toml (legacy [adapter] section) ──────────────────


class TestLoadAdapterTomlLegacy:
    """Loading from the legacy single [adapter] section."""

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        cfg = load_adapter_toml(tmp_path / "nope.toml")
        assert cfg.project_name == ""
        assert cfg.project_scope == ""
        assert cfg.host == "codex"
        assert cfg.adapter_version == CURRENT_MEMORY_VERSION
        assert cfg.canonical_files == []
        assert cfg.artifact_root is None

    def test_loads_full_config(self, tmp_path: Path) -> None:
        toml = textwrap.dedent("""\
            [adapter]
            project_name = "my-app"
            project_scope = "backend"
            host = "neovim"
            adapter_version = "2.0.0"
            canonical_files = ["README.md", "pyproject.toml"]
            artifact_root = "/tmp/artifacts"
        """)
        p = tmp_path / "adapter.toml"
        p.write_text(toml)

        cfg = load_adapter_toml(p)
        assert cfg.project_name == "my-app"
        assert cfg.project_scope == "backend"
        assert cfg.host == "neovim"
        assert cfg.adapter_version == "2.0.0"
        assert cfg.canonical_files == ["README.md", "pyproject.toml"]
        assert cfg.artifact_root == "/tmp/artifacts"

    def test_partial_config_uses_defaults(self, tmp_path: Path) -> None:
        toml = textwrap.dedent("""\
            [adapter]
            project_name = "minimal"
            project_scope = "scope"
        """)
        p = tmp_path / "adapter.toml"
        p.write_text(toml)

        cfg = load_adapter_toml(p)
        assert cfg.project_name == "minimal"
        assert cfg.host == "codex"
        assert cfg.adapter_version == CURRENT_MEMORY_VERSION
        assert cfg.canonical_files == []
        assert cfg.artifact_root is None

    def test_empty_toml_returns_defaults(self, tmp_path: Path) -> None:
        p = tmp_path / "adapter.toml"
        p.write_text("")

        cfg = load_adapter_toml(p)
        assert cfg.project_name == ""
        assert cfg.host == "codex"


# ── load_adapter_toml (canonical [core]/[policy]/[routing]) ────────


class TestLoadAdapterTomlCanonical:
    """Loading from the canonical multi-section layout."""

    def test_loads_canonical_format(self, tmp_path: Path) -> None:
        toml = textwrap.dedent("""\
            [core]
            version = "0.2.0"
            adapter = "default"

            [policy]
            legality_source_policy = "map-only"
            registration_commit_policy = "same-commit"
            registration_commit_phase = "post"

            [routing]
            project_name = "my-proj"
            project_scope = "backend"
            host = "codex"
        """)
        p = tmp_path / "adapter.toml"
        p.write_text(toml)

        cfg = load_adapter_toml(p)
        assert cfg.project_name == "my-proj"
        assert cfg.project_scope == "backend"
        assert cfg.host == "codex"
        assert cfg.adapter_version == "0.2.0"
        assert cfg.legality_source_policy == "map-only"
        assert cfg.registration_commit_policy == "same-commit"
        assert cfg.registration_commit_phase == "post"

    def test_canonical_without_project_name_falls_back_to_scope(self, tmp_path: Path) -> None:
        """When routing.project_name is missing, project_scope is used."""
        toml = textwrap.dedent("""\
            [core]
            version = "0.1.0"

            [routing]
            project_scope = "fallback-scope"
            host = "codex"
        """)
        p = tmp_path / "adapter.toml"
        p.write_text(toml)

        cfg = load_adapter_toml(p)
        assert cfg.project_name == "fallback-scope"
        assert cfg.project_scope == "fallback-scope"

    def test_canonical_policy_defaults(self, tmp_path: Path) -> None:
        """Missing [policy] section yields defaults."""
        toml = textwrap.dedent("""\
            [core]
            version = "0.1.0"

            [routing]
            project_scope = "s"
        """)
        p = tmp_path / "adapter.toml"
        p.write_text(toml)

        cfg = load_adapter_toml(p)
        assert cfg.legality_source_policy == "map-only"
        assert cfg.registration_commit_policy == "same-commit"
        assert cfg.registration_commit_phase == "post"


# ── dump_adapter_toml ──────────────────────────────────────────────


class TestDumpAdapterToml:
    """Serialisation to TOML string."""

    def test_dump_contains_core_section(self) -> None:
        cfg = AdapterConfig(project_name="x", project_scope="y")
        text = dump_adapter_toml(cfg)
        assert "[core]" in text
        assert "[policy]" in text
        assert "[routing]" in text

    def test_dump_roundtrip(self, tmp_path: Path) -> None:
        original = AdapterConfig(
            project_name="rt",
            project_scope="test",
            host="vscode",
            adapter_version="1.2.3",
            canonical_files=["a.md", "b.md"],
            artifact_root="/out",
        )
        text = dump_adapter_toml(original)

        p = tmp_path / "adapter.toml"
        p.write_text(text)
        loaded = load_adapter_toml(p)

        assert loaded == original

    def test_dump_default_artifact_root_comment(self) -> None:
        cfg = AdapterConfig(project_name="a", project_scope="b")
        text = dump_adapter_toml(cfg)
        assert "# artifact_root is not set" in text

    def test_dump_artifact_root_present(self) -> None:
        cfg = AdapterConfig(
            project_name="a",
            project_scope="b",
            artifact_root="/tmp",
        )
        text = dump_adapter_toml(cfg)
        assert 'artifact_root = "/tmp"' in text

    def test_roundtrip_with_special_chars(self, tmp_path: Path) -> None:
        """Backslash and quote in values survive roundtrip."""
        original = AdapterConfig(
            project_name='say "hello"',
            project_scope="C:\\Users\\test",
        )
        text = dump_adapter_toml(original)
        p = tmp_path / "adapter.toml"
        p.write_text(text)
        loaded = load_adapter_toml(p)
        assert loaded.project_name == 'say "hello"'
        assert loaded.project_scope == "C:\\Users\\test"

    def test_dump_contains_field_values(self) -> None:
        """Dumped text includes project routing values."""
        cfg = AdapterConfig(project_name="alpha", project_scope="beta")
        text = dump_adapter_toml(cfg)
        assert 'project_name = "alpha"' in text
        assert 'project_scope = "beta"' in text


# ── AdapterConfig dataclass ────────────────────────────────────────


class TestAdapterConfigDataclass:
    """Dataclass construction and defaults."""

    def test_defaults(self) -> None:
        cfg = AdapterConfig(project_name="n", project_scope="s")
        assert cfg.host == "codex"
        assert cfg.adapter_version == CURRENT_MEMORY_VERSION
        assert cfg.canonical_files == []
        assert cfg.artifact_root is None

    def test_policy_defaults(self) -> None:
        cfg = AdapterConfig(project_name="n", project_scope="s")
        assert cfg.legality_source_policy == "map-only"
        assert cfg.registration_commit_policy == "same-commit"
        assert cfg.registration_commit_phase == "post"

    def test_list_default_is_independent(self) -> None:
        a = AdapterConfig(project_name="a", project_scope="b")
        b = AdapterConfig(project_name="c", project_scope="d")
        a.canonical_files.append("x")
        assert b.canonical_files == []

    def test_equality(self) -> None:
        a = AdapterConfig(project_name="a", project_scope="b")
        b = AdapterConfig(project_name="a", project_scope="b")
        assert a == b
