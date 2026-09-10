"""Validation contract tests for wrapper probe implementation.

Tests all VAL-WRAP-* assertions from the validation contract.
These tests invoke the actual wrapper script via subprocess to verify
real-world behavior.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from memory_core.tools.factory_global_hooks import render_wrapper


@pytest.fixture
def wrapper_env():
    """Create a test environment with wrapper, gateway stub, and init stub."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create storage root
        storage_root = tmpdir / "storage"
        storage_root.mkdir()

        # Create gateway stub that outputs ROUTED_TO
        gateway_stub = tmpdir / "gateway-stub.sh"
        gateway_stub.write_text(
            "#!/bin/sh\n"
            'echo "ROUTED_TO=$MEMORY_HOOK_PROJECT_CWD"\n'
            'echo "ORIGINAL_CWD=$MEMORY_HOOK_ORIGINAL_CWD"\n'
            'echo "EVENT=$1"\n'
        )
        gateway_stub.chmod(0o755)

        # Create init stub (no-op)
        init_stub = tmpdir / "init-stub.sh"
        init_stub.write_text("#!/bin/sh\nexit 0\n")
        init_stub.chmod(0o755)

        # Render wrapper
        wrapper_content = render_wrapper(
            storage_root=storage_root,
            gateway_command=str(gateway_stub),
            init_command=str(init_stub),
        )

        wrapper_path = tmpdir / "wrapper.sh"
        wrapper_path.write_text(wrapper_content)
        wrapper_path.chmod(0o755)

        yield {
            "tmpdir": tmpdir,
            "storage_root": storage_root,
            "gateway_stub": gateway_stub,
            "init_stub": init_stub,
            "wrapper": wrapper_path,
            "errors_log": storage_root / "memory" / "system" / "errors.log",
        }


def run_wrapper(wrapper_env, cwd, event="session-start", extra_env=None):
    """Run the wrapper and return (exit_code, stdout, stderr)."""
    env = os.environ.copy()
    env["PWD"] = str(cwd)
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [str(wrapper_env["wrapper"]), "--host", "factory", "--event", event],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.returncode, result.stdout, result.stderr


def resolve_path(path):
    """Resolve path to handle macOS symlinks (/var -> /private/var)."""
    return str(Path(path).resolve())


def parse_output(stdout):
    """Parse ROUTED_TO and ORIGINAL_CWD from wrapper output."""
    result = {}
    for line in stdout.split("\n"):
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


# ============================================================================
# VAL-WRAP-001: Git root session routes to repo root (regression anchor)
# ============================================================================


def test_val_wrap_001_git_root_routes_to_repo_root(wrapper_env):
    """VAL-WRAP-001: Git root session routes to repo root."""
    repo = wrapper_env["tmpdir"] / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    (repo / ".git").mkdir(exist_ok=True)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, repo, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(repo)
    assert not (repo / "memory").exists()


def test_val_wrap_002_repo_subdir_routes_to_repo_root(wrapper_env):
    """VAL-WRAP-002: Repo subdirectory routes to repo root."""
    repo = wrapper_env["tmpdir"] / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    (repo / ".git").mkdir(exist_ok=True)

    subdir = repo / "src" / "deep"
    subdir.mkdir(parents=True)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, subdir, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(repo)


# ============================================================================
# VAL-WRAP-003: Non-git parent with single child repo routes to child
# ============================================================================


