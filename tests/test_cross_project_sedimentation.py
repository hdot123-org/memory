#!/usr/bin/env python3
"""Tests for cross-project sedimentation flow (VAL-CROSS-003/004).

Integration tests verifying the full sedimentation pipeline:
- VAL-CROSS-003: Full flow from capture → promote → new project can read
- VAL-CROSS-004: Multi-project sharing of global KB

These tests combine:
1. Inline capture helper (replaces deleted auto_capture.capture_candidates)
2. Promote CLI (promote_global_kb.main)
3. Routing fallback (RouteTargetPolicyImpl.resolve_kb_file)
4. Runtime profile (build_default_runtime_profile)
"""

import os
from datetime import datetime
from pathlib import Path

import pytest


def _capture_to_pending(
    project_root: Path,
    global_kb_root: Path,
) -> list[dict]:
    """Inline helper replacing deleted auto_capture.capture_candidates.

    Scans project memory/kb/lessons/ and decisions/ for today's changes
    and copies them to global_kb_root/pending/ with source metadata.
    """
    candidates: list[dict] = []
    today = datetime.now().date()
    captured_at = datetime.now().isoformat()

    scan_dirs = [
        project_root / "memory" / "kb" / "lessons",
        project_root / "memory" / "kb" / "decisions",
    ]

    pending_dir = global_kb_root / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue

        for file_path in scan_dir.iterdir():
            if not file_path.is_file():
                continue

            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime.date() != today:
                    continue
            except (OSError, ValueError):
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                project_name = project_root.name
                category = file_path.parent.name
                pending_filename = f"{project_name}_{category}_{file_path.name}"
                pending_path = pending_dir / pending_filename

                metadata_lines = [
                    "---",
                    f"source_project: {project_root}",
                    f"source_file: {file_path.relative_to(project_root)}",
                    f"captured_at: {captured_at}",
                    "---",
                    "",
                ]

                with pending_path.open("w", encoding="utf-8") as f:
                    f.write("\n".join(metadata_lines))
                    f.write(content)

                candidates.append({
                    "source_file": str(file_path.relative_to(project_root)),
                    "source_project": str(project_root),
                    "captured_at": captured_at,
                    "pending_path": str(pending_path),
                })
            except (OSError, IOError):
                pass

    return candidates


@pytest.fixture
def shared_global_kb(tmp_path: Path) -> Path:
    """Create a shared global KB structure that multiple projects will use."""
    global_kb_root = tmp_path / "shared-global-kb"
    global_kb_root.mkdir()

    # Create domain directories
    for domain in ["operations", "engineering", "collaboration", "pending"]:
        (global_kb_root / domain).mkdir()

    # Create INDEX.md
    index_content = """# 全局知识库 (Global Knowledge Base)

全局知识库是三层记忆架构的第二层,存储跨项目通用的知识和经验。

## 域分类

### [operations/](./operations/)
运维域知识

### [engineering/](./engineering/)
工程域知识

### [collaboration/](./collaboration/)
协作域知识

### [pending/](./pending/)
待确认候选区
"""
    (global_kb_root / "INDEX.md").write_text(index_content)

    return global_kb_root


@pytest.fixture
def project_a(tmp_path: Path, shared_global_kb: Path) -> Path:
    """Create Project A with memory structure and global KB enabled."""
    project_a = tmp_path / "project-a"
    project_a.mkdir()

    # Create memory/kb structure
    (project_a / "memory" / "kb" / "lessons").mkdir(parents=True)
    (project_a / "memory" / "kb" / "decisions").mkdir(parents=True)
    (project_a / "memory" / "kb" / "operations").mkdir(parents=True)
    (project_a / "memory" / "kb" / "engineering").mkdir(parents=True)
    (project_a / "memory" / "kb" / "collaboration").mkdir(parents=True)

    # Create adapter.toml with [global_kb] enabled
    adapter_dir = project_a / "memory" / "system"
    adapter_dir.mkdir(parents=True)
    adapter_toml = adapter_dir / "adapter.toml"
    adapter_toml.write_text(f"""[core]
project_name = "project-a"
project_scope = "default"
version = "0.8.0"

[global_kb]
enabled = true
root = "{shared_global_kb}"
""")

    return project_a


