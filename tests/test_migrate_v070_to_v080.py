"""Tests for migrate_v070_to_v080: 0.7→0.8 migration with [global_kb] injection.

Covers VAL-MIGRATE-001 through VAL-MIGRATE-005 and VAL-CROSS-002.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from memory_core.tools.adapter_toml_schema import load_adapter_toml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_main(argv: list[str]) -> int:
    """Invoke migrate_project_memory.main() with patched sys.argv."""
    from memory_core.tools.migrate_project_memory import main
    old_argv = sys.argv
    try:
        sys.argv = ["memory-migrate", *argv]
        return main()
    finally:
        sys.argv = old_argv


def _create_v070_project(tmp_path: Path) -> Path:
    """Create a 0.7.0 project skeleton with typical config sections.

    0.7.0 projects use the 0.5.0+ structure: memory/system/
    """
    memory_root = tmp_path / "memory" / "system"
    memory_root.mkdir(parents=True)

    # Create memory.lock at 0.7.0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lock_content = f"""# memory.lock
[memory]
memory_version = "0.7.0"
schema_version = "context-package-v1"
adapter_version = "builtin"
locked_at = "{now}"
lock_reason = "initial"
"""
    (memory_root / "memory.lock").write_text(lock_content, encoding="utf-8")

    # Create adapter.toml with typical 0.7.0 sections (no [global_kb])
    adapter_content = """# Memory Adapter Configuration

[core]
version = "0.7.0"
adapter = "default"

[policy]
legality_source_policy = "map-only"
registration_commit_policy = "same-commit"
registration_commit_phase = "post"