def test_val_wrap_003_non_git_parent_single_child_routes_to_child(wrapper_env):
    """VAL-WRAP-003: Non-git parent with single child repo routes to child."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    child = parent / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(child)
    assert not (parent / "memory").exists()
    assert stderr == ""


# ============================================================================
# VAL-WRAP-004: Non-git parent with ≥2 child repos → noop + stderr diagnostics
# ============================================================================


def test_val_wrap_004_two_candidates_noop_with_stderr(wrapper_env):
    """VAL-WRAP-004: Two candidates returns noop with stderr diagnostics."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    alpha = parent / "alpha"
    alpha.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=alpha, check=True, capture_output=True)

    beta = parent / "beta"
    beta.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=beta, check=True, capture_output=True)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    assert stdout.strip() == "{}"
    assert "ambiguous" in stderr
    assert "alpha" in stderr
    assert "beta" in stderr
    # Spec L148-149: diagnostics should be on a single line
    stderr_lines = [line for line in stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1
    assert "memory-project.toml" in stderr


def test_val_wrap_004_errors_log_session_start_only(wrapper_env):
    """VAL-WRAP-004: errors.log written only for session-start, not prompt-submit."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    alpha = parent / "alpha"
    alpha.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=alpha, check=True, capture_output=True)

    beta = parent / "beta"
    beta.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=beta, check=True, capture_output=True)

    # First call: prompt-submit (no log)
    run_wrapper(wrapper_env, parent, "prompt-submit")
    assert not wrapper_env["errors_log"].exists()

    # Second call: session-start (log created)
    run_wrapper(wrapper_env, parent, "session-start")
    assert wrapper_env["errors_log"].exists()
    content = wrapper_env["errors_log"].read_text()
    assert "session-start" in content


# ============================================================================
# VAL-WRAP-005: Non-git with 0 candidates → noop
# ============================================================================


def test_val_wrap_005_no_candidates_noop(wrapper_env):
    """VAL-WRAP-005: No candidates returns noop."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    assert stdout.strip() == "{}"
    # Should log to errors.log
    assert wrapper_env["errors_log"].exists()


# ============================================================================
# VAL-WRAP-006: Event gating (space/equals/missing syntax)
# ============================================================================


def test_val_wrap_006_event_space_syntax(wrapper_env):
    """VAL-WRAP-006: Event with space syntax (--event session-start)."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    assert wrapper_env["errors_log"].exists()


def test_val_wrap_006_event_equals_syntax(wrapper_env):
    """VAL-WRAP-006: Event with equals syntax (--event=session-start)."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    env = os.environ.copy()
    env["PWD"] = str(parent)

    # Manually invoke wrapper with --event= syntax
    result = subprocess.run(
        [str(wrapper_env["wrapper"]), "--host", "factory", "--event=session-start"],
        cwd=parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0
    assert wrapper_env["errors_log"].exists()


def test_val_wrap_006_event_prompt_submit_no_log(wrapper_env):
    """VAL-WRAP-006: prompt-submit event does not log."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "prompt-submit")

    assert exit_code == 0
    # errors.log should not exist or be empty
    if wrapper_env["errors_log"].exists():
        content = wrapper_env["errors_log"].read_text()
        assert content == ""


def test_val_wrap_006_missing_event_no_log_fourth_form(wrapper_env):
    """VAL-WRAP-006 fourth form (contract裁决 2026-09-10): missing --event → exit 0, no log.

    Contract says "按非 session-start" meaning missing event should NOT log.
    Previous implementation followed spec §3.1.4 contradictory version.
    """
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    env = os.environ.copy()
    env["PWD"] = str(parent)

    # Manually invoke wrapper WITHOUT --event flag
    result = subprocess.run(
        [str(wrapper_env["wrapper"]), "--host", "factory"],
        cwd=parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0
    # No errors.log should be created
    assert not wrapper_env["errors_log"].exists()


# ============================================================================
# VAL-WRAP-007: Worktree support (.git file)
# ============================================================================


def test_val_wrap_007_worktree_gitfile_counts_as_candidate(wrapper_env):
    """VAL-WRAP-007: Worktree child with .git file counts as candidate."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    # Main repo must live OUTSIDE parent so the worktree is the single
    # candidate (two candidates would trigger the ambiguity noop branch).
    main_repo = wrapper_env["tmpdir"] / "main-repo"
    main_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=main_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=main_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=main_repo, check=True, capture_output=True)
    (main_repo / "file.txt").write_text("test")
    subprocess.run(["git", "add", "."], cwd=main_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=main_repo, check=True, capture_output=True)

    worktree = parent / "worktree"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(worktree), "-b", "feature"],
        cwd=main_repo,
        check=True,
        capture_output=True,
    )

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(worktree)


# ============================================================================
# VAL-WRAP-008: Dangling .git file excluded
# ============================================================================


