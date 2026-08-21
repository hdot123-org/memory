"""Finalization phase: auto-fill, hooks, integrity, ownership, audit."""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION
from memory_core.ownership import load_memory_ownership

from ._init_autofill import _apply_auto_fill
from ._init_hooks import _cleanup_legacy_hooks_json, update_agents_md
from ._init_pipeline import _should_skip_file
from ._init_templates_misc import (
    template_ownership_toml,
)

logger = logging.getLogger(__name__)


def _finalize_auto_fill(
    target: Path,
    project_name: str,
    auto_fill: bool,
    result: dict[str, Any],
) -> None:
    """Handle auto-fill phase if enabled."""
    if not auto_fill:
        return
    try:
        from .project_probe import ProjectProbe
        probe = ProjectProbe(target)
        project_info = probe.probe()
        _apply_auto_fill(target, project_info, result, project_name=project_name)
    except Exception as exc:
        result["warnings"].append(f"auto-fill skipped: {exc}")


def _finalize_skill_yaml(
    target: Path,
    project_name: str,
    force: bool,
    result: dict[str, Any],
) -> None:
    """Generate and write memory-init-fill skill YAML."""
    try:
        from .template_sync import generate_skill_memory_init_fill_yaml
        fill_skill_content = generate_skill_memory_init_fill_yaml(project_name)
        if fill_skill_content:
            fill_skills_dir = target / "memory" / "system" / "skills"
            fill_skills_dir.mkdir(parents=True, exist_ok=True)
            fill_skill_path = fill_skills_dir / "memory-init-fill.yaml"
            if not fill_skill_path.exists() or force:
                fill_skill_path.write_text(fill_skill_content, encoding="utf-8")
                result["created"].append("file:memory/system/skills/memory-init-fill.yaml")
            else:
                result["skipped"].append("file:memory/system/skills/memory-init-fill.yaml (exists)")
    except Exception as exc:
        result["warnings"].append(f"memory-init-fill skill generation skipped: {exc}")


def _finalize_hooks_and_agents(
    target: Path,
    host: str,
    mode: str,
    result: dict[str, Any],
) -> None:
    """Clean up legacy hooks and update AGENTS.md."""
    _cleanup_legacy_hooks_json(target, result)
    update_agents_md(target, host=host, result=result, mode=mode)


def _finalize_integrity_signing(
    target: Path,
    result: dict[str, Any],
) -> None:
    """Sign the integrity manifest after scaffolding."""
    try:
        from .memory_hook_integrity_keys import load_or_create_key
        from .memory_hook_integrity_manifest import sign_project_incremental

        key = load_or_create_key()
        changed_paths = []
        for entry in result.get("created", []):
            if entry.startswith("file:"):
                path_part = entry[len("file:"):]
                paren_idx = path_part.find(" (")
                if paren_idx >= 0:
                    path_part = path_part[:paren_idx]
                changed_paths.append(path_part)

        sign_project_incremental(target, key, changed_paths=changed_paths, reason="memory-init baseline")
        result["created"].append("file:memory/system/manifest.json (signed)")
    except Exception as exc:
        result["warnings"].append(f"integrity signing skipped: {exc}")


def _finalize_integrity_audit(
    memory_root: Path,
    project_name: str,
    result: dict[str, Any],
) -> None:
    """Create initial integrity-audit.jsonl."""
    try:
        import json as _json
        audit_path = memory_root / "integrity-audit.jsonl"
        if not audit_path.exists():
            audit_entry = {
                "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                "action": "init",
                "version": CURRENT_MEMORY_VERSION,
                "project": project_name,
                "reason": "initial scaffold",
            }
            audit_path.write_text(_json.dumps(audit_entry, ensure_ascii=False) + "\n", encoding="utf-8")
            result["created"].append("file:memory/system/integrity-audit.jsonl")
    except Exception as exc:
        result["warnings"].append(f"integrity-audit.jsonl creation skipped: {exc}")


def _finalize_ownership_toml(
    target: Path,
    memory_root: Path,
    project_name: str,
    mode: str,
    force: bool,
    result: dict[str, Any],
) -> None:
    """Write ownership.toml with mode-aware handling."""
    try:
        ownership_path = memory_root / "ownership.toml"
        ownership = load_memory_ownership(target)
        authorized_maintenance = mode == "repair" or os.environ.get("MEMORY_INIT_RUNNING") == "1"
        should_skip, _ = _should_skip_file(
            ownership_path, mode, force, ownership, authorized_maintenance, target, result
        )
        if not should_skip:
            content, warnings = template_ownership_toml(project_name)
            ownership_path.write_text(content, encoding="utf-8")
            result["created"].append("file:ownership.toml")
            result["warnings"].extend(warnings)
        elif ownership_path.exists():
            if mode == "update":
                try:
                    from .version_sync import patch_ownership_memory_version
                except ImportError:
                    from memory_core.tools.version_sync import patch_ownership_memory_version
                if patch_ownership_memory_version(ownership_path, CURRENT_MEMORY_VERSION):
                    result["created"].append(f"file:ownership.toml (memory_version patched to {CURRENT_MEMORY_VERSION})")
                else:
                    result["skipped"].append("file:ownership.toml (already up-to-date)")
            else:
                result["skipped"].append("file:ownership.toml (already exists)")
    except Exception as exc:
        result["errors"].append(f"failed to create ownership.toml: {exc}")


def _finalize_evidence_refs(
    target: Path,
    result: dict[str, Any],
) -> None:
    """Validate evidence references on disk."""
    try:
        from memory_core.tools.evidence_ref_validator import validate_evidence_refs_on_disk
        ref_errors = validate_evidence_refs_on_disk(target)
        for err in ref_errors:
            result["warnings"].append(
                f"evidence ref check: {err.kb_file} has {len(err.missing_refs)} missing refs: "
                f"{', '.join(err.missing_refs[:3])}"
            )
    except Exception as exc:
        result["warnings"].append(f"evidence ref check skipped: {exc}")


def _finalize_post_audit(
    target: Path,
    result: dict[str, Any],
) -> None:
    """Run post-initialization audit and collect P1 findings."""
    try:
        from .audit_project_layout import audit_project_layout
        audit_result = audit_project_layout(target)
        for finding in audit_result.findings:
            if finding.severity == "P1":
                result["warnings"].append(f"audit P1 [{finding.kind}] {finding.path}: {finding.message}")
    except Exception as exc:
        result["warnings"].append(f"post-init audit skipped (error): {exc}")


def _finalize_init(
    target: Path,
    memory_root: Path,
    project_name: str,
    host: str,
    mode: str,
    force: bool,
    auto_fill: bool,
    result: dict[str, Any],
) -> None:
    """Finalize initialization: auto-fill, hooks, integrity, ownership, audit."""
    # Auto-fill
    if result["success"] and auto_fill:
        _finalize_auto_fill(target, project_name, auto_fill, result)

    if not result["success"]:
        return

    # Generate skill YAML
    _finalize_skill_yaml(target, project_name, force, result)

    # Hooks and AGENTS.md
    _finalize_hooks_and_agents(target, host, mode, result)

    # Integrity signing
    _finalize_integrity_signing(target, result)

    # Integrity audit
    _finalize_integrity_audit(memory_root, project_name, result)

    # Ownership.toml
    _finalize_ownership_toml(target, memory_root, project_name, mode, force, result)

    # Evidence refs
    _finalize_evidence_refs(target, result)

    # Post-init audit
    _finalize_post_audit(target, result)


