#!/usr/bin/env python3
"""Audit project memory layout and detect legacy/residue patterns.

Usage:
    python audit_project_layout.py --target /path/to/project
    python audit_project_layout.py --target /path/to/project --json
    python audit_project_layout.py --target /path/to/project --json --severity P0

This tool performs read-only analysis of a project directory to identify:
- Memory structure patterns (.memory, memory/, project-map/, etc.)
- Root pollution (scattered reports, dumps, backups)
- Manifest integrity issues
- Legacy multi-generation memory conflicts

Output:
    JSON with findings array containing severity, kind, path, message, suggested_bucket
"""

from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from memory_core.ownership import (
    Owned,
    classify_owned_path,
    load_memory_ownership,
)


@dataclass
class Finding:
    """A single audit finding."""

    severity: str  # P0, P1, P2
    kind: str
    path: str
    message: str
    suggested_bucket: str


@dataclass
class AuditResult:
    """Complete audit result."""

    target: str
    findings: list[Finding] = field(default_factory=list)
    scanned_dirs: int = 0
    scanned_files: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "findings": [
                {
                    "severity": f.severity,
                    "kind": f.kind,
                    "path": f.path,
                    "message": f.message,
                    "suggested_bucket": f.suggested_bucket,
                }
                for f in self.findings
            ],
            "summary": {
                "total": len(self.findings),
                "p0": len([f for f in self.findings if f.severity == "P0"]),
                "p1": len([f for f in self.findings if f.severity == "P1"]),
                "p2": len([f for f in self.findings if f.severity == "P2"]),
                "scanned_dirs": self.scanned_dirs,
                "scanned_files": self.scanned_files,
            },
        }


# Root pollution move destination used by memory-apply-residue-plan
ROOT_POLLUTION_DEST = "memory/artifacts/reports"


# Step 2.8: FORBIDDEN_OVERWRITE_PATTERNS replaced with classify_owned_path() calls
# The following patterns are now detected via classify_owned_path():
# - AGENTS.md (owned resource)
# - INDEX.md (owned via project_map domain)
# - project-map/** (owned domain)
# - CLAUDE.md (owned resource via domain)
# - memory/system/** (owned domain)
# - memory/** (owned domain)
# Legacy kept for backward compatibility during transition
LEGACY_FORBIDDEN_OVERWRITE_PATTERNS = [
    "AGENTS.md",
    "INDEX.md",
    "project-map/**",
    "CLAUDE.md",
]

# Action types for migration plan
ACTION_ADOPT_EXISTING_MEMORY = "adopt_existing_memory"
ACTION_CREATE_MISSING_MEMORY = "create_missing_memory"
ACTION_MOVE_ROOT_POLLUTION = "move_root_pollution"
ACTION_IGNORE_RUNTIME_ARTIFACT = "ignore_runtime_artifact"
ACTION_MARK_LEGACY_READONLY = "mark_legacy_readonly"
ACTION_MANUAL_DECISION_REQUIRED = "manual_decision_required"


ROOT_DOCUMENT_ENTRYPOINT_DIRS = {
    "doc",
    "docs",
    "documentation",
}

# Root files that are allowed/expected (should NOT be flagged as pollution)
ALLOWED_ROOT_FILES = {
    # Documentation
    "README.md",
    "README.rst",
    "README.txt",
    "README",
    "CHANGELOG.md",
    "CHANGELOG.rst",
    "CHANGELOG.txt",
    "CHANGELOG",
    "CHANGES.md",
    "CHANGES.rst",
    "CHANGES.txt",
    "CHANGES",
    "HISTORY.md",
    "HISTORY.rst",
    "HISTORY.txt",
    "HISTORY",
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "COPYING",
    "COPYING.md",
    "COPYING.txt",
    "NOTICE",
    "NOTICE.md",
    "NOTICE.txt",
    "CONTRIBUTING.md",
    "CONTRIBUTING.rst",
    "CONTRIBUTING.txt",
    "CODE_OF_CONDUCT.md",
    "CODE_OF_CONDUCT.rst",
    "CODE_OF_CONDUCT.txt",
    "SECURITY.md",
    "SECURITY.rst",
    "SECURITY.txt",
    "AUTHORS",
    "AUTHORS.md",
    "AUTHORS.txt",
    "MAINTAINERS",
    "MAINTAINERS.md",
    "MAINTAINERS.txt",
    "AGENTS.md",
    "CLAUDE.md",
    "CLAUDE",
    "INDEX.md",
    "INDEX",
    "NOW.md",
    # Config
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".pre-commit-config.yaml",
    ".pre-commit-config.yml",
    # Python
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "Pipfile",
    "MANIFEST.in",
    ".python-version",
    "poetry.lock",
    "uv.lock",
    # Node
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".npmignore",
    ".npmrc",
    ".nvmrc",
    # Rust
    "Cargo.toml",
    "Cargo.lock",
    # Go
    "go.mod",
    "go.sum",
    # Docker
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".dockerignore",
    # CI/CD
    ".gitlab-ci.yml",
    ".travis.yml",
    "appveyor.yml",
    "azure-pipelines.yml",
    "Jenkinsfile",
    "Makefile",
    "makefile",
    "GNUmakefile",
    # IDE
    ".vscode",
    ".idea",
    ".vs",
}