def test_val_wrap_008_dangling_gitfile_excluded(wrapper_env):
    """VAL-WRAP-008: Dangling .git file is excluded from candidates."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    real_child = parent / "real"
    real_child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=real_child, check=True, capture_output=True)

    dangling_child = parent / "dangling"
    dangling_child.mkdir()
    (dangling_child / ".git").write_text("gitdir: /nonexistent/path")

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(real_child)


# ============================================================================
# VAL-WRAP-010: Dataless .git directory does not trigger probe
# ============================================================================


def test_val_wrap_010_dataless_git_dir(wrapper_env):
    """VAL-WRAP-010: CWD with empty .git directory does not trigger probe (gate blocks it).

    The probe gate checks `[ ! -e "$PROJECT_CWD/.git" ]`. A dataless .git directory
    (empty dir, not a real repo) passes this existence check, so the probe is NOT triggered.
    The wrapper should treat CWD as-is (no routing to child repos).
    """
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()
    # Put a dataless .git directory in parent (not a real repo, just empty .git dir)
    (parent / ".git").mkdir()

    # Also put a real child repo
    child = parent / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    # CWD stays as parent because .git existence blocks probe (not dataless .git routing to child)
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(parent)
    # The child repo is NOT routed to
    assert resolve_path(output.get("ROUTED_TO")) != resolve_path(child)


def test_val_wrap_010_unreadable_gitfile_blocks_probe(wrapper_env):
    """VAL-WRAP-010 variant: CWD with chmod 000 .git file also blocks probe.

    An unreadable .git file passes `[ -e ... ]` existence check, so probe is suppressed.
    """
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()
    # Create a .git file with chmod 000
    gitfile = parent / ".git"
    gitfile.write_text("gitdir: /nonexistent")
    gitfile.chmod(0o000)

    child = parent / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    # CWD stays as parent because .git existence blocks probe
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(parent)

    # Cleanup: restore permissions so tmpdir can be cleaned
    gitfile.chmod(0o644)


# ============================================================================
# VAL-WRAP-011: Home directory guard
# ============================================================================


def test_val_wrap_011_home_exact_match_noop(wrapper_env):
    """VAL-WRAP-011: Exact $HOME match returns noop."""
    fake_home = wrapper_env["tmpdir"] / "home"
    fake_home.mkdir()

    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["PWD"] = str(fake_home)

    result = subprocess.run(
        [str(wrapper_env["wrapper"]), "--host", "factory", "--event", "session-start"],
        cwd=fake_home,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "{}"


# ============================================================================
# VAL-WRAP-012: Escape hatch
# ============================================================================


def test_val_wrap_012_escape_hatch_disables_probe(wrapper_env):
    """VAL-WRAP-012: Escape hatch disables probe."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    child = parent / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    extra_env = {"MEMORY_HOOK_DISABLE_DOWNWARD_PROBE": "1"}
    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start", extra_env)

    assert exit_code == 0
    # Should not route to child
    output = parse_output(stdout)
    assert resolve_path(output.get("ROUTED_TO")) != resolve_path(child)


# ============================================================================
# VAL-WRAP-013: Symlink handling
# ============================================================================


def test_val_wrap_013_symlink_excluded(wrapper_env):
    """VAL-WRAP-013: Symlinked child is excluded from candidates."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    real_child = parent / "real"
    real_child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=real_child, check=True, capture_output=True)

    link_child = parent / "link"
    link_child.symlink_to(real_child)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    # Should route to real_child, not link
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(real_child)


# ============================================================================
# VAL-WRAP-014: Consent marker passthrough
# ============================================================================


def test_val_wrap_014_consent_marker_in_ownership_toml(wrapper_env):
    """VAL-WRAP-014: Consent marker in ownership.toml allows non-git directory."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    memory_dir = parent / "memory" / "system"
    memory_dir.mkdir(parents=True)

    ownership = memory_dir / "ownership.toml"
    ownership.write_text("[policy]\nallow_non_git = true\n")

    child = parent / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    # Should stay at parent due to consent
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(parent)


