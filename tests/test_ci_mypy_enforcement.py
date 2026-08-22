"""CI mypy enforcement tests (M4-F1).

Validates that:
1. memory_core mypy job has no continue-on-error and no || true in command
2. The job id is in ci-ok.needs (hard gate via branch protection)
3. docs/code-quality-metrics.md threshold matches ruff.toml actual value
4. README has no 'memory_core/ 为 advisory' residual text

These tests prevent regression to advisory-only typing checks.
"""

import re
import tomllib
from pathlib import Path

import yaml


def _load_ci_config() -> dict:
    """Load .github/workflows/ci.yml."""
    ci_path = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"
    with ci_path.open() as f:
        return yaml.safe_load(f)


def _load_ruff_config() -> dict:
    """Load ruff.toml configuration."""
    ruff_path = Path(__file__).parent.parent / "ruff.toml"
    with ruff_path.open("rb") as f:
        return tomllib.load(f)


def test_mypy_memory_core_job_no_continue_on_error():
    """M4-F1-1: memory_core mypy job must not have continue-on-error."""
    ci = _load_ci_config()
    jobs = ci.get("jobs", {})

    # Find the memory_core mypy job (by name pattern)
    memory_core_job = None
    for _job_id, job_config in jobs.items():
        job_name = job_config.get("name", "")
        if "memory_core" in job_name.lower() and "mypy" in job_name.lower():
            memory_core_job = job_config
            break

    assert memory_core_job is not None, "memory_core mypy job not found"
    assert not memory_core_job.get("continue-on-error"), "memory_core mypy job must not have continue-on-error: true"


def test_mypy_memory_core_command_no_suppress_errors():
    """M4-F1-2: memory_core mypy command must not suppress errors with || true."""
    ci = _load_ci_config()
    jobs = ci.get("jobs", {})

    # Find the memory_core mypy job
    memory_core_job = None
    for _job_id, job_config in jobs.items():
        job_name = job_config.get("name", "")
        if "memory_core" in job_name.lower() and "mypy" in job_name.lower():
            memory_core_job = job_config
            break

    assert memory_core_job is not None, "memory_core mypy job not found"

    # Check all steps in the job
    steps = memory_core_job.get("steps", [])
    for step in steps:
        run_cmd = step.get("run", "")
        # Check for || true pattern (error suppression)
        assert "|| true" not in run_cmd, (
            f"memory_core mypy step contains '|| true' which suppresses errors: {run_cmd[:100]}"
        )
        # Also check for continue-on-error at step level
        assert not step.get("continue-on-error"), "memory_core mypy step must not have continue-on-error: true"


def test_mypy_memory_core_in_ci_ok_needs():
    """M4-F1-3: memory_core mypy job must be in ci-ok.needs for hard gate enforcement."""
    ci = _load_ci_config()
    jobs = ci.get("jobs", {})

    # Find the memory_core mypy job id
    memory_core_job_id = None
    for job_id, job_config in jobs.items():
        job_name = job_config.get("name", "")
        if "memory_core" in job_name.lower() and "mypy" in job_name.lower():
            memory_core_job_id = job_id
            break

    assert memory_core_job_id is not None, "memory_core mypy job not found"

    # Check ci-ok job exists and has needs
    ci_ok_job = jobs.get("ci-ok")
    assert ci_ok_job is not None, "ci-ok job not found"

    needs = ci_ok_job.get("needs", [])
    assert memory_core_job_id in needs, (
        f"memory_core mypy job ({memory_core_job_id}) must be in ci-ok.needs for hard gate enforcement. "
        f"Current needs: {needs}"
    )


def test_docs_threshold_matches_ruff_config():
    """M4-F1-4: docs/code-quality-metrics.md threshold must match ruff.toml actual value."""
    # Read ruff.toml to get actual threshold
    ruff_config = _load_ruff_config()
    actual_threshold = ruff_config.get("lint", {}).get("mccabe", {}).get("max-complexity")

    assert actual_threshold is not None, "ruff.toml missing lint.mccabe.max-complexity"

    # Read docs/code-quality-metrics.md
    docs_path = Path(__file__).parent.parent / "docs" / "code-quality-metrics.md"
    with docs_path.open() as f:
        docs_content = f.read()

    # Check that the documented threshold matches ruff.toml
    # Look for patterns like "max-complexity = N" (with or without backticks)
    threshold_pattern = rf"`max-complexity\s*=\s*{actual_threshold}`|max-complexity\s*=\s*{actual_threshold}"
    assert re.search(threshold_pattern, docs_content), (
        f"docs/code-quality-metrics.md must document max-complexity = {actual_threshold} "
        f"(matching ruff.toml). Current content does not match."
    )


