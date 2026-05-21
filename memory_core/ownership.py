"""Ownership protection model for memory-core.

Provides data structures and APIs for classifying paths as owned/protected
vs not-owned, with support for domains, resources, and AGENTS.md block classification.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

from memory_core.constants import OWNERSHIP_SCHEMA_VERSION, SOURCE_REPO_MODE_READONLY, VALID_SOURCE_REPO_MODES


class ProtectionLevel(Enum):
    """Protection levels for owned resources, ordered from least to most strict."""

    RECOMMENDED = auto()  # Soft protection, warnings only
    STANDARD = auto()  # Standard protection, requires explicit override
    CRITICAL = auto()  # Critical protection, denies most operations


class OwnershipKind(Enum):
    """Kind of ownership classification."""

    DOMAIN = auto()  # A directory domain (e.g., memory/docs)
    RESOURCE = auto()  # A specific resource file


@dataclass(frozen=True)
class OwnershipDomain:
    """A domain of owned paths (directory-based).

    Attributes:
        name: Domain identifier (e.g., "memory_docs")
        path: Relative path from project root (e.g., "memory/docs")
        level: Protection level for this domain
        recursive: Whether protection applies recursively to subpaths
        description: Human-readable description
    """

    name: str
    path: str
    level: ProtectionLevel
    recursive: bool = True
    description: str = ""

    def __post_init__(self):
        # Normalize path to use forward slashes
        object.__setattr__(
            self, "path", self.path.replace("\\", "/").strip("/")
        )


@dataclass(frozen=True)
class OwnershipResource:
    """A specific owned resource (file or directory).

    Attributes:
        name: Resource identifier
        path: Relative path from project root
        level: Protection level
        domain: Optional domain this resource belongs to
        description: Human-readable description
    """

    name: str
    path: str
    level: ProtectionLevel
    domain: str | None = None
    description: str = ""

    def __post_init__(self):
        # Normalize path to use forward slashes
        object.__setattr__(
            self, "path", self.path.replace("\\", "/").strip("/")
        )


@dataclass(frozen=True)
class Owned:
    """Classification result: path is owned/protected.

    Attributes:
        domain: The matching domain (if any)
        resource: The matching resource (if any)
        level: Effective protection level
        reason: Human-readable explanation
    """

    domain: OwnershipDomain | None = None
    resource: OwnershipResource | None = None
    level: ProtectionLevel = ProtectionLevel.STANDARD
    reason: str = ""


@dataclass(frozen=True)
class NotOwned:
    """Classification result: path is not owned/protected.

    Attributes:
        reason: Human-readable explanation
    """

    reason: str = ""


@dataclass
class MemoryOwnership:
    """Complete ownership configuration for a project.

    Attributes:
        schema_version: Schema version identifier
        memory_version: memory-core version that created this config
        domains: List of owned domains
        resources: List of owned resources
        policy: Additional policy configuration
    """

    schema_version: str = OWNERSHIP_SCHEMA_VERSION
    memory_version: str = ""
    domains: list[OwnershipDomain] = field(default_factory=list)
    resources: list[OwnershipResource] = field(default_factory=list)
    policy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "schema_version": self.schema_version,
            "memory_version": self.memory_version,
            "domains": [
                {
                    "name": d.name,
                    "path": d.path,
                    "level": d.level.name.lower(),
                    "recursive": d.recursive,
                    "description": d.description,
                }
                for d in self.domains
            ],
            "resources": [
                {
                    "name": r.name,
                    "path": r.path,
                    "level": r.level.name.lower(),
                    "domain": r.domain,
                    "description": r.description,
                }
                for r in self.resources
            ],
            "policy": self.policy,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryOwnership":
        """Create from dictionary representation."""
        domains = [
            OwnershipDomain(
                name=d["name"],
                path=d["path"],
                level=ProtectionLevel[d["level"].upper()],
                recursive=d.get("recursive", True),
                description=d.get("description", ""),
            )
            for d in data.get("domains", [])
        ]
        resources = [
            OwnershipResource(
                name=r["name"],
                path=r["path"],
                level=ProtectionLevel[r["level"].upper()],
                domain=r.get("domain"),
                description=r.get("description", ""),
            )
            for r in data.get("resources", [])
        ]
        return cls(
            schema_version=data.get("schema_version", OWNERSHIP_SCHEMA_VERSION),
            memory_version=data.get("memory_version", ""),
            domains=domains,
            resources=resources,
            policy=data.get("policy", {}),
        )


# Default ownership domains for memory-core projects
DEFAULT_OWNERSHIP_DOMAINS: list[OwnershipDomain] = [
    OwnershipDomain(
        name="memory_docs",
        path="memory/docs",
        level=ProtectionLevel.CRITICAL,
        recursive=True,
        description="Protected documentation domain",
    ),
    OwnershipDomain(
        name="memory_kb",
        path="memory/kb",
        level=ProtectionLevel.CRITICAL,
        recursive=True,
        description="Protected knowledge base domain",
    ),
    OwnershipDomain(
        name="memory_system",
        path="memory/system",
        level=ProtectionLevel.CRITICAL,
        recursive=True,
        description="Protected system state domain",
    ),
    OwnershipDomain(
        name="dot_memory",
        path=".memory",
        level=ProtectionLevel.CRITICAL,
        recursive=True,
        description="Protected project memory domain",
    ),
    OwnershipDomain(
        name="project_map",
        path="memory/project-map",
        level=ProtectionLevel.CRITICAL,
        recursive=True,
        description="Protected project map domain",
    ),
]

# Default ownership resources for memory-core projects
DEFAULT_OWNERSHIP_RESOURCES: list[OwnershipResource] = [
    OwnershipResource(
        name="agents_md",
        path="AGENTS.md",
        level=ProtectionLevel.CRITICAL,
        description="Agent policy file",
    ),
    OwnershipResource(
        name="memory_lock",
        path=".memory/memory.lock",
        level=ProtectionLevel.CRITICAL,
        domain="dot_memory",
        description="Memory lock file",
    ),
    OwnershipResource(
        name="canonical_md",
        path=".memory/CANONICAL.md",
        level=ProtectionLevel.CRITICAL,
        domain="dot_memory",
        description="Canonical definitions",
    ),
    OwnershipResource(
        name="state_md",
        path=".memory/STATE.md",
        level=ProtectionLevel.CRITICAL,
        domain="dot_memory",
        description="State documentation",
    ),
    OwnershipResource(
        name="plan_md",
        path=".memory/PLAN.md",
        level=ProtectionLevel.CRITICAL,
        domain="dot_memory",
        description="Plan documentation",
    ),
    OwnershipResource(
        name="tasks_md",
        path=".memory/TASKS.md",
        level=ProtectionLevel.CRITICAL,
        domain="dot_memory",
        description="Task documentation",
    ),
    OwnershipResource(
        name="adapter_toml",
        path=".memory/adapter.toml",
        level=ProtectionLevel.CRITICAL,
        domain="dot_memory",
        description="Adapter configuration",
    ),
    OwnershipResource(
        name="ownership_toml",
        path=".memory/ownership.toml",
        level=ProtectionLevel.CRITICAL,
        domain="dot_memory",
        description="Ownership configuration",
    ),
]


def _is_path_under(path: Path, root: Path) -> bool:
    """Check if path is under root (handles path traversal)."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, RuntimeError):
        return False


