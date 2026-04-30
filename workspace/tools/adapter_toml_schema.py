"""Adapter TOML schema and loader for .memory/adapter.toml configuration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AdapterConfig:
    """Configuration loaded from ``.memory/adapter.toml``."""

    project_name: str
    project_scope: str
    host: str = "codex"
    adapter_version: str = "0.1.0"
    canonical_files: list[str] = field(default_factory=list)
    artifact_root: str | None = None


_TOML_SECTION = "adapter"


def load_adapter_toml(path: Path) -> AdapterConfig:
    """Load an :class:`AdapterConfig` from *path*.

    If *path* does not exist, return a default configuration with
    ``project_name`` and ``project_scope`` set to empty strings.
    """
    if not path.is_file():
        return AdapterConfig(project_name="", project_scope="")

    with open(path, "rb") as fh:
        data: dict[str, Any] = tomllib.load(fh)

    section = data.get(_TOML_SECTION, {})

    return AdapterConfig(
        project_name=section.get("project_name", ""),
        project_scope=section.get("project_scope", ""),
        host=section.get("host", "codex"),
        adapter_version=section.get("adapter_version", "0.1.0"),
        canonical_files=list(section.get("canonical_files", [])),
        artifact_root=section.get("artifact_root"),
    )


def dump_adapter_toml(config: AdapterConfig) -> str:
    """Serialize *config* to a TOML string."""
    lines: list[str] = [f"[{_TOML_SECTION}]"]
    lines.append(f'project_name = {_toml_str(config.project_name)}')
    lines.append(f'project_scope = {_toml_str(config.project_scope)}')
    lines.append(f'host = {_toml_str(config.host)}')
    lines.append(f'adapter_version = {_toml_str(config.adapter_version)}')

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


def _toml_str(value: str) -> str:
    """Format a plain string as a TOML basic string."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
