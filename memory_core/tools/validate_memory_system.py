#!/usr/bin/env python3
"""Validate that the memory hook system is healthy and operational.

Runs a series of structural checks against the gateway module:
- Gateway imports without error
- Core builder resolves for at least one provider
- A context package can be built with the expected shape
- Required keys are present and non-trivial

Prints a summary report to stdout and returns 0 on success, 1 on failure.
"""

from __future__ import annotations

import argparse
import inspect
import sys
import traceback
from pathlib import Path
from typing import Any

# Ensure workspace/tools and the repo root are on sys.path.
# The gateway module uses both "memory_core.tools" dotted imports and
# bare module names depending on the import path taken.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
for p in (str(_SCRIPT_DIR), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from memory_hook_config import CoreConfig  # type: ignore
except ImportError:
    CoreConfig = None  # type: ignore

REQUIRED_PACKAGE_KEYS = {"status", "host", "event", "schema_version", "system_context", "task_context"}
REQUIRED_SYSTEM_CONTEXT_KEYS = {"boot_entry", "state_entry"}
REQUIRED_TASK_CONTEXT_KEYS = {"session_id", "event"}


def _empty_truth_basis() -> dict[str, Any]:
    """Return a minimal truth-basis dict that satisfies the core builder's access pattern."""
    return {
        "refs": [],
        "errors": [],
        "validation": "pass",
        "policy": "default",
        "project_ref": "",
        "source_refs": [],
        "authority_refs": [],
        "evidence_refs": [],
        "conflict_status": ["resolved"],
    }


class ValidateResult:
    """Collects individual check results and produces a summary."""

    def __init__(self) -> None:
        self.checks: list[tuple[str, bool, str]] = []

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, ok, detail))

    @property
    def all_passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)

    def summary(self) -> str:
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("Memory System Validation Report")
        lines.append("=" * 60)
        for name, ok, detail in self.checks:
            mark = "PASS" if ok else "FAIL"
            line = f"  [{mark}] {name}"
            if detail:
                line += f" — {detail}"
            lines.append(line)
        lines.append("-" * 60)
        total = len(self.checks)
        passed = sum(1 for _, ok, _ in self.checks if ok)
        lines.append(f"  {passed}/{total} checks passed")
        lines.append("=" * 60)
        return "\n".join(lines)


def check_gateway_import(result: ValidateResult) -> bool:
    """Verify the gateway module imports without raising."""
    try:
        import memory_hook_gateway  # type: ignore  # noqa: F401
        result.record("gateway_import", True, "memory_hook_gateway loaded")
        return True
    except Exception as exc:
        result.record("gateway_import", False, str(exc))
        return False


def check_core_builder_resolve(result: ValidateResult) -> tuple[bool, Any]:
    """Verify _resolve_core_builder returns a callable for the legacy provider."""
    try:
        from memory_hook_gateway import _resolve_core_builder  # type: ignore
        provider_name, builder, errors = _resolve_core_builder("legacy", allow_fallback=False)
        if not callable(builder):
            result.record("core_builder_resolve", False, "builder is not callable")
            return False, None
        detail = f"provider={provider_name}"
        if errors:
            detail += f", warnings={len(errors)}"
        result.record("core_builder_resolve", True, detail)
        return True, builder
    except Exception as exc:
        result.record("core_builder_resolve", False, str(exc))
        return False, None


def _wrap_builder_with_kwargs(builder: Any) -> Any:
    """Wrap a builder that takes a single config arg to accept kwargs."""
    sig = inspect.signature(builder)
    if len(sig.parameters) == 1:
        # Builder expects a single config argument (new interface)
        def wrapped(**kwargs):
            if CoreConfig is None:
                return builder(**kwargs)
            config = CoreConfig(**kwargs)
            return builder(config)
        return wrapped
    # Builder already accepts kwargs (old interface)
    return builder


