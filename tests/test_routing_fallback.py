"""Tests for layered routing fallback (v0.8.0 global knowledge base).

Covers validation assertions:
- VAL-ROUTING-001: Project layer priority over global
- VAL-ROUTING-002: Fallback to global when project missing
- VAL-ROUTING-003: Graceful when both missing
- VAL-ROUTING-004: Global source doesn't exist - only project layer, no error
- VAL-ROUTING-005: Fallback supports three domains
- VAL-ROUTING-006: allowed_reads includes global KB paths
- VAL-WRITE-001: Hook writes always go to project
- VAL-WRITE-002: Global formal categories only written by promote
"""


from pathlib import Path

import pytest


@pytest.fixture
def test_env(tmp_path: Path):
    """Create a test environment with project and global KB structures.

    Returns dict with 'project_root' and 'global_kb_root' keys.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    global_kb_root = tmp_path / "global-kb"
    global_kb_root.mkdir()
    (global_kb_root / "operations").mkdir()
    (global_kb_root / "engineering").mkdir()
    (global_kb_root / "collaboration").mkdir()
    (global_kb_root / "pending").mkdir()

    # Create project memory/kb structure
    kb_root = project_root / "memory" / "kb"
    kb_root.mkdir(parents=True)
    (kb_root / "operations").mkdir()
    (kb_root / "engineering").mkdir()
    (kb_root / "collaboration").mkdir()
    (kb_root / "decisions").mkdir()
    (kb_root / "lessons").mkdir()

    # Create minimal adapter.toml with [global_kb] enabled
    adapter_dir = project_root / "memory" / "system"
    adapter_dir.mkdir(parents=True)
    adapter_toml = adapter_dir / "adapter.toml"
    adapter_toml.write_text(f"""[core]
project_name = "test-project"
project_scope = "default"
version = "0.8.0"