[routing]
project_name = "test-project"
project_scope = "test"
host = "factory"
canonical_files = ["CANONICAL.md", "STATE.md"]
# artifact_root is not set
"""
    (memory_root / "adapter.toml").write_text(adapter_content, encoding="utf-8")

    # Create migrations.log
    (memory_root / "migrations.log").write_text("# Migrations Log\n", encoding="utf-8")

    # For 0.7.0, the migrate function will need to find memory/system/
    # We need to also create a marker so migrate knows this is a 0.5.0+ project
    # Actually, the migrate function should handle this automatically by checking
    # for memory/system/ when .memory/ doesn't exist

    return tmp_path


def _read_adapter_toml(memory_root: Path) -> dict:
    """Read and parse adapter.toml."""
    adapter_path = memory_root / "adapter.toml"
    return tomllib.loads(adapter_path.read_text(encoding="utf-8"))


def _read_memory_lock(memory_root: Path) -> dict:
    """Read and parse memory.lock."""
    lock_path = memory_root / "memory.lock"
    return tomllib.loads(lock_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# VAL-MIGRATE-001: migrate 注入 [global_kb] 段
# ---------------------------------------------------------------------------

def test_migrate_injects_global_kb_section(tmp_path: Path) -> None:
    """0.7 项目执行 migrate 后,adapter.toml 应含 [global_kb] 段."""
    project_root = _create_v070_project(tmp_path)
    memory_root = project_root / "memory" / "system"

    exit_code = _call_main([
        "--target", str(project_root),
        "--from", "0.7.0",
        "--to", "0.8.0",
    ])
    assert exit_code == 0

    # Verify [global_kb] section exists
    adapter_data = _read_adapter_toml(memory_root)
    assert "global_kb" in adapter_data, "adapter.toml should contain [global_kb] section"

    # Verify default values
    global_kb = adapter_data["global_kb"]
    assert global_kb.get("enabled") is True, "enabled should default to true"
    assert "root" in global_kb, "root field should be present"
    # root should be ~/.memory/global-kb (expanded or unexpanded)
    root_value = global_kb["root"]
    assert "global-kb" in root_value or root_value.endswith(".memory/global-kb"), \
        f"root should point to global-kb, got {root_value}"


# ---------------------------------------------------------------------------
# VAL-MIGRATE-002: migrate 更新版本号
# ---------------------------------------------------------------------------

def test_migrate_updates_version_to_080(tmp_path: Path) -> None:
    """migrate 后 memory.lock 和 adapter.toml [core].version 应为 0.8.0."""
    project_root = _create_v070_project(tmp_path)
    memory_root = project_root / "memory" / "system"

    exit_code = _call_main([
        "--target", str(project_root),
        "--from", "0.7.0",
        "--to", "0.8.0",
    ])
    assert exit_code == 0

    # Verify memory.lock version
    lock_data = _read_memory_lock(memory_root)
    assert lock_data["memory"]["memory_version"] == "0.8.0", \
        "memory.lock memory_version should be 0.8.0"

    # Verify adapter.toml [core].version
    adapter_data = _read_adapter_toml(memory_root)
    assert adapter_data["core"]["version"] == "0.8.0", \
        "adapter.toml [core].version should be 0.8.0"


# ---------------------------------------------------------------------------
# VAL-MIGRATE-003: migrate 保留原有配置段
# ---------------------------------------------------------------------------

def test_migrate_preserves_existing_sections(tmp_path: Path) -> None:
    """migrate 不修改原有 [core]/[policy]/[routing] 段内容."""
    project_root = _create_v070_project(tmp_path)
    memory_root = project_root / "memory" / "system"

    # Capture state before migration
    adapter_before = _read_adapter_toml(memory_root)
    core_before = adapter_before.get("core", {})
    policy_before = adapter_before.get("policy", {})
    routing_before = adapter_before.get("routing", {})

    exit_code = _call_main([
        "--target", str(project_root),
        "--from", "0.7.0",
        "--to", "0.8.0",
    ])
    assert exit_code == 0

    # Verify sections preserved
    adapter_after = _read_adapter_toml(memory_root)

    # [core] should have same fields except version
    core_after = adapter_after.get("core", {})
    assert core_after.get("adapter") == core_before.get("adapter"), \
        "[core].adapter should be preserved"

    # [policy] should be identical
    policy_after = adapter_after.get("policy", {})
    assert policy_after == policy_before, \
        "[policy] section should be completely preserved"

    # [routing] should be identical
    routing_after = adapter_after.get("routing", {})
    assert routing_after == routing_before, \
        "[routing] section should be completely preserved"


# ---------------------------------------------------------------------------
# VAL-MIGRATE-004: migrate --dry-run 预览不执行
# ---------------------------------------------------------------------------

def test_migrate_dry_run_does_not_modify(tmp_path: Path) -> None:
    """--dry-run 显示将注入的变更但不实际修改."""
    project_root = _create_v070_project(tmp_path)
    memory_root = project_root / "memory" / "system"

    # Capture state before
    adapter_before = (memory_root / "adapter.toml").read_text(encoding="utf-8")
    lock_before = (memory_root / "memory.lock").read_text(encoding="utf-8")

    exit_code = _call_main([
        "--target", str(project_root),
        "--from", "0.7.0",
        "--to", "0.8.0",
        "--dry-run",
    ])
    assert exit_code == 0

    # Verify files unchanged
    adapter_after = (memory_root / "adapter.toml").read_text(encoding="utf-8")
    lock_after = (memory_root / "memory.lock").read_text(encoding="utf-8")

    assert adapter_after == adapter_before, \
        "adapter.toml should be unchanged after --dry-run"
    assert lock_after == lock_before, \
        "memory.lock should be unchanged after --dry-run"

    # Verify no [global_kb] was injected
    adapter_data = _read_adapter_toml(memory_root)
    assert "global_kb" not in adapter_data, \
        "[global_kb] should not be present after --dry-run"

    # Verify version still 0.7.0
    lock_data = _read_memory_lock(memory_root)
    assert lock_data["memory"]["memory_version"] == "0.7.0", \
        "version should still be 0.7.0 after --dry-run"


# ---------------------------------------------------------------------------
# VAL-MIGRATE-005: migrate 幂等
# ---------------------------------------------------------------------------

def test_migrate_idempotent_no_duplicate_injection(tmp_path: Path) -> None:
    """对已是 0.8.0 的项目再 migrate,不重复注入 [global_kb]."""
    project_root = _create_v070_project(tmp_path)
    memory_root = project_root / "memory" / "system"

    # First migration: 0.7.0 → 0.8.0
    exit_code = _call_main([
        "--target", str(project_root),
        "--from", "0.7.0",
        "--to", "0.8.0",
    ])
    assert exit_code == 0

    # Capture state after first migration
    adapter_after_first = (memory_root / "adapter.toml").read_text(encoding="utf-8")

    # Second migration: 0.8.0 → 0.8.0 (should be noop)
    exit_code = _call_main([
        "--target", str(project_root),
        "--from", "0.8.0",
        "--to", "0.8.0",
    ])
    assert exit_code == 0

    # Verify adapter.toml unchanged
    adapter_after_second = (memory_root / "adapter.toml").read_text(encoding="utf-8")
    assert adapter_after_second == adapter_after_first, \
        "adapter.toml should be unchanged on second migrate (idempotent)"

    # Verify only one [global_kb] section
    adapter_data = _read_adapter_toml(memory_root)
    assert "global_kb" in adapter_data
    # Count occurrences in raw text (should be exactly 1)
    global_kb_count = adapter_after_first.count("[global_kb]")
    assert global_kb_count == 1, \
        f"Should have exactly one [global_kb] section, found {global_kb_count}"


# ---------------------------------------------------------------------------
# VAL-CROSS-002: migrate 全流程 (0.7→0.8→fallback)
# ---------------------------------------------------------------------------

def test_migrate_full_flow_routing_fallback(tmp_path: Path) -> None:
    """0.7 项目 → migrate 0.8 → [global_kb] 注入 → 路由 fallback 可配置."""
    project_root = _create_v070_project(tmp_path)
    memory_root = project_root / "memory" / "system"

    # Migrate to 0.8.0
    exit_code = _call_main([
        "--target", str(project_root),
        "--from", "0.7.0",
        "--to", "0.8.0",
    ])
    assert exit_code == 0

    # Verify [global_kb] injected
    adapter_data = _read_adapter_toml(memory_root)
    assert "global_kb" in adapter_data

    # Load via AdapterConfig to verify parsing works
    config = load_adapter_toml(memory_root / "adapter.toml")
    assert config.global_kb_enabled is True, \
        "AdapterConfig should parse global_kb_enabled=True"
    assert "global-kb" in config.global_kb_root, \
        f"AdapterConfig.global_kb_root should point to global-kb, got {config.global_kb_root}"

    # Verify version updated
    lock_data = _read_memory_lock(memory_root)
    assert lock_data["memory"]["memory_version"] == "0.8.0"


# ---------------------------------------------------------------------------
# Additional edge case tests
# ---------------------------------------------------------------------------

def test_migrate_with_custom_global_kb_config(tmp_path: Path) -> None:
    """If adapter.toml already has [global_kb], migrate should preserve it."""
    project_root = tmp_path / "memory" / "system"
    project_root.mkdir(parents=True)

    # Create adapter.toml with custom [global_kb]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lock_content = f"""# memory.lock
[memory]
memory_version = "0.7.0"
schema_version = "context-package-v1"
adapter_version = "builtin"
locked_at = "{now}"
lock_reason = "initial"
"""
    (project_root / "memory.lock").write_text(lock_content, encoding="utf-8")

    adapter_content = """# Memory Adapter Configuration

[core]
version = "0.7.0"
adapter = "default"

[routing]
project_name = "test"
project_scope = "test"
host = "factory"

[global_kb]
enabled = false
root = "/custom/path"
"""
    (project_root / "adapter.toml").write_text(adapter_content, encoding="utf-8")
    (project_root / "migrations.log").write_text("# Migrations Log\n", encoding="utf-8")

    exit_code = _call_main([
        "--target", str(tmp_path),
        "--from", "0.7.0",
        "--to", "0.8.0",
    ])
    assert exit_code == 0

    # Verify custom config preserved
    adapter_data = _read_adapter_toml(project_root)
    assert adapter_data["global_kb"]["enabled"] is False
    assert adapter_data["global_kb"]["root"] == "/custom/path"