ALLOWED_ROOT_PATTERNS = [
    # README variants
    "README*",
    # CHANGELOG variants
    "CHANGELOG*",
    "CHANGES*",
    "HISTORY*",
    # License variants
    "LICENSE*",
    "COPYING*",
    "NOTICE*",
    # Config files
    ".*ignore",
    ".*rc",
    ".*rc.*",
    # Package files
    "setup.*",
    "pyproject.*",
    "requirements*.txt",
    # Lock files
    "*.lock",
    "Poetry.lock",
    "uv.lock",
    # CI templates
    ".github/**/*",
    ".circleci/**/*",
]

# Root pollution patterns (files that should not be in root)
ROOT_POLLUTION_PATTERNS = [
    ("*report*.md", "P1", "root_report", "Root-level report file"),
    ("*audit*.md", "P1", "root_audit", "Root-level audit file"),
    ("p[0-9]-*.md", "P1", "root_plan", "Root-level phase plan file"),
    ("*.bak", "P2", "root_backup", "Root-level backup file"),
    ("*.backup.*", "P2", "root_backup", "Root-level backup file"),
    ("*dump*.json", "P1", "root_dump", "Root-level dump file"),
    ("*dump*.md", "P1", "root_dump", "Root-level dump file"),
]

# Memory structure patterns to detect
MEMORY_STRUCTURE_PATTERNS = {
    ".memory": ("dot_memory", "Modern memory-core structure"),
    "memory": ("current_memory", "Current memory/ directory"),
    "project-map": ("project_map", "Project map directory"),
    "workspace/memory": ("workspace_memory", "Workspace memory directory"),
    "workspace/project-map": ("workspace_project_map", "Workspace project-map directory"),
    "history-projects": ("history_projects", "History projects directory"),
    "memory/artifacts/memory-hook": ("artifacts_memory_hook", "Memory hook artifacts"),
}


def _is_allowed_root_file(name: str) -> bool:
    """Check if a root file is allowed/expected."""
    if name in ALLOWED_ROOT_FILES:
        return True
    for pattern in ALLOWED_ROOT_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _check_root_pollution(root: Path, result: AuditResult) -> None:
    """Check for root-level pollution files and forbidden document entrypoints."""
    for item in root.iterdir():
        name = item.name
        if item.is_symlink() and name in ROOT_DOCUMENT_ENTRYPOINT_DIRS:
            result.findings.append(
                Finding(
                    severity="P1",
                    kind="root_docs_symlink",
                    path=name,
                    message=f"Root-level document symlink is forbidden; use memory/docs/: {name}",
                    suggested_bucket="root_pollution",
                )
            )
            continue
        if item.is_dir() and name in ROOT_DOCUMENT_ENTRYPOINT_DIRS:
            result.findings.append(
                Finding(
                    severity="P1",
                    kind="root_docs_dir",
                    path=name,
                    message=f"Root-level document directory is forbidden; use memory/docs/: {name}",
                    suggested_bucket="root_pollution",
                )
            )
            continue
        if item.is_dir():
            continue
        if _is_allowed_root_file(name):
            continue
        for pattern, severity, kind, message in ROOT_POLLUTION_PATTERNS:
            if fnmatch.fnmatch(name, pattern):
                result.findings.append(
                    Finding(
                        severity=severity,
                        kind=kind,
                        path=str(item.relative_to(root)),
                        message=f"{message}: {name}",
                        suggested_bucket="root_pollution",
                    )
                )
                break


def _check_memory_structures(root: Path, result: AuditResult) -> None:
    """Check for memory structure patterns."""
    for rel_path, (kind, description) in MEMORY_STRUCTURE_PATTERNS.items():
        full_path = root / rel_path
        if full_path.exists():
            # P0 for dot_memory (modern), P1 for current_memory and others
            if kind == "dot_memory":
                severity = "P0"
            elif kind == "current_memory":
                severity = "P1"
            else:
                severity = "P1"
            result.findings.append(
                Finding(
                    severity=severity,
                    kind=kind,
                    path=rel_path,
                    message=f"Detected {description}",
                    suggested_bucket=_suggest_bucket_for_memory(kind),
                )
            )