def test_readme_no_advisory_residual():
    """M4-F1-5: README must not contain 'memory_core/ 为 advisory' text."""
    readme_path = Path(__file__).parent.parent / "README.md"
    with readme_path.open() as f:
        readme_content = f.read()

    # Check for the specific advisory text that should be removed
    advisory_pattern = r"memory_core/\s*为\s*advisory"
    matches = re.findall(advisory_pattern, readme_content)

    assert len(matches) == 0, (
        f"README.md still contains '{matches[0]}' text. This should be updated to reflect hard gate enforcement."
    )


def test_readme_mypy_section_accuracy():
    """M4-F1-6: README mypy section should accurately reflect hard gate status."""
    readme_path = Path(__file__).parent.parent / "README.md"
    with readme_path.open() as f:
        readme_content = f.read()

    # Check that README mentions mypy enforcement for both domains
    # Should mention scripts/ and memory_core/ as hard gates
    assert "mypy" in readme_content.lower(), "README should mention mypy"

    # Look for evidence of hard gate documentation
    # This could be in various forms: "hard gate", "enforced", "mandatory", etc.
    gate_indicators = ["hard gate", "enforced", "mandatory", "required", "fail", "block"]
    has_gate_language = any(indicator in readme_content.lower() for indicator in gate_indicators)

    # Also check that it mentions both scripts/ and memory_core/
    has_scripts = "scripts/" in readme_content
    has_memory_core = "memory_core/" in readme_content

    assert has_scripts and has_memory_core, "README should mention both scripts/ and memory_core/ for mypy checking"

    # At least one indication of enforcement (not just "run mypy")
    assert has_gate_language, "README should use language indicating hard gate enforcement, not just advisory"


def test_enforced_pipeline_steps_have_pipefail():
    """M4-F1b: Enforced job pipeline steps must have pipefail semantics.

    GHA default shell for `run` is `bash -e` which does NOT set pipefail.
    A pipeline like `cmd | tee file` will always exit 0 (tee's exit code)
    even if `cmd` fails, silently swallowing the error. This test ensures
    every step with a pipe operator in an enforced job (listed in ci-ok.needs)
    has proper pipefail handling via one of:
      - shell: bash (which GHA expands to `bash -eo pipefail`)
      - `set -o pipefail` in the run command
      - PIPESTATUS handling at end of run command
    """
    ci = _load_ci_config()
    jobs = ci.get("jobs", {})

    # Jobs aggregated into ci-ok are the enforced (hard gate) jobs
    ci_ok_job = jobs.get("ci-ok")
    assert ci_ok_job is not None, "ci-ok job not found"
    enforced_job_ids = set(ci_ok_job.get("needs", []))
    assert enforced_job_ids, "ci-ok.needs is empty"

    violations = []
    for job_id in enforced_job_ids:
        job = jobs.get(job_id)
        if not job:
            continue
        for step in job.get("steps", []) or []:
            run_cmd = step.get("run", "") or ""
            # Only check steps that actually contain a pipe operator (| but not ||).
            # Use regex to find | that is not preceded/followed by another |
            if not re.search(r"(?<!\|)\|(?!\|)", run_cmd):
                continue

            has_pipefail_semantics = False

            # Check 1: shell: bash (GHA expands to bash -eo pipefail)
            if step.get("shell") == "bash":
                has_pipefail_semantics = True

            # Check 2: set -o pipefail in the run command
            if "set -o pipefail" in run_cmd or "set -eo pipefail" in run_cmd:
                has_pipefail_semantics = True

            # Check 3: PIPESTATUS handling at end of command
            if "PIPESTATUS" in run_cmd:
                has_pipefail_semantics = True

            if not has_pipefail_semantics:
                violations.append(
                    f"Job '{job_id}', step '{step.get('name', '(unnamed)')}': "
                    f"pipeline step without pipefail semantics. "
                    f"Add 'shell: bash' to the step, or 'set -o pipefail' / PIPESTATUS in the run command."
                )

    assert not violations, (
        "Enforced jobs have pipeline steps without pipefail semantics. "
        "Without pipefail, a failed command piped to 'tee' etc. is silently swallowed "
        "because bash -e (GHA default) does not propagate non-zero exit through pipes. "
        "Violations:\n" + "\n".join(f"  - {v}" for v in violations)
    )
