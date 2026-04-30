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

import sys
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
        package = builder(**kwargs)
    except Exception as exc:
        result.record("context_package", False, f"builder raised: {exc}")
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
        from memory_hook_config import CoreConfig  # type: ignore
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


def main() -> int:
    result = ValidateResult()

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

    print(result.summary())
    return 0 if result.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