def _suggest_bucket_for_memory(kind: str) -> str:
    """Suggest a bucket for memory structure findings."""
    bucket_map = {
        "dot_memory": "direct_manage",
        "current_memory": "direct_manage",
        "project_map": "continue_active",
        "workspace_memory": "needs_human_decision",
        "workspace_project_map": "needs_human_decision",
        "history_projects": "legacy_readonly",
        "artifacts_memory_hook": "continue_active",
    }
    return bucket_map.get(kind, "needs_human_decision")


def _check_manifest(root: Path, result: AuditResult) -> None:
    """Check memory/system/manifest.json for issues."""
    manifest_path = root / "memory" / "system" / "manifest.json"
    if not manifest_path.exists():
        return

    try:
        content = manifest_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except (json.JSONDecodeError, OSError) as e:
        result.findings.append(
            Finding(
                severity="P1",
                kind="manifest_invalid",
                path="memory/system/manifest.json",
                message=f"Manifest is invalid JSON: {e}",
                suggested_bucket="needs_human_decision",
            )
        )
        return

    entries = data.get("entries", [])
    # Precise prefix matching: only flag true runtime paths.
    # Normalize to forward slashes before matching.
    runtime_prefixes = (
        "memory/artifacts/",
        "memory/system/cache/",
        "tmp/",
        "memory/log/",
    )

    for entry in entries:
        path = entry.get("path", "")
        # Normalize path to forward slashes for consistent prefix matching
        normalized_path = path.replace("\\", "/")
        for prefix in runtime_prefixes:
            if normalized_path.startswith(prefix) or f"/{prefix}" in normalized_path:
                result.findings.append(
                    Finding(
                        severity="P2",
                        kind="manifest_includes_runtime",
                        path="memory/system/manifest.json",
                        message=f"Manifest includes runtime/tmp/log path: {path}",
                        suggested_bucket="runtime_ignore",
                    )
                )
                break


def _check_multi_generation_conflict(root: Path, result: AuditResult) -> None:
    """Check for multi-generation memory conflicts.

    Conflict rules:
    - memory/system + memory: NOT a conflict (both are current/valid)
    - memory/system + memory + project-map: NOT a conflict
    - Current root layout (memory/system/memory/project-map) + workspace/memory: CONFLICT
    - Current root layout + workspace/project-map: CONFLICT
    - history-projects: Does NOT participate in active conflict
    """
    has_system_memory = (root / "memory" / "system").exists()
    has_current_memory = (root / "memory").exists()
    has_project_map = (root / "project-map").exists()
    has_workspace_memory = (root / "workspace" / "memory").exists()
    has_workspace_project_map = (root / "workspace" / "project-map").exists()

    # Build list of active current structures (excluding history-projects)
    current_structures = []
    if has_system_memory:
        current_structures.append("memory/system")
    if has_current_memory:
        current_structures.append("memory/")
    if has_project_map:
        current_structures.append("project-map/")

    # Build list of workspace legacy structures
    workspace_structures = []
    if has_workspace_memory:
        workspace_structures.append("workspace/memory/")
    if has_workspace_project_map:
        workspace_structures.append("workspace/project-map/")

    # Conflict: current root layout + workspace structures
    if current_structures and workspace_structures:
        locations = current_structures + workspace_structures
        result.findings.append(
            Finding(
                severity="P0",
                kind="multi_generation_conflict",
                path=root.name,
                message=f"Root memory structures conflict with workspace legacy: {', '.join(locations)}",
                suggested_bucket="needs_human_decision",
            )
        )


def _check_agents_md(root: Path, result: AuditResult) -> None:
    """Check AGENTS.md for marker-based vs legacy content."""
    agents_path = root / "AGENTS.md"
    if not agents_path.exists():
        return

    try:
        content = agents_path.read_text(encoding="utf-8")
    except OSError:
        return

    has_begin_marker = "<!-- MEMORY_HOOK_BEGIN -->" in content
    has_end_marker = "<!-- MEMORY_HOOK_END -->" in content

    if has_begin_marker and has_end_marker:
        # Modern marker-based structure
        result.findings.append(
            Finding(
                severity="P2",
                kind="agents_md_marked",
                path="AGENTS.md",
                message="AGENTS.md has MEMORY_HOOK markers (modern format)",
                suggested_bucket="direct_manage",
            )
        )
    elif "memory" in content.lower() or "hook" in content.lower():
        # Legacy unmarked content
        result.findings.append(
            Finding(
                severity="P1",
                kind="agents_md_unmarked",
                path="AGENTS.md",
                message="AGENTS.md contains memory/hook references without markers",
                suggested_bucket="needs_human_decision",
            )
        )


def _check_index_md(root: Path, result: AuditResult) -> None:
    """Check for root INDEX.md that might be business content."""
    index_path = root / "INDEX.md"
    if not index_path.exists():
        return

    try:
        content = index_path.read_text(encoding="utf-8")
        # Check if it looks like a business INDEX vs memory INDEX
        if "project-map" not in content.lower() and "memory" not in content.lower():
            result.findings.append(
                Finding(
                    severity="P2",
                    kind="index_md_business",
                    path="INDEX.md",
                    message="INDEX.md appears to be business content (not memory structure)",
                    suggested_bucket="continue_active",
                )
            )
    except OSError:
        pass