@pytest.fixture
def project_b(tmp_path: Path, shared_global_kb: Path) -> Path:
    """Create Project B with memory structure and global KB enabled."""
    project_b = tmp_path / "project-b"
    project_b.mkdir()

    # Create memory/kb structure
    (project_b / "memory" / "kb" / "lessons").mkdir(parents=True)
    (project_b / "memory" / "kb" / "decisions").mkdir(parents=True)
    (project_b / "memory" / "kb" / "operations").mkdir(parents=True)
    (project_b / "memory" / "kb" / "engineering").mkdir(parents=True)
    (project_b / "memory" / "kb" / "collaboration").mkdir(parents=True)

    # Create adapter.toml with [global_kb] enabled
    adapter_dir = project_b / "memory" / "system"
    adapter_dir.mkdir(parents=True)
    adapter_toml = adapter_dir / "adapter.toml"
    adapter_toml.write_text(f"""[core]
project_name = "project-b"
project_scope = "default"
version = "0.8.0"

[global_kb]
enabled = true
root = "{shared_global_kb}"
""")

    return project_b


class TestVALCross003SedimentationFullFlow:
    """VAL-CROSS-003: 沉淀全流程(捕获→promote→新项目可读)

    Test the complete sedimentation pipeline:
    1. Project produces experience (lesson/decision)
    2. session-end captures to pending/
    3. promote moves to formal category
    4. New project can read via fallback routing
    """

    def test_capture_creates_pending_candidate(
        self, project_a: Path, shared_global_kb: Path
    ):
        """Step 1: Auto-capture creates pending candidate from today's changes."""
        # Create a lesson modified today
        today_ts = datetime.now().timestamp()
        lesson_file = project_a / "memory" / "kb" / "lessons" / "ssh-pitfall.md"
        lesson_file.write_text("# SSH Pitfall\n\nDon't forget to configure Tailscale.")
        os.utime(lesson_file, (today_ts, today_ts))

        # Capture candidates
        candidates = _capture_to_pending(
            project_root=project_a,
            global_kb_root=shared_global_kb,
        )

        # Should create pending candidate
        assert len(candidates) == 1
        assert "ssh-pitfall" in candidates[0]["source_file"]

        # Verify file exists in pending/
        pending_dir = shared_global_kb / "pending"
        pending_files = list(pending_dir.glob("*.md"))
        assert len(pending_files) == 1
        assert "ssh-pitfall" in pending_files[0].name

    def test_promote_moves_to_formal_category(
        self, project_a: Path, shared_global_kb: Path
    ):
        """Step 2: Promote moves file from pending/ to formal category."""
        from memory_core.tools.promote_global_kb import main as promote_main

        # Step 2a: Create and capture a lesson
        today_ts = datetime.now().timestamp()
        lesson_file = project_a / "memory" / "kb" / "lessons" / "ci-cache.md"
        lesson_file.write_text("# CI Cache\n\nUse pyc cache for faster builds.")
        os.utime(lesson_file, (today_ts, today_ts))

        _capture_to_pending(
            project_root=project_a,
            global_kb_root=shared_global_kb,
        )

        # Verify it's in pending/
        pending_dir = shared_global_kb / "pending"
        pending_files = list(pending_dir.glob("*.md"))
        assert len(pending_files) == 1
        pending_file = pending_files[0]

        # Step 2b: Promote to engineering/
        exit_code = promote_main([
            str(pending_file), "--to", "engineering",
            "--global-kb-root", str(shared_global_kb),
        ])
        assert exit_code == 0

        # Verify file moved from pending/ to engineering/
        remaining_pending = list(pending_dir.glob("*.md"))
        assert len(remaining_pending) == 0

        engineering_dir = shared_global_kb / "engineering"
        engineering_files = [f for f in engineering_dir.glob("*.md") if f.name != "README.md"]
        assert len(engineering_files) == 1
        assert "ci-cache" in engineering_files[0].name

    def test_new_project_can_read_promoted_knowledge(
        self, project_a: Path, project_b: Path, shared_global_kb: Path
    ):
        """Step 3: New project (B) can read promoted knowledge via fallback."""
        from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl
        from memory_core.tools.promote_global_kb import main as promote_main

        # Step 3a: Project A produces and promotes knowledge
        today_ts = datetime.now().timestamp()
        lesson_file = project_a / "memory" / "kb" / "lessons" / "docker-tips.md"
        lesson_file.write_text("# Docker Tips\n\nAlways use multi-stage builds.")
        os.utime(lesson_file, (today_ts, today_ts))

        _capture_to_pending(
            project_root=project_a,
            global_kb_root=shared_global_kb,
        )

        pending_dir = shared_global_kb / "pending"
        pending_file = list(pending_dir.glob("*.md"))[0]

        # Promote to operations/
        exit_code = promote_main([
            str(pending_file), "--to", "operations",
            "--global-kb-root", str(shared_global_kb),
        ])
        assert exit_code == 0

        # Step 3b: Project B (new project) can read via fallback
        route_policy_b = RouteTargetPolicyImpl(
            workspace_root=project_b,
            repo_root=project_b,
            global_kb_root=shared_global_kb,
            global_kb_enabled=True,
        )

        # Project B should find the promoted knowledge via fallback
        resolved = route_policy_b.resolve_kb_file("operations", pending_file.name)
        assert resolved is not None
        assert "docker-tips" in resolved.name
        assert "global-kb" in str(resolved) or "shared-global-kb" in str(resolved)
        assert resolved.exists()

        # Verify content is accessible
        content = resolved.read_text()
        assert "Docker Tips" in content
        assert "multi-stage" in content

    def test_full_sedimentation_flow_end_to_end(
        self, project_a: Path, project_b: Path, shared_global_kb: Path
    ):
        """Complete end-to-end test of sedimentation flow."""
        from memory_core.tools.memory_hook_adapters.default_runtime_profile import (
            build_default_runtime_profile,
        )
        from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl
        from memory_core.tools.promote_global_kb import main as promote_main

        # 1. Project A produces knowledge
        today_ts = datetime.now().timestamp()
        lesson_file = project_a / "memory" / "kb" / "decisions" / "api-versioning.md"
        lesson_file.write_text("# API Versioning Decision\n\nUse URL path versioning.")
        os.utime(lesson_file, (today_ts, today_ts))

        # 2. Session-end captures to pending
        candidates = _capture_to_pending(
            project_root=project_a,
            global_kb_root=shared_global_kb,
        )
        assert len(candidates) == 1
        assert "api-versioning" in candidates[0]["source_file"]

        # 3. Promote to formal category
        pending_dir = shared_global_kb / "pending"
        pending_file = list(pending_dir.glob("*.md"))[0]
        exit_code = promote_main([
            str(pending_file), "--to", "engineering",
            "--global-kb-root", str(shared_global_kb),
        ])
        assert exit_code == 0

        # 4. Verify Project B's runtime profile has global KB enabled
        profile_b = build_default_runtime_profile(project_b, project_b)
        assert profile_b["GLOBAL_KB_ENABLED"] is True
        assert profile_b["GLOBAL_KB_ROOT"] == shared_global_kb

        # 5. Project B can route to promoted knowledge
        route_policy_b = RouteTargetPolicyImpl(
            workspace_root=project_b,
            repo_root=project_b,
            global_kb_root=shared_global_kb,
            global_kb_enabled=True,
        )

        resolved = route_policy_b.resolve_kb_file("engineering", pending_file.name)
        assert resolved is not None
        assert "api-versioning" in resolved.name
        assert resolved.exists()

        content = resolved.read_text()
        assert "API Versioning" in content
        assert "URL path" in content