def test_val_wrap_014_consent_marker_in_manifest_json(wrapper_env):
    """VAL-WRAP-014: Consent marker in manifest.json."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    memory_dir = parent / "memory" / "system"
    memory_dir.mkdir(parents=True)

    manifest = memory_dir / "manifest.json"
    manifest.write_text(json.dumps({"allow_non_git": True}))

    child = parent / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(parent)


# ============================================================================
# VAL-WRAP-015: Residual tree without consent routes to child
# ============================================================================


def test_val_wrap_015_residual_tree_without_consent_routes_to_child(wrapper_env):
    """VAL-WRAP-015: Residual tree without consent routes to child repo."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    memory_dir = parent / "memory" / "system"
    memory_dir.mkdir(parents=True)
    (memory_dir / "residual.txt").write_text("residual")

    child = parent / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(child)


# ============================================================================
# VAL-WRAP-016: errors.log write discipline
# ============================================================================


def test_val_wrap_016_errors_log_one_line_per_event(wrapper_env):
    """VAL-WRAP-016: errors.log has one line per event."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    run_wrapper(wrapper_env, parent, "session-start")
    run_wrapper(wrapper_env, parent, "session-start")

    lines = wrapper_env["errors_log"].read_text().strip().split("\n")
    assert len(lines) == 2


# ============================================================================
# VAL-WRAP-009: Dangling .git only scenario (0 candidates)
# ============================================================================


def test_val_wrap_009_only_dangling_git_noop(wrapper_env):
    """VAL-WRAP-009: When only dangling .git candidates exist, treat as 0 candidates noop.

    If all child repos have dangling/corrupt .git, rev-parse fails for all,
    resulting in 0 valid candidates → noop + session-start log.
    """
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    # Create two children with dangling .git files
    child1 = parent / "child1"
    child1.mkdir()
    (child1 / ".git").write_text("gitdir: /nonexistent/path1")

    child2 = parent / "child2"
    child2.mkdir()
    (child2 / ".git").write_text("gitdir: /nonexistent/path2")

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    assert stdout.strip() == "{}"

    # Should log to errors.log (session-start only)
    assert wrapper_env["errors_log"].exists()
    content = wrapper_env["errors_log"].read_text()
    assert "session-start" in content


# ============================================================================
# VAL-WRAP-017: Adopt mode doesn't inject AGENTS.md marker
# ============================================================================


def test_val_wrap_017_adopt_mode_no_agents_md_injection(wrapper_env):
    """VAL-WRAP-017: Probe-triggered init uses adopt mode, which doesn't inject AGENTS.md.

    When probe routes to a child repo, init is called with --mode adopt.
    Adopt mode should NOT inject the MEMORY_HOOK_BEGIN/END markers into AGENTS.md.
    """
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    child = parent / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    # Create a business AGENTS.md in child
    agents_md = child / "AGENTS.md"
    original_content = "# Business AGENTS.md\n\nThis is business-specific content.\n"
    agents_md.write_text(original_content)
    original_sha = subprocess.run(
        ["sha256sum", str(agents_md)],
        capture_output=True,
        text=True,
        check=True
    ).stdout.split()[0]

    # Run wrapper to trigger probe routing
    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(child)

    # AGENTS.md should NOT have MEMORY_HOOK_BEGIN/END markers injected
    new_content = agents_md.read_text()
    assert "MEMORY_HOOK_BEGIN" not in new_content
    assert "MEMORY_HOOK_END" not in new_content

    # Content should be unchanged
    new_sha = subprocess.run(
        ["sha256sum", str(agents_md)],
        capture_output=True,
        text=True,
        check=True
    ).stdout.split()[0]
    assert new_sha == original_sha


# ============================================================================
# ≥3 candidates with initialized child priority
# ============================================================================


def test_val_wrap_019_three_candidates_with_initialized_priority(wrapper_env):
    """VAL-WRAP-019: With ≥3 candidates, initialized child still has priority.

    Previous implementation capped at 2 candidates before checking priority.
    Fixed: scan all candidates first, then check priority.
    """
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    # Create three child repos
    alpha = parent / "alpha"
    alpha.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=alpha, check=True, capture_output=True)

    beta = parent / "beta"
    beta.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=beta, check=True, capture_output=True)

    gamma = parent / "gamma"
    gamma.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=gamma, check=True, capture_output=True)

    # Initialize beta (middle one)
    (beta / "memory" / "system").mkdir(parents=True)
    (beta / "memory" / "system" / "initialized").write_text("yes")

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    # Should route to beta (initialized), not alpha or gamma
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(beta)
    # No stderr (not ambiguous when initialized child exists)
    assert stderr == ""


def test_val_wrap_candidate_paths_with_spaces(wrapper_env):
    """Candidate paths with spaces are handled correctly.

    Previous implementation used space-separated candidate lists which broke
    when paths contained spaces. Fixed: use newline separator + IFS=newline.
    """
    parent = wrapper_env["tmpdir"] / "parent with spaces"
    parent.mkdir()

    # Create two child repos with spaces in names
    child1 = parent / "child one"
    child1.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child1, check=True, capture_output=True)

    child2 = parent / "child two"
    child2.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child2, check=True, capture_output=True)

    # Initialize child2
    (child2 / "memory" / "system").mkdir(parents=True)
    (child2 / "memory" / "system" / "initialized").write_text("yes")

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    # Should route to child2 (initialized), even with spaces in path
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(child2)
    # No stderr (not ambiguous when initialized child exists)
    assert stderr == ""


# ============================================================================
# READONLY re-evaluation after probe routing
# ============================================================================


def test_val_wrap_readonly_reevaluation_after_probe(wrapper_env):
    """READONLY re-evaluation: If probe routes to memory-core clone, set READONLY=1.

    Edge case: parent has a child that is a memory-core clone.
    Probe routes to child, then READONLY should be re-evaluated for child.
    """
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    # Create a memory-core clone as child
    child = parent / "memory-core-clone"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    # Add memory-core signature files
    tools_dir = child / "memory_core" / "tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "factory_global_hooks.py").write_text("# marker")

    # Create a gateway stub that outputs READONLY value
    gateway_stub = wrapper_env["tmpdir"] / "gateway-stub-readonly.sh"
    gateway_stub.write_text(
        "#!/bin/sh\n"
        'echo "READONLY=$READONLY"\n'
        'echo "ROUTED_TO=$MEMORY_HOOK_PROJECT_CWD"\n'
    )
    gateway_stub.chmod(0o755)

    # Update wrapper to use new gateway stub
    wrapper_content = render_wrapper(
        storage_root=wrapper_env["storage_root"],
        gateway_command=str(gateway_stub),
        init_command=str(wrapper_env["init_stub"]),
    )
    wrapper_env["wrapper"].write_text(wrapper_content)
    wrapper_env["wrapper"].chmod(0o755)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    # Should route to child
    assert "ROUTED_TO" in stdout
    # READONLY should be set to 1
    assert "READONLY=1" in stdout


# ============================================================================
# VAL-WRAP-018: Init denied by denylist degrades to noop
# ============================================================================


def test_val_wrap_018_denied_by_denylist_degrades_to_noop(wrapper_env):
    """VAL-WRAP-018: Init denied by denylist degrades to noop."""
    # Create a real init script that respects denylist
    init_script = wrapper_env["tmpdir"] / "real-init.sh"
    init_script.write_text(
        "#!/bin/sh\n"
        'TARGET=""\n'
        "while [ $# -gt 0 ]; do\n"
        '  case "$1" in\n'
        '    --target) TARGET="$2"; shift 2 ;;\n'
        "    *) shift ;;\n"
        "  esac\n"
        "done\n"
        "# Simulate denylist rejection for demo-* directories\n"
        'case "$TARGET" in\n'
        "  */demo-*) echo 'Denied by denylist' >&2; exit 1 ;;\n"
        "esac\n"
        "exit 0\n"
    )
    init_script.chmod(0o755)

    # Update wrapper to use real init
    wrapper_content = render_wrapper(
        storage_root=wrapper_env["storage_root"],
        gateway_command=str(wrapper_env["gateway_stub"]),
        init_command=str(init_script),
    )
    wrapper_env["wrapper"].write_text(wrapper_content)
    wrapper_env["wrapper"].chmod(0o755)

    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    demo_child = parent / "demo-test"
    demo_child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=demo_child, check=True, capture_output=True)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    # Should degrade to noop (exit 0) instead of failing
    assert exit_code == 0


# ============================================================================
# VAL-WRAP-019: Initialized child has priority
# ============================================================================


def test_val_wrap_019_initialized_child_has_priority(wrapper_env):
    """VAL-WRAP-019: Initialized child repo has priority."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    alpha = parent / "alpha"
    alpha.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=alpha, check=True, capture_output=True)
    (alpha / "memory" / "system").mkdir(parents=True)
    (alpha / "memory" / "system" / "initialized").write_text("yes")

    beta = parent / "beta"
    beta.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=beta, check=True, capture_output=True)

    exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")

    assert exit_code == 0
    output = parse_output(stdout)
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(alpha)