def _scan_directory_stats(root: Path, result: AuditResult) -> None:
    """Collect basic scan statistics."""
    result.scanned_dirs = 0
    result.scanned_files = 0

    for item in root.iterdir():
        if item.is_dir():
            result.scanned_dirs += 1
        else:
            result.scanned_files += 1


def audit_project_layout(target: Path, severity_filter: str | None = None) -> AuditResult:
    """Perform a full audit of the project layout.

    Args:
        target: Path to the project root to audit.
        severity_filter: If provided, only return findings of this severity or higher.

    Returns:
        AuditResult containing all findings.
    """
    result = AuditResult(target=str(target.resolve()))

    if not target.exists():
        result.findings.append(
            Finding(
                severity="P0",
                kind="target_missing",
                path=str(target),
                message=f"Target path does not exist: {target}",
                suggested_bucket="needs_human_decision",
            )
        )
        return result

    if not target.is_dir():
        result.findings.append(
            Finding(
                severity="P0",
                kind="target_not_dir",
                path=str(target),
                message=f"Target path is not a directory: {target}",
                suggested_bucket="needs_human_decision",
            )
        )
        return result

    _scan_directory_stats(target, result)
    _check_memory_structures(target, result)
    _check_multi_generation_conflict(target, result)
    _check_root_pollution(target, result)
    _check_manifest(target, result)
    _check_agents_md(target, result)
    _check_index_md(target, result)

    # Step 2.8: New ownership-related finding kinds
    _check_ownership_findings(target, result)

    # Apply severity filter if requested
    if severity_filter:
        severity_order = {"P0": 0, "P1": 1, "P2": 2}
        min_level = severity_order.get(severity_filter, 0)
        result.findings = [f for f in result.findings if severity_order.get(f.severity, 2) <= min_level]

    return result


def _check_ownership_findings(root: Path, result: AuditResult) -> None:
    """Step 2.8: Check for ownership-related findings.

    New finding kinds:
    - ownership_missing: ownership.toml does not exist
    - domain_missing: Critical domain paths missing
    - domain_weakened: Protection level weakened
    - marker_tampered: AGENTS.md markers tampered
    - index_inconsistent: Index files inconsistent
    - owned_file_unreadable: Cannot read owned file
    """
    # Check ownership.toml exists
    ownership_path = root / "memory" / "system" / "ownership.toml"
    if not ownership_path.exists():
        result.findings.append(
            Finding(
                severity="P1",
                kind="ownership_missing",
                path="memory/system/ownership.toml",
                message="ownership.toml not found - ownership declaration missing",
                suggested_bucket="needs_human_decision",
            )
        )
    else:
        # Try to load and validate ownership
        try:
            from memory_core.ownership import validate_ownership_schema
            ownership = load_memory_ownership(root)
            schema_errors = validate_ownership_schema(ownership)
            for error in schema_errors:
                if "downgraded" in error.lower():
                    result.findings.append(
                        Finding(
                            severity="P0",
                            kind="domain_weakened",
                            path="memory/system/ownership.toml",
                            message=f"Ownership protection weakened: {error}",
                            suggested_bucket="needs_human_decision",
                        )
                    )
                elif "deleted" in error.lower():
                    result.findings.append(
                        Finding(
                            severity="P0",
                            kind="domain_missing",
                            path="memory/system/ownership.toml",
                            message=f"Ownership domain/resource deleted: {error}",
                            suggested_bucket="needs_human_decision",
                        )
                    )
        except OSError as e:
            result.findings.append(
                Finding(
                    severity="P1",
                    kind="owned_file_unreadable",
                    path="memory/system/ownership.toml",
                    message=f"Cannot read ownership.toml: {e}",
                    suggested_bucket="needs_human_decision",
                )
            )

    # Check index consistency
    index_paths = [
        ("memory/docs/INDEX.md", root / "memory" / "docs" / "INDEX.md"),
        ("memory/kb/INDEX.md", root / "memory" / "kb" / "INDEX.md"),
        ("project-map/INDEX.md", root / "project-map" / "INDEX.md"),
    ]
    for rel_path, full_path in index_paths:
        if full_path.exists():
            try:
                content = full_path.read_text(encoding="utf-8")
                # Check for broken internal references
                import re
                refs = re.findall(r"\[.*?\]\((.*?)\)", content)
                for ref in refs:
                    if not ref.startswith("http") and not ref.startswith("#"):
                        ref_path = root / ref
                        if not ref_path.exists():
                            result.findings.append(
                                Finding(
                                    severity="P2",
                                    kind="index_inconsistent",
                                    path=rel_path,
                                    message=f"Broken reference to {ref}",
                                    suggested_bucket="needs_human_decision",
                                )
                            )
            except OSError as e:
                result.findings.append(
                    Finding(
                        severity="P1",
                        kind="owned_file_unreadable",
                        path=rel_path,
                        message=f"Cannot read index file: {e}",
                        suggested_bucket="needs_human_decision",
                    )
                )