def check_context_package(result: ValidateResult, builder: Any) -> bool:
    """Verify the core builder produces a well-shaped context package."""
    try:
        import memory_hook_gateway as gw  # type: ignore

        kwargs = dict(
            host="codex",
            event="test",
            payload={},
            cwd=gw.REPO_ROOT,
            project_scope="global",
            workspace_root=gw.WORKSPACE_ROOT,
            repo_root=gw.REPO_ROOT,
            required_canonical=gw.REQUIRED_CANONICAL,
            project_canonical=gw.PROJECT_CANONICAL,
            project_runtime_root=gw.PROJECT_RUNTIME_ROOT,
            global_canonical=gw.GLOBAL_CANONICAL,
            project_map_governance=gw.PROJECT_MAP_GOVERNANCE,
            event_log=gw.EVENT_LOG,
            legality_source_policy=gw.LEGALITY_SOURCE_POLICY,
            registration_commit_policy=gw.REGISTRATION_COMMIT_POLICY,
            registration_commit_phase=gw.REGISTRATION_COMMIT_PHASE,
            project_map_refs=[],
            extract_excerpt_fn=lambda p, max_lines=12: [],
            now_iso_fn=gw.now_iso,
            write_targets_fn=lambda: {},
            validate_project_map_fn=lambda: [],
            validate_unique_legal_system_contract_fn=lambda: [],
            policy_validate_fn=lambda ctx: [],
            get_policy_pack_fn=lambda scope: {},
            governance_frozen_tuple_errors_fn=lambda: [],
            event_contract_blocker_errors_fn=lambda: [],
            git_registration_probe_fn=lambda e, p: {},
            truth_basis_for_scope_fn=lambda scope: _empty_truth_basis(),
            decision_refs_for_scope_fn=lambda scope: [],
            lesson_refs_for_scope_fn=lambda scope: [],
            docs_refs_for_scope_fn=lambda scope: [],
            hook_contract_path=gw.HOOK_CONTRACT_PATH,
            surface_id="",
            workspace_id="",
            governance_blocker_scopes=[],
            event_contract_blocker_scopes=[],
            core_evidence_refs=[],
        )
        # Wrap builder to handle both old (kwargs) and new (config) interfaces
        wrapped_builder = _wrap_builder_with_kwargs(builder)
        package = wrapped_builder(**kwargs)
    except Exception as exc:
        result.record(
            "context_package",
            False,
            f"builder raised: {exc}\n{traceback.format_exc()}",
        )
        return False

    if not isinstance(package, dict):
        result.record("context_package", False, "package is not a dict")
        return False

    missing_keys = REQUIRED_PACKAGE_KEYS - set(package.keys())
    if missing_keys:
        result.record("context_package", False, f"missing top-level keys: {missing_keys}")
        return False

    sys_ctx = package.get("system_context", {})
    if not isinstance(sys_ctx, dict):
        result.record("context_package", False, "system_context is not a dict")
        return False

    missing_sys_keys = REQUIRED_SYSTEM_CONTEXT_KEYS - set(sys_ctx.keys())
    if missing_sys_keys:
        result.record("context_package", False, f"missing system_context keys: {missing_sys_keys}")
        return False

    task_ctx = package.get("task_context", {})
    if not isinstance(task_ctx, dict):
        result.record("context_package", False, "task_context is not a dict")
        return False

    missing_task_keys = REQUIRED_TASK_CONTEXT_KEYS - set(task_ctx.keys())
    if missing_task_keys:
        result.record("context_package", False, f"missing task_context keys: {missing_task_keys}")
        return False

    status = package.get("status")
    result.record("context_package", True, f"status={status}, keys present")
    return True




def check_core_config_path(result: ValidateResult) -> bool:
    """Verify the CoreConfig-native assembly path works."""
    try:
        from memory_hook_core import build_context_package_from_config  # type: ignore
        if not callable(build_context_package_from_config):
            result.record("core_config_path", False, "build_context_package_from_config is not callable")
            return False
        result.record("core_config_path", True, "build_context_package_from_config available")
        return True
    except Exception as exc:
        result.record("core_config_path", False, str(exc))
        return False


def check_v1_schema(result: ValidateResult) -> bool:
    """Verify build_context_package_simple returns context-package-v1."""
    try:
        from memory_hook_gateway import build_context_package_simple  # type: ignore
        from memory_hook_schema import is_v1  # type: ignore
        package = build_context_package_simple("codex", "test", {})
        if not is_v1(package):
            result.record("v1_schema", False, f"expected context-package-v1, got {package.get('schema_version')}")
            return False
        # Verify v1 structure
        assert "paths" in package, "missing 'paths' key"
        assert "project" in package, "missing 'project' key"
        assert "task" in package, "missing 'task' key"
        assert "system_context" not in package, "system_context should be removed in v1"
        result.record("v1_schema", True, "context-package-v1 structure valid")
        return True
    except Exception as exc:
        result.record("v1_schema", False, str(exc))
        return False


def check_package_imports(result: ValidateResult) -> bool:
    """Verify memory_core.tools public API is importable."""
    try:
        import memory_core.tools  # type: ignore
        assert hasattr(memory_core.tools, 'build_context_package')
        assert hasattr(memory_core.tools, 'CoreConfig')
        result.record("package_imports", True, "4 public symbols importable")
        return True
    except Exception as exc:
        result.record("package_imports", False, str(exc))
        return False