# ============================================================================
# VAL-WRAP-020: Concurrent probe results are consistent
# ============================================================================


def test_val_wrap_020_concurrent_probe_consistent(wrapper_env):
    """VAL-WRAP-020: Concurrent probe results are consistent."""
    import concurrent.futures

    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    child = parent / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    def probe_once():
        exit_code, stdout, stderr = run_wrapper(wrapper_env, parent, "session-start")
        return parse_output(stdout).get("ROUTED_TO")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(probe_once) for _ in range(8)]
        results = [f.result() for f in futures]

    # All should route to child
    assert all(resolve_path(r) == resolve_path(child) for r in results)


# ============================================================================
# VAL-WRAP-021: Non-existent CWD does not crash
# ============================================================================


def test_val_wrap_021_nonexistent_cwd_no_crash(wrapper_env):
    """VAL-WRAP-021: Non-existent CWD does not crash."""
    fake_cwd = wrapper_env["tmpdir"] / "nonexistent"

    env = os.environ.copy()
    env["PWD"] = str(fake_cwd)

    result = subprocess.run(
        [str(wrapper_env["wrapper"]), "--host", "factory", "--event", "session-start"],
        cwd=wrapper_env["tmpdir"],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0


# ============================================================================
# VAL-WRAP-022: FACTORY_PROJECT_DIR drives routing
# ============================================================================


def test_val_wrap_022_factory_project_dir_drives_routing(wrapper_env):
    """VAL-WRAP-022: FACTORY_PROJECT_DIR drives routing over PWD."""
    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    child = parent / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    other_dir = wrapper_env["tmpdir"] / "other"
    other_dir.mkdir()

    extra_env = {"FACTORY_PROJECT_DIR": str(parent)}
    exit_code, stdout, stderr = run_wrapper(wrapper_env, other_dir, "session-start", extra_env)

    assert exit_code == 0
    output = parse_output(stdout)
    assert resolve_path(output.get("ROUTED_TO")) == resolve_path(child)


# ============================================================================
# VAL-CROSS-002: Self-repo protection
# ============================================================================


def test_val_cross_002_self_repo_not_routed(wrapper_env):
    """VAL-CROSS-002: Self-repo (memory-core) is not routed."""
    repo = wrapper_env["tmpdir"] / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)

    tools_dir = repo / "memory_core" / "tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "factory_global_hooks.py").write_text("# marker")

    exit_code, stdout, stderr = run_wrapper(wrapper_env, repo, "session-start")

    assert exit_code == 0
    # Should detect self-repo and output ROUTED_TO=repo
    output = parse_output(stdout)
    assert "ROUTED_TO" in output