@dataclass
class PlanAction:
    """A single action in the migration plan."""

    action: str  # adopt_existing_memory, create_missing_memory, move_root_pollution, etc.
    path: str
    severity: str
    kind: str
    message: str
    source_bucket: str
    target_bucket: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "path": self.path,
            "severity": self.severity,
            "kind": self.kind,
            "message": self.message,
            "source_bucket": self.source_bucket,
            "target_bucket": self.target_bucket,
            "metadata": self.metadata,
        }


@dataclass
class MigrationPlan:
    """Migration plan for residue cleanup with stable schema."""

    # Core schema fields
    target: str
    buckets: dict[str, list[dict[str, Any]]]  # Retained for compatibility
    actions: list[PlanAction]
    risk_level: str  # critical, high, medium, low
    requires_human_confirmation: bool
    backup_plan: dict[str, Any]
    rollback_plan: dict[str, Any]
    forbidden_overwrites: list[str]
    must_commit_together: list[list[str]]
    # Legacy field
    total_items: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "buckets": self.buckets,
            "actions": [a.to_dict() for a in self.actions],
            "risk_level": self.risk_level,
            "requires_human_confirmation": self.requires_human_confirmation,
            "backup_plan": self.backup_plan,
            "rollback_plan": self.rollback_plan,
            "forbidden_overwrites": self.forbidden_overwrites,
            "must_commit_together": self.must_commit_together,
            "summary": {
                "total_items": self.total_items,
                "action_count": len(self.actions),
                "bucket_counts": {k: len(v) for k, v in self.buckets.items()},
            },
        }


def _determine_action(finding: Finding, has_conflict: bool) -> PlanAction:
    """Determine the appropriate action for a finding.

    Maps findings to specific action types based on kind and context.
    """
    action_map: dict[str, str] = {
        "dot_memory": ACTION_ADOPT_EXISTING_MEMORY,
        "agents_md_marked": ACTION_ADOPT_EXISTING_MEMORY,
        "current_memory": ACTION_ADOPT_EXISTING_MEMORY,
        "workspace_memory": ACTION_MARK_LEGACY_READONLY,
        "workspace_project_map": ACTION_MARK_LEGACY_READONLY,
        "history_projects": ACTION_MARK_LEGACY_READONLY,
        "project_map": ACTION_ADOPT_EXISTING_MEMORY,
        "artifacts_memory_hook": ACTION_IGNORE_RUNTIME_ARTIFACT,
        "manifest_includes_runtime": ACTION_IGNORE_RUNTIME_ARTIFACT,
        "root_report": ACTION_MOVE_ROOT_POLLUTION,
        "root_audit": ACTION_MOVE_ROOT_POLLUTION,
        "root_plan": ACTION_MOVE_ROOT_POLLUTION,
        "root_docs_dir": ACTION_MOVE_ROOT_POLLUTION,
        "root_docs_symlink": ACTION_MOVE_ROOT_POLLUTION,
        "root_dump": ACTION_MOVE_ROOT_POLLUTION,
        "root_now": ACTION_MOVE_ROOT_POLLUTION,
        "root_backup": ACTION_IGNORE_RUNTIME_ARTIFACT,
        "index_md_business": ACTION_ADOPT_EXISTING_MEMORY,
        "agents_md_unmarked": ACTION_MANUAL_DECISION_REQUIRED,
        "multi_generation_conflict": ACTION_MANUAL_DECISION_REQUIRED,
        "target_missing": ACTION_MANUAL_DECISION_REQUIRED,
        "target_not_dir": ACTION_MANUAL_DECISION_REQUIRED,
        "manifest_invalid": ACTION_MANUAL_DECISION_REQUIRED,
    }

    action = action_map.get(finding.kind, ACTION_MANUAL_DECISION_REQUIRED)

    # Note: has_conflict affects risk_level and requires_human_confirmation at plan level,
    # but individual actions should keep their original type unless they ARE the conflict

    # Determine target bucket based on action
    target_bucket_map: dict[str, str | None] = {
        ACTION_ADOPT_EXISTING_MEMORY: "direct_manage",
        ACTION_MARK_LEGACY_READONLY: "legacy_readonly",
        ACTION_IGNORE_RUNTIME_ARTIFACT: "runtime_ignore",
        ACTION_MOVE_ROOT_POLLUTION: "root_pollution",
        ACTION_MANUAL_DECISION_REQUIRED: "needs_human_decision",
    }

    target_bucket = target_bucket_map.get(action)
    metadata: dict[str, Any] = {
        "has_conflict": has_conflict,
    }
    if action == ACTION_MOVE_ROOT_POLLUTION:
        metadata["destination"] = f"{ROOT_POLLUTION_DEST}/{Path(finding.path).name}"

    return PlanAction(
        action=action,
        path=finding.path,
        severity=finding.severity,
        kind=finding.kind,
        message=finding.message,
        source_bucket=finding.suggested_bucket,
        target_bucket=target_bucket,
        metadata=metadata,
    )