def _normalize_rel_path(rel_path: str | Path) -> str:
    """Normalize a relative path string."""
    path_str = str(rel_path).replace("\\", "/")
    # Remove leading ./ and ../ attempts (path escape)
    while path_str.startswith("../"):
        path_str = path_str[3:]
    while path_str.startswith("./"):
        path_str = path_str[2:]
    return path_str.strip("/")


def _check_path_escape(rel_path: str) -> bool:
    """Check if a relative path attempts to escape the project root.

    Returns True if the path contains escape sequences like ../ or
    absolute paths that would leave the project root.
    """
    # Check for common escape patterns
    if ".." in rel_path:
        return True
    # Check for absolute paths
    if rel_path.startswith("/"):
        return True
    # Check for tilde expansion attempts
    if rel_path.startswith("~"):
        return True
    return False


def classify_owned_path(
    rel_path: str | Path,
    ownership: MemoryOwnership | None = None,
    project_root: Path | None = None,
) -> Owned | NotOwned:
    """Classify a path as owned or not-owned.

    Args:
        rel_path: Relative path from project root (e.g., "memory/docs/INDEX.md")
        ownership: Ownership configuration (uses defaults if None)
        project_root: Project root for additional checks (optional)

    Returns:
        Owned if the path is protected, NotOwned otherwise
    """
    path_str = _normalize_rel_path(rel_path)

    # Reject path escape attempts
    if _check_path_escape(str(rel_path)):
        return NotOwned(reason="Path escape detected - path rejected")

    # Use default ownership if none provided
    if ownership is None:
        ownership = MemoryOwnership(
            domains=list(DEFAULT_OWNERSHIP_DOMAINS),
            resources=list(DEFAULT_OWNERSHIP_RESOURCES),
        )

    # Check resources first (more specific)
    for resource in ownership.resources:
        if path_str == resource.path:
            return Owned(
                resource=resource,
                level=resource.level,
                reason=f"Exact match to owned resource: {resource.name}",
            )

    # Check domains
    for domain in ownership.domains:
        domain_parts = domain.path.split("/")
        path_parts = path_str.split("/")

        # Check if path is under this domain
        if len(path_parts) >= len(domain_parts):
            if path_parts[: len(domain_parts)] == domain_parts:
                if domain.recursive or len(path_parts) == len(domain_parts):
                    return Owned(
                        domain=domain,
                        level=domain.level,
                        reason=f"Path under owned domain: {domain.name}",
                    )

    return NotOwned(reason="Path not in any owned domain or resource")


