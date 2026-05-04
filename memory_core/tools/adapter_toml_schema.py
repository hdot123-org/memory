"""Adapter TOML schema and loader for .memory/adapter.toml configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from memory_core.constants import CURRENT_MEMORY_VERSION, SUPPORTED_HOSTS


@dataclass
class AdapterConfig:
    """Configuration loaded from ``.memory/adapter.toml``.

    The canonical TOML layout uses ``[core]``, ``[policy]``, and
    ``[routing]`` sections.  The legacy single-section ``[adapter]``
    layout is still accepted for backward compatibility.
    """

    project_name: str
    project_scope: str
    host: str = "codex"
    adapter_version: str = CURRENT_MEMORY_VERSION
    canonical_files: list[str] = field(default_factory=list)
    artifact_root: str | None = None
    # Extra fields preserved from [policy] section
    legality_source_policy: str = "map-only"
    registration_commit_policy: str = "same-commit"
    registration_commit_phase: str = "post"


# ── internal helpers ──────────────────────────────────────────────

def _toml_str(value: str) -> str:
    """Format a plain string as a TOML basic string."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _has_new_sections(data: dict[str, Any]) -> bool:
    """Return True if *data* uses the [core]/[routing] layout."""
    return "core" in data or "routing" in data


# ── public API ────────────────────────────────────────────────────


def load_adapter_toml(path: Path) -> AdapterConfig:
    """Load an :class:`AdapterConfig` from *path*.

    Supports two TOML layouts:

    * **Canonical** — ``[core]``, ``[policy]``, ``[routing]`` sections.
    * **Legacy** — single ``[adapter]`` section (backward compat).

    If *path* does not exist, return a default configuration with
    ``project_name`` and ``project_scope`` set to empty strings.
    """
    if not path.is_file():
        return AdapterConfig(project_name="", project_scope="")

    with open(path, "rb") as fh:
        data: dict[str, Any] = tomllib.load(fh)

    if _has_new_sections(data):
        config = _load_new_format(data)
    else:
        # Legacy [adapter] fallback
        section = data.get("adapter") or {}
        config = AdapterConfig(
            project_name=section.get("project_name", ""),
            project_scope=section.get("project_scope", ""),
            host=section.get("host", "codex"),
            adapter_version=section.get("adapter_version", CURRENT_MEMORY_VERSION),
            canonical_files=list(section.get("canonical_files", [])),
            artifact_root=section.get("artifact_root"),
        )

    # Validate host against SUPPORTED_HOSTS
    if config.host and config.host not in SUPPORTED_HOSTS:
        import warnings
        warnings.warn(
            f"adapter.toml routing.host='{config.host}' is not in SUPPORTED_HOSTS={SUPPORTED_HOSTS}",
            stacklevel=2,
        )

    return config

def _load_new_format(data: dict[str, Any]) -> AdapterConfig:
    """Parse the canonical ``[core]`` / ``[policy]`` / ``[routing]`` layout."""
    core: dict[str, Any] = data.get("core", {})
    policy: dict[str, Any] = data.get("policy", {})
    routing: dict[str, Any] = data.get("routing", {})

    return AdapterConfig(
        project_name=routing.get("project_name", routing.get("project_scope", "")),
        project_scope=routing.get("project_scope", ""),
        host=routing.get("host", "codex"),
        adapter_version=core.get("version", CURRENT_MEMORY_VERSION),
        canonical_files=list(routing.get("canonical_files", [])),
        artifact_root=routing.get("artifact_root"),
        legality_source_policy=policy.get("legality_source_policy", "map-only"),
        registration_commit_policy=policy.get("registration_commit_policy", "same-commit"),
        registration_commit_phase=policy.get("registration_commit_phase", "post"),
    )


def dump_adapter_toml(config: AdapterConfig) -> str:
    """Serialize *config* to a TOML string using the canonical layout."""
    lines: list[str] = []

    # [core]
    lines.append("# Memory Adapter Configuration")
    lines.append("")
    lines.append("[core]")
    lines.append(f'version = {_toml_str(config.adapter_version)}')
    lines.append(f'adapter = {_toml_str("default")}')

    # [policy]
    lines.append("")
    lines.append("[policy]")
    lines.append(f'legality_source_policy = {_toml_str(config.legality_source_policy)}')
    lines.append(f'registration_commit_policy = {_toml_str(config.registration_commit_policy)}')
    lines.append(f'registration_commit_phase = {_toml_str(config.registration_commit_phase)}')

    # [routing]
    lines.append("")
    lines.append("[routing]")
    lines.append(f'project_name = {_toml_str(config.project_name)}')
    lines.append(f'project_scope = {_toml_str(config.project_scope)}')
    lines.append(f'host = {_toml_str(config.host)}')

    # canonical_files
    lines.append("canonical_files = [")
    for f in config.canonical_files:
        lines.append(f"  {_toml_str(f)},")
    lines.append("]")

    # artifact_root (optional)
    if config.artifact_root is not None:
        lines.append(f'artifact_root = {_toml_str(config.artifact_root)}')
    else:
        lines.append("# artifact_root is not set")

    return "\n".join(lines) + "\n"