def _calculate_risk_level(
    findings: list[Finding],
    has_multi_generation: bool,
    has_root_vs_workspace_conflict: bool,
) -> str:
    """Calculate overall risk level for the migration plan.

    Risk levels: critical, high, medium, low
    """
    # Check for critical conditions: multi-generation conflicts or root vs workspace conflicts
    if has_multi_generation or has_root_vs_workspace_conflict:
        return "critical"

    # P0 from current memory structures (dot_memory) is not critical
    # Only count P0 from actual conflicts
    conflict_p0_count = len([f for f in findings if f.severity == "P0" and f.kind == "multi_generation_conflict"])
    if conflict_p0_count > 0:
        return "critical"

    # Count P1 findings
    p1_count = len([f for f in findings if f.severity == "P1"])
    if p1_count > 0:
        return "high"

    # Count P2 findings
    p2_count = len([f for f in findings if f.severity == "P2"])
    if p2_count > 0:
        return "medium"

    return "low"


def _requires_human_confirmation(
    findings: list[Finding],
    has_multi_generation: bool,
    has_root_vs_workspace_conflict: bool,
) -> bool:
    """Determine if human confirmation is required.

    Human confirmation required for:
    - Multi-generation conflicts (root vs workspace)
    - Root memory/project-map vs workspace memory/project-map conflicts
    - Any manual decision actions
    - Forbidden overwrite patterns

    NOT required for:
    - Current memory structures (.memory, memory/, project-map/)
    - History projects (legacy_readonly)
    """
    if has_multi_generation:
        return True

    if has_root_vs_workspace_conflict:
        return True

    for finding in findings:
        if finding.kind in ("multi_generation_conflict", "agents_md_unmarked"):
            return True
        # Only workspace legacy structures require confirmation, not current ones
        if finding.kind in ("workspace_memory", "workspace_project_map"):
            return True

    return False


def _generate_backup_plan(findings: list[Finding], target: Path) -> dict[str, Any]:
    """Generate backup plan for critical files.

    Returns backup instructions for files that must be preserved.
    """
    files_to_backup: list[str] = []

    for finding in findings:
        if finding.kind in ("dot_memory", "legacy_memory", "project_map"):
            files_to_backup.append(finding.path)
        elif finding.kind in ("agents_md_marked", "agents_md_unmarked"):
            files_to_backup.append(finding.path)
        elif finding.kind == "index_md_business":
            files_to_backup.append(finding.path)

    return {
        "backup_root": str(target / "memory" / "system" / "backups" / "migration"),
        "files_to_backup": files_to_backup,
        "backup_strategy": "copy_before_modify",
        "timestamp_format": "iso8601",
    }


def _generate_rollback_plan(findings: list[Finding], target: Path) -> dict[str, Any]:
    """Generate rollback plan in case migration fails.

    Returns rollback instructions.
    """
    rollback_steps: list[dict[str, str]] = []

    for finding in findings:
        if finding.kind == "dot_memory":
            rollback_steps.append(
                {
                    "step": f"Restore {finding.path} from backup",
                    "command": f"cp -r $BACKUP_DIR/{finding.path} {finding.path}",
                }
            )
        elif finding.kind in ("root_report", "root_audit", "root_plan", "root_dump", "root_now", "root_docs_dir", "root_docs_symlink"):
            destination = f"{ROOT_POLLUTION_DEST}/{Path(finding.path).name}"
            rollback_steps.append(
                {
                    "step": f"Restore {finding.path} to root",
                    "command": f"mv {destination} ./{finding.path}",
                }
            )

    return {
        "rollback_available": len(rollback_steps) > 0,
        "rollback_steps": rollback_steps,
        "rollback_trigger": "on_error_or_manual_abort",
    }


def _generate_must_commit_together(findings: list[Finding]) -> list[list[str]]:
    """Generate groups of files that must be committed together.

    Returns list of file groups that are interdependent.
    """
    groups: list[list[str]] = []

    # Check for multi-generation conflicts that need coordinated handling
    memory_structures: list[str] = []
    for finding in findings:
        if finding.kind in ("dot_memory", "legacy_memory", "workspace_memory"):
            memory_structures.append(finding.path)

    if len(memory_structures) > 1:
        groups.append(memory_structures)

    # AGENTS.md and INDEX.md should be committed together if both exist
    critical_docs: list[str] = []
    for finding in findings:
        if finding.kind in ("agents_md_marked", "agents_md_unmarked"):
            critical_docs.append(finding.path)
        elif finding.kind == "index_md_business":
            critical_docs.append(finding.path)

    if len(critical_docs) > 1:
        groups.append(critical_docs)

    return groups