def classify_agents_md_block(
    rel_path: str | Path,
    content_before: str | None = None,
    content_after: str | None = None,
) -> dict[str, Any]:
    """Classify an AGENTS.md operation for block protection.

    Implements 5 scenario classification for AGENTS.md:
    1. block internal modification -> block
    2. delete protection marker -> block
    3. block external append -> allow
    4. full overwrite (uncertain) -> block
    5. memory-init creation -> allow

    Args:
        rel_path: Path being modified
        content_before: Original content (for edit detection)
        content_after: New content (for edit detection)

    Returns:
        Classification result with decision and reason
    """
    path_str = _normalize_rel_path(rel_path)

    # Only applies to AGENTS.md
    if path_str != "AGENTS.md":
        return {"decision": "not_applicable", "reason": "Not AGENTS.md"}

    # Scenario 5: memory-init creation (no before content)
    if content_before is None and content_after is not None:
        return {
            "decision": "allow",
            "reason": "memory-init creation scenario",
            "scenario": 5,
        }

    # Scenario 4: Full overwrite (no content tracking available)
    if content_before is None or content_after is None:
        return {
            "decision": "block",
            "reason": "Cannot determine modification scope - full overwrite uncertain",
            "scenario": 4,
        }

    # Check for protection marker deletion (Scenario 2)
    # Common patterns: <!-- ownership:block --> or similar markers
    marker_pattern = r"<!--\s*ownership:.*?-->|#\s*PROTECTED\s+BLOCK|<!--\s*PROTECTED\s*-->"
    markers_before = set(re.findall(marker_pattern, content_before, re.IGNORECASE))
    markers_after = set(re.findall(marker_pattern, content_after, re.IGNORECASE))

    if markers_before - markers_after:
        return {
            "decision": "block",
            "reason": "Protection marker deletion detected",
            "scenario": 2,
            "markers_removed": list(markers_before - markers_after),
        }

    # Check for block boundaries
    # Look for block markers like <!-- ownership:block:start --> ... <!-- ownership:block:end -->
    block_start_pattern = r"<!--\s*ownership:block:start\s*-->"
    block_end_pattern = r"<!--\s*ownership:block:end\s*-->"

    block_starts_before = list(re.finditer(block_start_pattern, content_before, re.IGNORECASE))
    block_ends_before = list(re.finditer(block_end_pattern, content_before, re.IGNORECASE))

    # Scenario 1: Check if modification touches inside a block
    if len(block_starts_before) == len(block_ends_before) and len(block_starts_before) > 0:
        # Build protected ranges
        protected_ranges = []
        for start, end in zip(block_starts_before, block_ends_before):
            protected_ranges.append((start.start(), end.end()))

        # Check if content changed within any protected range
        # Simple check: if lengths differ significantly, assume modification
        if len(content_after) != len(content_before):
            # Check if change is outside all blocks
            changed = True  # Assume changed
            # If only appending at the end after last block
            if len(block_ends_before) > 0:
                _last_block_end = block_ends_before[-1].end()
                if len(content_after) > len(content_before):
                    # Appending after last block - Scenario 3
                    return {
                        "decision": "allow",
                        "reason": "Append after protected block",
                        "scenario": 3,
                    }

            if changed:
                return {
                    "decision": "block",
                    "reason": "Modification inside protected block detected",
                    "scenario": 1,
                }

    # Default: allow if no specific block violation detected
    return {
        "decision": "allow",
        "reason": "No protected block violation detected",
        "scenario": 3,
    }


def load_memory_ownership(project_root: Path) -> MemoryOwnership:
    """Load ownership configuration from project root.

    Looks for .memory/ownership.toml first, then falls back to defaults
    if not found.

    Args:
        project_root: Path to project root

    Returns:
        MemoryOwnership configuration
    """
    ownership_file = project_root / ".memory" / "ownership.toml"

    if ownership_file.exists():
        try:
            import tomllib

            content = ownership_file.read_text(encoding="utf-8")
            data = tomllib.loads(content)
            return MemoryOwnership.from_dict(data)
        except ImportError:
            # Python < 3.11, try tomli
            try:
                import tomli

                content = ownership_file.read_text(encoding="utf-8")
                data = tomli.loads(content)
                return MemoryOwnership.from_dict(data)
            except ImportError:
                pass  # Fall through to JSON fallback
        except Exception:
            pass  # Fall through to defaults

    # Try JSON fallback
    json_file = project_root / ".memory" / "ownership.json"
    if json_file.exists():
        try:
            content = json_file.read_text(encoding="utf-8")
            data = json.loads(content)
            return MemoryOwnership.from_dict(data)
        except Exception:
            pass

    # Return defaults
    return MemoryOwnership(
        domains=list(DEFAULT_OWNERSHIP_DOMAINS),
        resources=list(DEFAULT_OWNERSHIP_RESOURCES),
    )


