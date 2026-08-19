"""Tests for scripts/auto_merge_triage.sh (auto-merge blind-spot triage).

Three blind-spot forms (scrutiny r1/r2 + 编排器增补 2026-08-19):
1. CONFLICTING: PR silently skipped, no notification (#794 停滞 11h+)
2. BEHIND + all green: needs update-branch self-heal (#814/#819/#825/#827/#828)
3. Early-fire + no re-trigger: schedule sweep should catch BEHIND PRs

Contract:
- Input: gh pr list --json number,mergeable,mergeStateStatus,statusCheckRollup JSON
- Output: JSON triage result with classified PRs + actions
- Exit 0 always (triage never fails the workflow)
- No side effects (pure classification + command generation)
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def get_script_path() -> Path:
    """Get path to auto_merge_triage.sh script."""
    return Path(__file__).parent.parent / "scripts" / "auto_merge_triage.sh"


class TestAutoMergeTriage:
    """Triage classification tests."""

    def test_script_exists_and_executable(self):
        """Script exists and is executable."""
        script = get_script_path()
        assert script.exists(), f"{script} not found"
        assert os.access(script, os.X_OK), f"{script} not executable"

    def test_empty_input_returns_empty(self):
        """Empty PR list → empty triage result."""
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input="[]",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output == {"mergeable": [], "behind": [], "conflicting": [], "unknown": []}

    def test_mergeable_pr_classified(self):
        """PR with mergeable=MERGEABLE → mergeable list."""
        prs = [{"number": 123, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["mergeable"]) == 1
        assert output["mergeable"][0]["number"] == 123
        assert output["behind"] == []
        assert output["conflicting"] == []

    def test_behind_pr_classified(self):
        """PR with mergeStateStatus=BEHIND → behind list."""
        prs = [{"number": 456, "mergeable": "MERGEABLE", "mergeStateStatus": "BEHIND"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["behind"]) == 1
        assert output["behind"][0]["number"] == 456
        assert output["mergeable"] == []

    def test_conflicting_pr_classified(self):
        """PR with mergeable=CONFLICTING → conflicting list."""
        prs = [{"number": 789, "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["conflicting"]) == 1
        assert output["conflicting"][0]["number"] == 789
        assert output["mergeable"] == []
        assert output["behind"] == []

    def test_unknown_state_classified(self):
        """PR with mergeable=UNKNOWN → unknown list."""
        prs = [{"number": 101, "mergeable": "UNKNOWN", "mergeStateStatus": "UNKNOWN"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["unknown"]) == 1
        assert output["unknown"][0]["number"] == 101

    def test_mixed_prs_classified(self):
        """Mixed PRs → correct classification into all categories."""
        prs = [
            {"number": 1, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"},
            {"number": 2, "mergeable": "MERGEABLE", "mergeStateStatus": "BEHIND"},
            {"number": 3, "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY"},
            {"number": 4, "mergeable": "UNKNOWN", "mergeStateStatus": "UNKNOWN"},
        ]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert [p["number"] for p in output["mergeable"]] == [1]
        assert [p["number"] for p in output["behind"]] == [2]
        assert [p["number"] for p in output["conflicting"]] == [3]
        assert [p["number"] for p in output["unknown"]] == [4]

    def test_invalid_json_exits_zero(self):
        """Invalid JSON input → exit 0 with empty result (triage never fails workflow)."""
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input="not json",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output == {"mergeable": [], "behind": [], "conflicting": [], "unknown": []}


class TestAutoMergeTriageActions:
    """Action generation tests."""

    def test_behind_pr_generates_update_branch_command(self):
        """BEHIND PR → generates update-branch command."""
        prs = [{"number": 456, "mergeable": "MERGEABLE", "mergeStateStatus": "BEHIND"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["behind"]) == 1
        pr = output["behind"][0]
        assert "action" in pr
        assert pr["action"] == "update-branch"

    def test_conflicting_pr_generates_notify_command(self):
        """CONFLICTING PR → generates notify action."""
        prs = [{"number": 789, "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["conflicting"]) == 1
        pr = output["conflicting"][0]
        assert "action" in pr
        assert pr["action"] == "notify"

    def test_mergeable_pr_has_no_action(self):
        """MERGEABLE PR → no special action (workflow proceeds to merge)."""
        prs = [{"number": 123, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["mergeable"]) == 1
        pr = output["mergeable"][0]
        # mergeable PRs don't need special actions
        assert pr.get("action") is None or pr.get("action") == "merge"


class TestAutoMergeTriageWorkflow:
    """Workflow integration tests (YAML structure)."""

    def test_auto_merge_yaml_has_triage_step(self):
        """auto-merge.yml includes triage step in schedule path."""
        import yaml

        workflow_path = Path(__file__).parent.parent / ".github/workflows/auto-merge.yml"
        data = yaml.safe_load(workflow_path.read_text())

        # Find the auto-merge job
        assert "jobs" in data
        assert "auto-merge" in data["jobs"]

        # Check for triage-related steps or comments
        steps = data["jobs"]["auto-merge"].get("steps", [])
        step_names = [s.get("name", "") for s in steps]

        # At least one step should mention triage, conflicting, or behind
        has_triage = any(
            "triage" in name.lower() or "conflict" in name.lower() or "behind" in name.lower()
            for name in step_names
        )
        # Or the workflow uses the triage script
        uses_triage = any(
            "auto_merge_triage" in str(s) for s in steps
        )

        assert has_triage or uses_triage, (
            f"auto-merge.yml lacks triage logic. Steps: {step_names}"
        )

    def test_auto_merge_yaml_schedule_not_just_resolve(self):
        """Schedule path does more than just resolve (has triage/self-heal)."""
        import yaml

        workflow_path = Path(__file__).parent.parent / ".github/workflows/auto-merge.yml"
        data = yaml.safe_load(workflow_path.read_text())

        # The workflow should have logic beyond just resolve → merge
        # Either a triage job or triage steps in auto-merge job
        jobs = data.get("jobs", {})

        # Check if there's a dedicated triage job
        has_triage_job = any("triage" in job_name.lower() for job_name in jobs.keys())

        # Or check if auto-merge job has triage steps
        auto_merge_steps = jobs.get("auto-merge", {}).get("steps", [])
        has_triage_steps = any(
            "triage" in str(s).lower() or "auto_merge_triage" in str(s)
            for s in auto_merge_steps
        )

        assert has_triage_job or has_triage_steps, (
            "auto-merge.yml schedule path lacks triage/self-heal logic"
        )