class TestVALCross004MultiProjectSharing:
    """VAL-CROSS-004: 多项目共享全局层

    Test that Project A and B share the same global KB,
    and A's promoted knowledge is readable by B.
    """

    def test_both_projects_use_same_global_kb_root(
        self, project_a: Path, project_b: Path, shared_global_kb: Path
    ):
        """Both projects should reference the same global KB root."""
        from memory_core.tools.memory_hook_adapters.default_runtime_profile import (
            build_default_runtime_profile,
        )

        # Build runtime profiles for both projects
        profile_a = build_default_runtime_profile(project_a, project_a)
        profile_b = build_default_runtime_profile(project_b, project_b)

        # Both should have global KB enabled
        assert profile_a["GLOBAL_KB_ENABLED"] is True
        assert profile_b["GLOBAL_KB_ENABLED"] is True

        # Both should point to the same global KB root
        assert profile_a["GLOBAL_KB_ROOT"] == profile_b["GLOBAL_KB_ROOT"]
        assert profile_a["GLOBAL_KB_ROOT"] == shared_global_kb

    def test_project_b_can_read_project_a_promoted_knowledge(
        self, project_a: Path, project_b: Path, shared_global_kb: Path
    ):
        """Project B should be able to read knowledge promoted by Project A."""
        from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl
        from memory_core.tools.promote_global_kb import main as promote_main

        # Project A promotes knowledge to engineering/
        today_ts = datetime.now().timestamp()
        lesson_file = project_a / "memory" / "kb" / "lessons" / "pytest-fixtures.md"
        lesson_file.write_text("# Pytest Fixtures\n\nUse @pytest.fixture for reusable setup.")
        os.utime(lesson_file, (today_ts, today_ts))

        _capture_to_pending(
            project_root=project_a,
            global_kb_root=shared_global_kb,
        )

        pending_dir = shared_global_kb / "pending"
        pending_file = list(pending_dir.glob("*.md"))[0]

        # Promote to engineering/
        exit_code = promote_main([
            str(pending_file), "--to", "engineering",
            "--global-kb-root", str(shared_global_kb),
        ])
        assert exit_code == 0

        # Project B can route to it
        route_policy_b = RouteTargetPolicyImpl(
            workspace_root=project_b,
            repo_root=project_b,
            global_kb_root=shared_global_kb,
            global_kb_enabled=True,
        )

        resolved = route_policy_b.resolve_kb_file("engineering", pending_file.name)
        assert resolved is not None
        assert "pytest-fixtures" in resolved.name
        assert resolved.exists()

        # Verify content matches what Project A promoted
        content = resolved.read_text()
        assert "Pytest Fixtures" in content
        assert "@pytest.fixture" in content

    def test_multiple_promotions_accessible_across_projects(
        self, project_a: Path, project_b: Path, shared_global_kb: Path
    ):
        """Multiple promoted files should all be accessible across projects."""
        from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl
        from memory_core.tools.promote_global_kb import main as promote_main

        # Create multiple knowledge items
        today_ts = datetime.now().timestamp()

        # Item 1: SSH guide
        ssh_file = project_a / "memory" / "kb" / "lessons" / "ssh-config.md"
        ssh_file.write_text("# SSH Config\n\nUse ~/.ssh/config for aliases.")
        os.utime(ssh_file, (today_ts, today_ts))

        # Item 2: CI optimization
        ci_file = project_a / "memory" / "kb" / "lessons" / "ci-optimization.md"
        ci_file.write_text("# CI Optimization\n\nCache dependencies aggressively.")
        os.utime(ci_file, (today_ts, today_ts))

        # Capture both
        candidates = _capture_to_pending(
            project_root=project_a,
            global_kb_root=shared_global_kb,
        )
        assert len(candidates) == 2

        # Promote to different domains
        pending_dir = shared_global_kb / "pending"
        pending_files = list(pending_dir.glob("*.md"))

        ssh_pending = [f for f in pending_files if "ssh" in f.name][0]
        ci_pending = [f for f in pending_files if "ci" in f.name][0]

        assert promote_main([
            str(ssh_pending), "--to", "operations",
            "--global-kb-root", str(shared_global_kb),
        ]) == 0
        assert promote_main([
            str(ci_pending), "--to", "engineering",
            "--global-kb-root", str(shared_global_kb),
        ]) == 0

        # Project B can access both
        route_policy_b = RouteTargetPolicyImpl(
            workspace_root=project_b,
            repo_root=project_b,
            global_kb_root=shared_global_kb,
            global_kb_enabled=True,
        )

        # Can access SSH guide in operations/
        resolved_ssh = route_policy_b.resolve_kb_file("operations", ssh_pending.name)
        assert resolved_ssh is not None
        assert "ssh-config" in resolved_ssh.name
        assert "SSH Config" in resolved_ssh.read_text()

        # Can access CI optimization in engineering/
        resolved_ci = route_policy_b.resolve_kb_file("engineering", ci_pending.name)
        assert resolved_ci is not None
        assert "ci-optimization" in resolved_ci.name
        assert "CI Optimization" in resolved_ci.read_text()

    def test_project_priority_over_global_still_holds(
        self, project_a: Path, project_b: Path, shared_global_kb: Path
    ):
        """Project-specific knowledge still takes priority over global KB."""
        from memory_core.tools.memory_hook_impls import RouteTargetPolicyImpl
        from memory_core.tools.promote_global_kb import main as promote_main

        # Project A promotes SSH guide to global
        today_ts = datetime.now().timestamp()
        global_ssh = project_a / "memory" / "kb" / "lessons" / "ssh-guide.md"
        global_ssh.write_text("# SSH Guide (Global)\n\nGeneric SSH tips.")
        os.utime(global_ssh, (today_ts, today_ts))

        _capture_to_pending(
            project_root=project_a,
            global_kb_root=shared_global_kb,
        )

        pending_dir = shared_global_kb / "pending"
        pending_file = list(pending_dir.glob("*.md"))[0]
        promote_main([
            str(pending_file), "--to", "operations",
            "--global-kb-root", str(shared_global_kb),
        ])

        # Project B has its own SSH guide
        project_b_ssh = project_b / "memory" / "kb" / "operations" / pending_file.name
        project_b_ssh.write_text("# SSH Guide (Project B)\n\nProject B specific SSH config.")

        # Project B's routing should prefer its own file
        route_policy_b = RouteTargetPolicyImpl(
            workspace_root=project_b,
            repo_root=project_b,
            global_kb_root=shared_global_kb,
            global_kb_enabled=True,
        )

        resolved = route_policy_b.resolve_kb_file("operations", pending_file.name)
        assert resolved == project_b_ssh
        assert "project-b" in str(resolved)

        # Content should be Project B's version
        content = resolved.read_text()
        assert "Project B" in content
        assert "Generic SSH tips" not in content