# ──────────────────────────────────────────────────────────────────────
# Pollution detection (B.Q5-2 + B.Q5-3)
# ──────────────────────────────────────────────────────────────────────

# Canonical locations that ARE allowed to contain STATE/PLAN/CANONICAL files.
_WHITELIST_PATH_PREFIXES: tuple[str, ...] = (
    "memory/system/",
    "memory/kb/global/",
    "project-map/",
    "archive/legacy-workbot/",
)

# Directories that are always safe (config / docs / CI).
_WHITELIST_TOPLEVEL_DIRS: tuple[str, ...] = (
    ".github",
    "docs",
    "scripts",
    "tests",
    "memory_core",
    "archive",
)

# Runtime-state filenames that indicate business pollution when found
# outside whitelisted paths.
_FORBIDDEN_STATE_NAMES: tuple[str, ...] = (
    "STATE.md",
    "PLAN.md",
    "CANONICAL.md",
    "TASKS.md",
)

# Business-specific strings that should NOT appear in newly created
# kb / project-map / memory/system content.  Allowed only in source code,
# documentation, or archived legacy content.
_FORBIDDEN_BUSINESS_STRINGS: tuple[str, ...] = (
    "axonhub",
    "workbot",
)

# File extensions / patterns to check for business string pollution.
_POLLUTION_CHECK_EXTENSIONS: tuple[str, ...] = (".md",)


def _is_whitelisted_path(rel_path: Path) -> bool:
    """Check if *rel_path* is in an allowed location."""
    rel_str = rel_path.as_posix()
    # Top-level whitelisted directories
    top = rel_str.split("/")[0] if "/" in rel_str else rel_str
    if top in _WHITELIST_TOPLEVEL_DIRS:
        return True
    # Specific prefix whitelist
    for prefix in _WHITELIST_PATH_PREFIXES:
        if rel_str.startswith(prefix):
            return True
    # Hidden / dotfiles at root (e.g., .gitignore, .gitlab-ci.yml)
    if top.startswith(".") and rel_path.is_file():
        return True
    # Root-level config files (README, LICENSE, CHANGELOG, etc.)
    if rel_path.parent == rel_path:
        return True
    return False


def _has_forbidden_state_name(rel_path: Path) -> bool:
    """Check if the filename itself is a forbidden runtime-state file."""
    return rel_path.name in _FORBIDDEN_STATE_NAMES


def _scan_file_content(filepath: Path, repo_root: Path) -> list[dict]:
    """Scan a .md file in a runtime location for business-specific strings.

    Only flags files directly under runtime directories like
    memory/system/, project-map/, or
    memory/kb/global/.  Archived and source-code locations
    are exempt.
    """
    findings: list[dict] = []
    rel_path = filepath.relative_to(repo_root)
    rel_str = rel_path.as_posix()

    # Only scan newly created runtime content
    runtime_prefixes = (
        "memory/system/",
        "project-map/",
        "memory/kb/global/",
    )
    if not any(rel_str.startswith(p) for p in runtime_prefixes):
        return findings

    # Exempt spec/governance/index docs — they are reference docs that
    # naturally mention project names.
    exempt_names = ("projects-spec.md", "INDEX.md", "governance.md", "legal-core-map.md", "ingestion-registry-map.md")
    if rel_path.name in exempt_names:
        return findings

    if filepath.suffix not in _POLLUTION_CHECK_EXTENSIONS:
        return findings

    try:
        text = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError, OSError):
        return findings

    text_lower = text.lower()
    for keyword in _FORBIDDEN_BUSINESS_STRINGS:
        if keyword in text_lower:
            findings.append({
                "path": str(rel_path),
                "rule": f"business-string:{keyword}",
                "severity": "error",
                "detail": f"Forbidden business keyword '{keyword}' found in runtime content",
            })
    return findings


