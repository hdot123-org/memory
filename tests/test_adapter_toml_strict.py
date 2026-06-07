"""Strict validation tests for load_adapter_toml."""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_core.tools.adapter_toml_schema import load_adapter_toml

# ── helpers ──────────────────────────────────────────────────────


def _write_toml(tmp_path: Path, content: str) -> Path:
    """Write *content* to a temporary adapter.toml and return its path."""
    toml_path = tmp_path / "adapter.toml"
    toml_path.write_text(content, encoding="utf-8")
    return toml_path


# ── host validation ──────────────────────────────────────────────


def test_strict_rejects_unknown_host(tmp_path: Path) -> None:
    """host='foo' in strict=True must raise ValueError."""
    toml = """\
[core]
version = "0.2.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "my-project"
project_scope = "my-scope"
host = "foo"
canonical_files = []
"""
    path = _write_toml(tmp_path, toml)
    with pytest.raises(ValueError, match=r"Unsupported host: 'foo'"):
        load_adapter_toml(path, strict=True)


def test_non_strict_warns_on_unknown_host(tmp_path: Path) -> None:
    """strict=False should only warn, not raise."""
    toml = """\
[core]
version = "0.2.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "my-project"
project_scope = "my-scope"
host = "foo"
canonical_files = []
"""
    path = _write_toml(tmp_path, toml)
    with pytest.warns(UserWarning, match="is not in SUPPORTED_HOSTS"):
        config = load_adapter_toml(path, strict=False)
    assert config.host == "foo"


# ── project_scope validation ─────────────────────────────────────


def test_strict_rejects_empty_project_scope(tmp_path: Path) -> None:
    """Empty project_scope in strict=True must raise ValueError."""
    toml = """\
[core]
version = "0.2.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "my-project"
project_scope = ""
host = "factory"
canonical_files = []
"""
    path = _write_toml(tmp_path, toml)
    with pytest.raises(ValueError, match="routing.project_scope must be non-empty"):
        load_adapter_toml(path, strict=True)


def test_strict_rejects_whitespace_project_scope(tmp_path: Path) -> None:
    """Whitespace-only project_scope in strict=True must raise ValueError."""
    toml = """\
[core]
version = "0.2.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "my-project"
project_scope = "   "
host = "factory"
canonical_files = []
"""
    path = _write_toml(tmp_path, toml)
    with pytest.raises(ValueError, match="routing.project_scope must be non-empty"):
        load_adapter_toml(path, strict=True)


# ── project_name validation ──────────────────────────────────────


def test_strict_rejects_empty_project_name(tmp_path: Path) -> None:
    """Empty project_name (with empty project_scope fallback) must raise."""
    toml = """\
[core]
version = "0.2.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = ""
project_scope = "my-scope"
host = "factory"
canonical_files = []
"""
    path = _write_toml(tmp_path, toml)
    with pytest.raises(ValueError, match="routing.project_name must be non-empty"):
        load_adapter_toml(path, strict=True)


# ── unknown key validation ───────────────────────────────────────


def test_strict_rejects_unknown_core_key(tmp_path: Path) -> None:
    """Unknown key in [core] must raise ValueError in strict mode."""
    toml = """\
[core]
version = "0.2.0"
adapter = "default"
foo = "bar"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "my-project"
project_scope = "my-scope"
host = "factory"
canonical_files = []
"""
    path = _write_toml(tmp_path, toml)
    with pytest.raises(ValueError, match=r"unknown key in \[core\]: foo"):
        load_adapter_toml(path, strict=True)


def test_strict_rejects_unknown_policy_key(tmp_path: Path) -> None:
    """Unknown key in [policy] must raise ValueError in strict mode."""
    toml = """\
[core]
version = "0.2.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"
extra_policy_setting = "value"

[routing]
project_name = "my-project"
project_scope = "my-scope"
host = "factory"
canonical_files = []
"""
    path = _write_toml(tmp_path, toml)
    with pytest.raises(ValueError, match=r"unknown key in \[policy\]: extra_policy_setting"):
        load_adapter_toml(path, strict=True)


def test_strict_rejects_unknown_routing_key(tmp_path: Path) -> None:
    """Unknown key in [routing] must raise ValueError in strict mode."""
    toml = """\
[core]
version = "0.2.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "my-project"
project_scope = "my-scope"
host = "factory"
canonical_files = []
mystery_field = "hello"
"""
    path = _write_toml(tmp_path, toml)
    with pytest.raises(ValueError, match=r"unknown key in \[routing\]: mystery_field"):
        load_adapter_toml(path, strict=True)


# ── canonical layout acceptance ──────────────────────────────────


def test_strict_accepts_canonical_layout(tmp_path: Path) -> None:
    """Canonical layout with all required fields should pass strict=True."""
    toml = """\
[core]
version = "0.2.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "my-project"
project_scope = "my-scope"
host = "factory"
canonical_files = ["CANONICAL.md", "PLAN.md"]
artifact_root = "/tmp/artifacts"
"""
    path = _write_toml(tmp_path, toml)
    config = load_adapter_toml(path, strict=True)
    assert config.project_name == "my-project"
    assert config.project_scope == "my-scope"
    assert config.host == "factory"
    assert config.adapter_version == "0.2.0"
    assert config.canonical_files == ["CANONICAL.md", "PLAN.md"]
    assert config.artifact_root == "/tmp/artifacts"


# ── backward compatibility ───────────────────────────────────────


def test_default_load_still_backward_compatible(tmp_path: Path) -> None:
    """Loading without strict parameter must work with imperfect toml."""
    toml = """\
[core]
version = "0.2.0"
adapter = "default"
unknown_field = "should-be-ignored"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"
extra_policy = "ignored"

[routing]
project_name = "my-project"
project_scope = "my-scope"
host = "factory"
canonical_files = []
extra_routing = "ignored"
"""
    path = _write_toml(tmp_path, toml)
    # Should not raise — unknown keys are silently ignored in non-strict mode
    config = load_adapter_toml(path)
    assert config.project_name == "my-project"
    assert config.project_scope == "my-scope"
    assert config.host == "factory"