# ============================================================================
# VAL-CROSS-007: Sandbox matrix
# ============================================================================


def test_val_cross_007_sandbox_matrix_six_scenarios(wrapper_env):
    """VAL-CROSS-007: Six layout scenarios in sandbox."""
    scenarios = []

    # Scenario 1: git root
    scenario1 = wrapper_env["tmpdir"] / "git_root"
    scenario1.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=scenario1, check=True, capture_output=True)
    scenarios.append(("git_root", str(scenario1), str(scenario1)))

    # Scenario 2: git subdirectory
    scenario2 = wrapper_env["tmpdir"] / "git_subdir"
    scenario2.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=scenario2, check=True, capture_output=True)
    subdir = scenario2 / "src"
    subdir.mkdir()
    scenarios.append(("git_subdir", str(subdir), str(scenario2)))

    # Scenario 3: non-git with single child
    scenario3 = wrapper_env["tmpdir"] / "non_git_single"
    scenario3.mkdir()
    child = scenario3 / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)
    scenarios.append(("non_git_single", str(scenario3), str(child)))

    # Scenario 4: non-git ambiguous
    scenario4 = wrapper_env["tmpdir"] / "non_git_ambiguous"
    scenario4.mkdir()
    child1 = scenario4 / "child1"
    child1.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child1, check=True, capture_output=True)
    child2 = scenario4 / "child2"
    child2.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child2, check=True, capture_output=True)
    scenarios.append(("non_git_ambiguous", str(scenario4), "{}"))

    # Scenario 5: dataless git
    scenario5 = wrapper_env["tmpdir"] / "dataless_git"
    scenario5.mkdir()
    (scenario5 / ".git").mkdir()
    scenarios.append(("dataless_git", str(scenario5), str(scenario5)))

    # Scenario 6: no candidates
    scenario6 = wrapper_env["tmpdir"] / "no_candidates"
    scenario6.mkdir()
    scenarios.append(("no_candidates", str(scenario6), "{}"))

    for name, cwd, expected in scenarios:
        exit_code, stdout, stderr = run_wrapper(wrapper_env, cwd, "session-start")
        assert exit_code == 0, f"Scenario {name} failed"
        output = parse_output(stdout)
        if expected == "{}":
            assert stdout.strip() == "{}", f"Scenario {name} failed"
        else:
            assert resolve_path(output.get("ROUTED_TO")) == resolve_path(expected), f"Scenario {name} failed"