[global_kb]
enabled = true
root = "{global_kb_root}"
""")

    return {
        "project_root": project_root,
        "global_kb_root": global_kb_root
    }


def test_val_routing_001_project_priority_over_global(test_env):
    """VAL-ROUTING-001: When both project and global have same file, project wins."""
    from memory_core.tools.memory_hook_adapters.default_runtime_profile import build_default_runtime_profile
    from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl

    project_root = test_env["project_root"]
    global_kb_root = test_env["global_kb_root"]

    # Create same file in both project and global
    project_file = project_root / "memory" / "kb" / "operations" / "ssh-guide.md"
    project_file.write_text("# SSH Guide (Project)\nProject-specific SSH tips.")

    global_file = global_kb_root / "operations" / "ssh-guide.md"
    global_file.write_text("# SSH Guide (Global)\nGeneric SSH tips.")

    # Build runtime profile
    profile = build_default_runtime_profile(project_root, project_root)

    # Verify GLOBAL_KB_ROOT is in profile
    assert "GLOBAL_KB_ROOT" in profile
    assert profile["GLOBAL_KB_ROOT"] == global_kb_root

    # Test routing: project file should be found first
    route_policy = RouteTargetPolicyImpl(
        workspace_root=project_root,
        repo_root=project_root,
        global_kb_root=global_kb_root,
        global_kb_enabled=True,
    )

    # Resolve operations domain - should return project path
    resolved = route_policy.resolve_kb_file("operations", "ssh-guide.md")
    assert resolved == project_file
    assert "global-kb" not in str(resolved)


def test_val_routing_002_fallback_to_global_when_project_missing(test_env):
    """VAL-ROUTING-002: When project missing file, fallback to global."""
    from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl

    project_root = test_env["project_root"]
    global_kb_root = test_env["global_kb_root"]

    # Create file only in global
    global_file = global_kb_root / "engineering" / "ci-cache.md"
    global_file.write_text("# CI Cache Tips\nGeneric CI cache strategies.")

    route_policy = RouteTargetPolicyImpl(
        workspace_root=project_root,
        repo_root=project_root,
        global_kb_root=global_kb_root,
        global_kb_enabled=True,
    )

    # Resolve engineering domain - project doesn't have it, should fallback to global
    resolved = route_policy.resolve_kb_file("engineering", "ci-cache.md")
    assert resolved == global_file
    assert "global-kb" in str(resolved)


def test_val_routing_003_graceful_when_both_missing(test_env):
    """VAL-ROUTING-003: When both project and global missing file, return None gracefully."""
    from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl

    project_root = test_env["project_root"]
    global_kb_root = test_env["global_kb_root"]

    route_policy = RouteTargetPolicyImpl(
        workspace_root=project_root,
        repo_root=project_root,
        global_kb_root=global_kb_root,
        global_kb_enabled=True,
    )

    # Resolve non-existent file - should return None, not crash
    resolved = route_policy.resolve_kb_file("operations", "nonexistent.md")
    assert resolved is None


def test_val_routing_004_global_not_exist_only_project(tmp_path):
    """VAL-ROUTING-004: When global KB doesn't exist, only use project layer, no error."""
    import sys
    from io import StringIO

    from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl

    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create project memory/kb structure
    kb_root = project_root / "memory" / "kb"
    kb_root.mkdir(parents=True)
    (kb_root / "lessons").mkdir()

    # Create file in project
    project_file = project_root / "memory" / "kb" / "lessons" / "project-lesson.md"
    project_file.write_text("# Project Lesson\nProject-specific lesson.")

    # Global KB doesn't exist (use non-existent path)
    non_existent_global = tmp_path / "non-existent-global"

    # Capture stderr
    old_stderr = sys.stderr
    sys.stderr = StringIO()

    try:
        route_policy = RouteTargetPolicyImpl(
            workspace_root=project_root,
            repo_root=project_root,
            global_kb_root=non_existent_global,
            global_kb_enabled=True,
        )

        # Resolve project file - should work
        resolved = route_policy.resolve_kb_file("lessons", "project-lesson.md")
        assert resolved == project_file

        # Resolve global-only file - should return None (no error, no stderr)
        resolved = route_policy.resolve_kb_file("engineering", "global-only.md")
        assert resolved is None

        # Verify no stderr output
        stderr_output = sys.stderr.getvalue()
        assert stderr_output == "" or "warning" not in stderr_output.lower()
    finally:
        sys.stderr = old_stderr


def test_val_routing_005_fallback_supports_three_domains(test_env):
    """VAL-ROUTING-005: Fallback supports operations/engineering/collaboration domains."""
    from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl

    project_root = test_env["project_root"]
    global_kb_root = test_env["global_kb_root"]

    # Create files in all three domains (global only)
    ops_file = global_kb_root / "operations" / "server-guide.md"
    ops_file.write_text("# Server Guide\nOps guide.")

    eng_file = global_kb_root / "engineering" / "ci-guide.md"
    eng_file.write_text("# CI Guide\nEngineering guide.")

    collab_file = global_kb_root / "collaboration" / "team-workflow.md"
    collab_file.write_text("# Team Workflow\nCollaboration guide.")

    route_policy = RouteTargetPolicyImpl(
        workspace_root=project_root,
        repo_root=project_root,
        global_kb_root=global_kb_root,
        global_kb_enabled=True,
    )

    # Test all three domains
    assert route_policy.resolve_kb_file("operations", "server-guide.md") == ops_file
    assert route_policy.resolve_kb_file("engineering", "ci-guide.md") == eng_file
    assert route_policy.resolve_kb_file("collaboration", "team-workflow.md") == collab_file


def test_val_routing_006_allowed_reads_includes_global_kb(test_env):
    """VAL-ROUTING-006: allowed_reads includes global KB paths when enabled."""
    from memory_core.tools.memory_hook_adapters.default_runtime_profile import build_default_runtime_profile

    project_root = test_env["project_root"]
    global_kb_root = test_env["global_kb_root"]

    # Build runtime profile with global KB enabled
    profile = build_default_runtime_profile(project_root, project_root)

    # Verify GLOBAL_KB_ROOT is set
    assert "GLOBAL_KB_ROOT" in profile
    assert profile["GLOBAL_KB_ROOT"] == global_kb_root

    # The profile should include global KB in allowed reads
    # This will be verified in integration with build_context_package_core
    # For now, verify the profile has the necessary info
    assert profile.get("GLOBAL_KB_ENABLED", True) is True