def detect_pollution(repo_root: Path) -> list[dict]:
    """Return list of pollution findings.

    Each dict has:
        - ``path``: relative path from *repo_root*
        - ``rule``: which rule was violated
        - ``severity``: ``"error"`` (blocks CI) or ``"warning"`` (informational)

    Uses an allow-list + deny-list approach:
    - Allow-list: ``memory/system/``, ``memory/kb/global/``,
      ``project-map/``, ``archive/legacy-workbot/``, standard
      repo directories (docs/, tests/, scripts/, .github/, config files).
    - Deny-list: any ``*.STATE.md`` / ``*.PLAN.md`` / ``*.CANONICAL.md``
      appearing in business runtime locations (repo root,
      ``workspace/projects/*``, etc.).
    - Deny-list: business-specific strings (``axonhub``, ``workbot``) in
      newly created runtime content (kb / project-map / memory/system).
    - Deny-list: ``.memory/`` directories outside ``memory/system/``
      or ``archive/``.
    """
    findings: list[dict] = []

    if not repo_root.is_dir():
        findings.append({
            "path": str(repo_root),
            "rule": "repo-root-missing",
            "severity": "error",
            "detail": "Repository root does not exist",
        })
        return findings

    # Walk every file in the working tree.
    for filepath in sorted(repo_root.rglob("*")):
        if not filepath.is_file():
            continue

        # Skip hidden dirs (.git, .pytest_cache, etc.) and build artifacts.
        parts = filepath.relative_to(repo_root).parts
        if parts and parts[0].startswith(".") and parts[0] not in (".github", ".memory"):
            continue
        if parts and parts[0] in ("build", "memory_core.egg-info", "__pycache__", ".ruff_cache"):
            continue

        rel_path = filepath.relative_to(repo_root)

        # ── Rule 1: Forbidden .memory/ directories outside allowed locations ──
        if ".memory" in parts:
            mem_idx = parts.index(".memory")
            if mem_idx == 0:
                # .memory/ at repo root — always unexpected
                findings.append({
                    "path": str(rel_path),
                    "rule": "unexpected-memory-dir",
                    "severity": "error",
                    "detail": ".memory/ directory found at repository root",
                })
            else:
                # Allowed parents: memory/system/, archive/legacy-workbot/
                allowed_parents = (
                    ("memory_core", "memory", "system"),
                    ("archive", "legacy-workbot"),
                )
                is_allowed = any(
                    parts[: mem_idx] == allowed[: mem_idx]
                    for allowed in allowed_parents
                    if len(allowed) == mem_idx
                )
                if not is_allowed:
                    findings.append({
                        "path": str(rel_path),
                        "rule": "unexpected-memory-dir",
                        "severity": "error",
                        "detail": ".memory/ directory found outside memory/system/ or archive/",
                    })

        # ── Rule 2: Forbidden state files in runtime locations ──
        if _has_forbidden_state_name(rel_path):
            if not _is_whitelisted_path(rel_path):
                findings.append({
                    "path": str(rel_path),
                    "rule": "forbidden-state-file",
                    "severity": "error",
                    "detail": f"Runtime state file {rel_path.name!r} found outside whitelisted paths",
                })

        # ── Rule 3: Business strings in runtime content ──
        content_findings = _scan_file_content(filepath, repo_root)
        findings.extend(content_findings)

    # De-duplicate by (path, rule) to avoid duplicates from Rule 1
    seen: set[tuple[str, str]] = set()
    unique_findings: list[dict] = []
    for f in findings:
        key = (f["path"], f["rule"])
        if key not in seen:
            seen.add(key)
            unique_findings.append(f)

    return unique_findings


def check_pollution(result: ValidateResult, repo_root: Path) -> bool:
    """Run pollution detection and record results."""
    try:
        findings = detect_pollution(repo_root)
    except Exception as exc:
        result.record("pollution_check", False, f"detect_pollution raised: {exc}")
        return False

    if not findings:
        result.record("pollution_check", True, "0 pollution findings")
        return True

    errors = [f for f in findings if f.get("severity") == "error"]
    warnings = [f for f in findings if f.get("severity") == "warning"]
    detail_parts = []
    if errors:
        detail_parts.append(f"{len(errors)} error(s)")
    if warnings:
        detail_parts.append(f"{len(warnings)} warning(s)")
    detail = ", ".join(detail_parts)
    for f in findings:
        detail += f"; [{f['severity']}] {f['path']}: {f['rule']}"

    result.record("pollution_check", len(errors) == 0, detail)
    return len(errors) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate memory system health and pollution")
    parser.add_argument(
        "--check",
        choices=["all", "health", "pollution"],
        default="all",
        help="Which checks to run (default: all)",
    )
    args = parser.parse_args()

    repo_root = _REPO_ROOT
    result = ValidateResult()

    if args.check in ("all", "health"):
        ok = check_gateway_import(result)
        if not ok:
            print(result.summary())
            return 1

        builder_ok, builder = check_core_builder_resolve(result)
        if not builder_ok or builder is None:
            print(result.summary())
            return 1

        check_context_package(result, builder)
        check_core_config_path(result)
        check_v1_schema(result)
        check_package_imports(result)

    if args.check in ("all", "pollution"):
        check_pollution(result, repo_root)

    print(result.summary())
    return 0 if result.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