# ============================================================================
# VAL-CROSS-009: Probe latency bound
# ============================================================================


def test_val_cross_009_probe_latency_under_500ms(wrapper_env):
    """VAL-CROSS-009: Probe latency under 500ms."""
    import time

    parent = wrapper_env["tmpdir"] / "parent"
    parent.mkdir()

    child = parent / "child"
    child.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=child, check=True, capture_output=True)

    start = time.time()
    for _ in range(10):
        run_wrapper(wrapper_env, parent, "session-start")
    elapsed = time.time() - start

    avg_latency_ms = (elapsed / 10) * 1000
    assert avg_latency_ms < 500, f"Average latency {avg_latency_ms:.2f}ms exceeds 500ms"


# ============================================================================
# Template content tests
# ============================================================================


def test_wrapper_template_has_nested_probe():
    """Verify wrapper template contains nested probe implementation."""
    from pathlib import Path

    content = render_wrapper(
        storage_root=Path("/tmp/test-storage"),
        gateway_command="/usr/local/bin/memory-hook-gateway",
        init_command="/usr/local/bin/memory-init",
    )

    assert "NESTED_REPO_PROBE_ENABLED" in content
    assert "NESTED_COUNT" in content
    assert "NESTED_CANDIDATES" in content
    assert "allow_non_git" in content
    assert "MEMORY_HOOK_DISABLE_DOWNWARD_PROBE" in content


def test_wrapper_template_posix_compliant():
    """Verify wrapper template is POSIX-compliant (no bash arrays)."""
    from pathlib import Path

    content = render_wrapper(
        storage_root=Path("/tmp/test-storage"),
        gateway_command="/usr/local/bin/memory-hook-gateway",
        init_command="/usr/local/bin/memory-init",
    )

    # Should not contain bash array syntax
    assert "_args_remaining=(" not in content
    assert "${#" not in content

    # Should contain POSIX-compliant for loop
    assert 'for _arg in "$@"' in content


def test_wrapper_template_anchored_consent_regex():
    """Verify wrapper template uses anchored regex for consent marker."""
    from pathlib import Path

    content = render_wrapper(
        storage_root=Path("/tmp/test-storage"),
        gateway_command="/usr/local/bin/memory-hook-gateway",
        init_command="/usr/local/bin/memory-init",
    )

    # Should use anchored regex
    assert "^[[:space:]]*allow_non_git[[:space:]]*=[[:space:]]*true" in content