def _check_root_vs_workspace_conflict(
    findings: list[Finding],
) -> bool:
    """Check for root memory/project-map vs workspace memory/project-map conflicts.

    Current root structures (.memory, memory/, project-map/) coexisting with
    workspace legacy structures (workspace/memory, workspace/project-map) is a conflict.
    """
    has_root_memory = any(f.kind in ("dot_memory", "current_memory", "project_map") for f in findings)
    has_workspace_memory = any(f.kind in ("workspace_memory", "workspace_project_map") for f in findings)

    return has_root_memory and has_workspace_memory


def plan_residue_migration(
    audit_result: AuditResult,
    target: Path,
) -> MigrationPlan:
    """Generate a migration plan from audit findings with stable schema.

    This function generates a comprehensive migration plan that includes:
    - actions: Detailed actions to take
    - risk_level: Overall risk assessment (critical, high, medium, low)
    - requires_human_confirmation: Whether manual review is needed
    - backup_plan: Instructions for backing up critical files
    - rollback_plan: Instructions for rolling back if needed
    - forbidden_overwrites: List of files/patterns that must never be overwritten
    - must_commit_together: Groups of files that are interdependent

    Buckets (retained for compatibility):
        - direct_manage: Items that can be directly managed by memory-core
        - continue_active: Items that should continue to be used as-is
        - legacy_readonly: Legacy items that should be kept read-only
        - runtime_ignore: Runtime/tmp items that should be ignored
        - needs_human_decision: Items requiring manual review
        - root_pollution: Root-scattered files that need cleanup

    Actions:
        - adopt_existing_memory: Adopt existing memory structure into management
        - create_missing_memory: Create missing memory structure (placeholder)
        - move_root_pollution: Move root-scattered files to appropriate location
        - ignore_runtime_artifact: Ignore runtime/tmp artifacts
        - mark_legacy_readonly: Mark legacy items as read-only
        - manual_decision_required: Requires human review and decision
    """
    buckets: dict[str, list[dict[str, Any]]] = {
        "direct_manage": [],
        "continue_active": [],
        "legacy_readonly": [],
        "runtime_ignore": [],
        "needs_human_decision": [],
        "root_pollution": [],
    }

    # Check for conflicts
    has_multi_generation = any(f.kind == "multi_generation_conflict" for f in audit_result.findings)
    has_root_vs_workspace = _check_root_vs_workspace_conflict(audit_result.findings)

    # Generate actions from findings
    actions: list[PlanAction] = []
    for finding in audit_result.findings:
        action = _determine_action(finding, has_multi_generation)
        actions.append(action)

        # Also populate buckets for backward compatibility
        bucket = finding.suggested_bucket
        item = {
            "path": finding.path,
            "severity": finding.severity,
            "kind": finding.kind,
            "message": finding.message,
        }
        if bucket in buckets:
            buckets[bucket].append(item)
        else:
            buckets["needs_human_decision"].append(item)

    # Add any root-level files/directories that might need migration
    for item in target.iterdir():
        name = item.name
        if item.is_symlink() and name in ROOT_DOCUMENT_ENTRYPOINT_DIRS:
            if not any(f.path == name for f in audit_result.findings):
                buckets["root_pollution"].append(
                    {
                        "path": name,
                        "severity": "P1",
                        "kind": "root_docs_symlink",
                        "message": f"Root-level document symlink is forbidden; use memory/docs/: {name}",
                    }
                )
                actions.append(
                    PlanAction(
                        action=ACTION_MOVE_ROOT_POLLUTION,
                        path=name,
                        severity="P1",
                        kind="root_docs_symlink",
                        message=f"Root-level document symlink is forbidden; use memory/docs/: {name}",
                        source_bucket="root_pollution",
                        target_bucket="root_pollution",
                        metadata={"destination": f"{ROOT_POLLUTION_DEST}/{name}"},
                    )
                )
            continue
        if item.is_dir() and name in ROOT_DOCUMENT_ENTRYPOINT_DIRS:
            if not any(f.path == name for f in audit_result.findings):
                buckets["root_pollution"].append(
                    {
                        "path": name,
                        "severity": "P1",
                        "kind": "root_docs_dir",
                        "message": f"Root-level document directory is forbidden; use memory/docs/: {name}",
                    }
                )
                actions.append(
                    PlanAction(
                        action=ACTION_MOVE_ROOT_POLLUTION,
                        path=name,
                        severity="P1",
                        kind="root_docs_dir",
                        message=f"Root-level document directory is forbidden; use memory/docs/: {name}",
                        source_bucket="root_pollution",
                        target_bucket="root_pollution",
                        metadata={"destination": f"{ROOT_POLLUTION_DEST}/{name}"},
                    )
                )
            continue
        if item.is_file():
            # Check for root-level markdown files that might be business content
            if name.endswith(".md") and not _is_allowed_root_file(name):
                # Check if it's already in findings
                if not any(f.path == name for f in audit_result.findings):
                    buckets["needs_human_decision"].append(
                        {
                            "path": name,
                            "severity": "P2",
                            "kind": "unknown_md_file",
                            "message": f"Unclassified markdown file in root: {name}",
                        }
                    )
                    actions.append(
                        PlanAction(
                            action=ACTION_MANUAL_DECISION_REQUIRED,
                            path=name,
                            severity="P2",
                            kind="unknown_md_file",
                            message=f"Unclassified markdown file in root: {name}",
                            source_bucket="needs_human_decision",
                            target_bucket="needs_human_decision",
                        )
                    )

    # Calculate risk level
    risk_level = _calculate_risk_level(
        audit_result.findings,
        has_multi_generation,
        has_root_vs_workspace,
    )

    # Determine if human confirmation is required
    requires_confirmation = _requires_human_confirmation(
        audit_result.findings,
        has_multi_generation,
        has_root_vs_workspace,
    )

    # Generate backup and rollback plans
    backup_plan = _generate_backup_plan(audit_result.findings, target)
    rollback_plan = _generate_rollback_plan(audit_result.findings, target)

    # Generate must_commit_together groups
    must_commit_together = _generate_must_commit_together(audit_result.findings)

    # Step 2.8: Populate forbidden_overwrites using classify_owned_path
    forbidden_overwrites: list[str] = []
    try:
        ownership = load_memory_ownership(target)
        # Check all files in the project
        for item in target.rglob("*"):
            if item.is_file():
                try:
                    rel_path = item.relative_to(target).as_posix()
                    classification = classify_owned_path(rel_path, ownership=ownership)
                    if isinstance(classification, Owned):
                        forbidden_overwrites.append(rel_path)
                except (ValueError, OSError):
                    pass
    except Exception:
        # Fallback to legacy patterns if ownership loading fails
        forbidden_overwrites = LEGACY_FORBIDDEN_OVERWRITE_PATTERNS.copy()

    total_items = sum(len(v) for v in buckets.values())

    return MigrationPlan(
        target=str(target.resolve()),
        buckets=buckets,
        actions=actions,
        risk_level=risk_level,
        requires_human_confirmation=requires_confirmation,
        backup_plan=backup_plan,
        rollback_plan=rollback_plan,
        forbidden_overwrites=forbidden_overwrites if forbidden_overwrites else LEGACY_FORBIDDEN_OVERWRITE_PATTERNS.copy(),
        must_commit_together=must_commit_together,
        total_items=total_items,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit project memory layout and detect legacy/residue patterns.")
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Path to the project root to audit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "--severity",
        type=str,
        choices=["P0", "P1", "P2"],
        default=None,
        help="Filter findings by severity (P0=most severe).",
    )
    args = parser.parse_args(argv)

    result = audit_project_layout(args.target, severity_filter=args.severity)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=" * 70)
        print("Project Memory Layout Audit Report")
        print("=" * 70)
        print(f"Target: {result.target}")
        print(f"Scanned: {result.scanned_dirs} dirs, {result.scanned_files} files")
        print("-" * 70)

        if not result.findings:
            print("No findings. Project appears clean.")
        else:
            for f in result.findings:
                print(f"[{f.severity}] {f.kind}: {f.path}")
                print(f"    Message: {f.message}")
                print(f"    Suggested bucket: {f.suggested_bucket}")
                print()

        summary = result.to_dict()["summary"]
        print("-" * 70)
        print(f"Summary: {summary['total']} findings (P0: {summary['p0']}, P1: {summary['p1']}, P2: {summary['p2']})")
        print("=" * 70)

    return 0


def plan_main(argv: list[str] | None = None) -> int:
    """Entry point for memory-plan-residue CLI."""
    parser = argparse.ArgumentParser(description="Generate migration plan for memory residue cleanup.")
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Path to the project root to analyze.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Output results as JSON (default: True).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write plan to file instead of stdout.",
    )
    args = parser.parse_args(argv)

    # First run audit
    audit_result = audit_project_layout(args.target)

    # Generate migration plan
    plan = plan_residue_migration(audit_result, args.target)

    plan_dict = plan.to_dict()

    if args.output:
        args.output.write_text(json.dumps(plan_dict, indent=2, ensure_ascii=False))
        print(f"Migration plan written to: {args.output}")
    else:
        print(json.dumps(plan_dict, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