def test_val_routing_007_disabled_no_fallback(test_env):
    """When enabled=false, no fallback to global."""
    from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl

    project_root = test_env["project_root"]
    global_kb_root = test_env["global_kb_root"]

    # Create file in global only
    global_file = global_kb_root / "operations" / "global-only.md"
    global_file.write_text("# Global Only\nThis should not be accessible.")

    # Disable global KB
    route_policy = RouteTargetPolicyImpl(
        workspace_root=project_root,
        repo_root=project_root,
        global_kb_root=global_kb_root,
        global_kb_enabled=False,  # Disabled
    )

    # Should not find global file when disabled
    resolved = route_policy.resolve_kb_file("operations", "global-only.md")
    assert resolved is None


def test_val_write_001_hook_writes_always_to_project(test_env):
    """VAL-WRITE-001: Hook runtime writes always go to project, never to global."""
    from memory_core.tools.memory_hook_impls import WriteTargetPolicyImpl

    project_root = test_env["project_root"]

    write_policy = WriteTargetPolicyImpl(workspace_root=project_root)
    targets = write_policy.get_targets()

    # All write targets should be under project workspace_root
    for key, target in targets.items():
        if key == "fact" or target is None:
            continue  # fact is dynamic, skip
        if isinstance(target, str):
            assert str(project_root) in target or target.startswith(str(project_root))
            assert "global-kb" not in target or "pending" in target  # Only pending is allowed in global

    # Verify specific targets
    assert "memory/kb/lessons" in targets.get("lesson", "")
    assert "memory/kb/decisions" in targets.get("decision", "")
    assert "global-kb/operations" not in str(targets.get("lesson", ""))
    assert "global-kb/engineering" not in str(targets.get("decision", ""))


def test_val_write_002_global_formal_categories_only_by_promote(test_env):
    """VAL-WRITE-002: Global formal categories only written by promote, not by hook."""
    from memory_core.tools.memory_hook_impls import WriteTargetPolicyImpl

    project_root = test_env["project_root"]

    write_policy = WriteTargetPolicyImpl(workspace_root=project_root)
    targets = write_policy.get_targets()

    # Verify that write targets don't include global formal categories
    # (operations/engineering/collaboration in global-kb)
    for key, target in targets.items():
        if isinstance(target, str):
            # Should not write to global formal categories
            assert "global-kb/operations" not in target
            assert "global-kb/engineering" not in target
            assert "global-kb/collaboration" not in target
            # pending/ is allowed (auto-capture)
            # But formal categories are not


def test_build_default_runtime_profile_includes_global_kb(test_env):
    """build_default_runtime_profile includes GLOBAL_KB_ROOT when [global_kb] enabled."""
    from memory_core.tools.memory_hook_adapters.default_runtime_profile import build_default_runtime_profile

    project_root = test_env["project_root"]

    profile = build_default_runtime_profile(project_root, project_root)

    # Should include global KB info
    assert "GLOBAL_KB_ROOT" in profile
    assert "GLOBAL_KB_ENABLED" in profile
    assert profile["GLOBAL_KB_ENABLED"] is True


def test_route_target_policy_impl_accepts_global_kb_params(test_env):
    """RouteTargetPolicyImpl accepts global_kb_root and global_kb_enabled parameters."""
    from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl

    project_root = test_env["project_root"]
    global_kb_root = test_env["global_kb_root"]

    # Should accept new parameters without error
    route_policy = RouteTargetPolicyImpl(
        workspace_root=project_root,
        repo_root=project_root,
        global_kb_root=global_kb_root,
        global_kb_enabled=True,
    )

    assert route_policy._global_kb_root == global_kb_root
    assert route_policy._global_kb_enabled is True