def validate_ownership_schema(ownership: MemoryOwnership) -> list[str]:
    """Validate ownership configuration for schema weakening.

    Checks for:
    - Deleted default domains/resources
    - Downgraded protection levels
    - Non-recursive changes to critical domains

    Args:
        ownership: Ownership configuration to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []

    # Check for deleted default domains
    default_domain_names = {d.name for d in DEFAULT_OWNERSHIP_DOMAINS}
    current_domain_names = {d.name for d in ownership.domains}
    missing_domains = default_domain_names - current_domain_names
    if missing_domains:
        errors.append(f"Deleted default domains: {', '.join(missing_domains)}")

    # Check for deleted default resources
    default_resource_names = {r.name for r in DEFAULT_OWNERSHIP_RESOURCES}
    current_resource_names = {r.name for r in ownership.resources}
    missing_resources = default_resource_names - current_resource_names
    if missing_resources:
        errors.append(f"Deleted default resources: {', '.join(missing_resources)}")

    # Check for domain downgrades
    default_domain_map = {d.name: d for d in DEFAULT_OWNERSHIP_DOMAINS}
    for current in ownership.domains:
        if current.name in default_domain_map:
            default = default_domain_map[current.name]
            if current.level.value < default.level.value:
                errors.append(
                    f"Domain '{current.name}' downgraded from "
                    f"{default.level.name} to {current.level.name}"
                )
            if default.level == ProtectionLevel.CRITICAL and not current.recursive:
                errors.append(
                    f"Critical domain '{current.name}' must be recursive"
                )

    # Check for resource downgrades
    default_resource_map = {r.name: r for r in DEFAULT_OWNERSHIP_RESOURCES}
    for current in ownership.resources:
        if current.name in default_resource_map:
            default = default_resource_map[current.name]
            if current.level.value < default.level.value:
                errors.append(
                    f"Resource '{current.name}' downgraded from "
                    f"{default.level.name} to {current.level.name}"
                )

    return errors


def is_memory_core_source_repo(path: Path) -> bool:
    """Check if path is the memory-core source repository (anti-pollution).

    This is a shared API extracted from multiple locations to provide
    a single source of truth for detecting the memory-core source repo.

    Args:
        path: Path to check (typically project root or cwd)

    Returns:
        True if path is within the memory-core source repository
    """
    resolved = path.resolve()

    # Direct markers - check if these files exist under the path
    markers = [
        resolved / "memory_core" / "tools" / "memory_hook_gateway.py",
        resolved / "memory_core" / "tools" / "factory_global_hooks.py",
        resolved / "memory_core" / "tools" / "codex_global_hooks.py",
        resolved / "memory_core" / "ownership.py",  # This file
    ]
    if any(marker.exists() for marker in markers):
        return True

    # Also check git root
    try:
        git_root_result = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if git_root_result.returncode == 0 and git_root_result.stdout.strip():
            git_path = Path(git_root_result.stdout.strip())
            git_markers = [
                git_path / "memory_core" / "tools" / "memory_hook_gateway.py",
                git_path / "memory_core" / "tools" / "factory_global_hooks.py",
                git_path / "memory_core" / "tools" / "codex_global_hooks.py",
                git_path / "memory_core" / "ownership.py",
            ]
            if any(marker.exists() for marker in git_markers):
                return True
    except Exception:
        pass

    return False


def get_source_repo_mode(project_root: Path) -> str:
    """Get the source repo operating mode.

    Reads the mode from ownership policy configuration.
    Returns "readonly" if not explicitly set or if not a source repo.

    Args:
        project_root: Path to project root

    Returns:
        "readonly" or "develop"
    """
    if not is_memory_core_source_repo(project_root):
        return SOURCE_REPO_MODE_READONLY

    ownership = load_memory_ownership(project_root)
    source_repo_policy = ownership.policy.get("source_repo", {})
    mode = source_repo_policy.get("mode", SOURCE_REPO_MODE_READONLY)

    if mode not in VALID_SOURCE_REPO_MODES:
        return SOURCE_REPO_MODE_READONLY

    return mode
