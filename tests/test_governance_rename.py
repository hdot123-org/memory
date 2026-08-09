"""Tests for governance workflow rename detection patterns.

Validates that the protected path patterns in evolution-governance.yml
correctly detect files that are renamed into or out of protected paths.
"""
import re

import pytest

# These patterns are extracted from .github/workflows/evolution-governance.yml
# They must match the grep patterns used in the governance check
PROTECTED_PATTERNS = [
    re.compile(r'^\.evolution/'),
    re.compile(r'^scripts/evolution_.*\.py$'),
    re.compile(r'^\.github/workflows/evolution-.*\.yml$'),
    re.compile(r'^\.github/CODEOWNERS$'),
]


def is_protected(filepath: str) -> bool:
    """Check if a file path matches any protected path pattern."""
    return any(p.search(filepath) for p in PROTECTED_PATTERNS)


def detect_rename_violation(changed_files: list[dict]) -> bool:
    """Simulate the governance check for renamed files.

    Args:
        changed_files: List of dicts with 'filename' and optional 'previous_filename'
                       (matching GitHub PR files API format)

    Returns:
        True if any protected path is touched (including via rename)
    """
    for f in changed_files:
        if is_protected(f.get('filename', '')):
            return True
        prev = f.get('previous_filename')
        if prev and is_protected(prev):
            return True
    return False


class TestProtectedPathPatterns:
    """Validate that protected path patterns match expected paths."""

    @pytest.mark.parametrize("path", [
        ".evolution/config.yml",
        ".evolution/findings_over_time.json",
        ".evolution/DISABLED",
        ".evolution/subdir/nested.yml",
        "scripts/evolution_scanner.py",
        "scripts/evolution_utils.py",
        "scripts/evolution_adapters.py",
        ".github/workflows/evolution-scan.yml",
        ".github/workflows/evolution-governance.yml",
        ".github/CODEOWNERS",
    ])
    def test_protected_paths_detected(self, path):
        assert is_protected(path), f"Should be protected: {path}"

    @pytest.mark.parametrize("path", [
        "docs/README.md",
        "memory_core/tools/hook.py",
        "scripts/other_script.py",
        ".github/workflows/ci.yml",
        ".github/ISSUE_TEMPLATE.md",
        "evolution/config.yml",  # Missing leading dot - NOT protected
        "scripts/evolution.txt",  # Wrong extension
    ])
    def test_non_protected_paths_not_detected(self, path):
        assert not is_protected(path), f"Should NOT be protected: {path}"


class TestRenameDetection:
    """Validate that renamed files are correctly detected."""

    def test_rename_from_protected_detected(self):
        """Renaming a protected file to a non-protected path is caught via previous_filename."""
        files = [{"filename": "docs/config.yml", "previous_filename": ".evolution/config.yml"}]
        assert detect_rename_violation(files) is True

    def test_rename_to_protected_detected(self):
        """Renaming a non-protected file to a protected path is caught via filename."""
        files = [{"filename": ".evolution/config.yml", "previous_filename": "docs/config.yml"}]
        assert detect_rename_violation(files) is True

    def test_rename_within_protected_detected(self):
        """Renaming within protected paths is caught by both filename and previous_filename."""
        files = [{"filename": "scripts/evolution_v2.py", "previous_filename": "scripts/evolution_scanner.py"}]
        assert detect_rename_violation(files) is True

    def test_rename_of_codeowners_detected(self):
        """Renaming CODEOWNERS is caught."""
        files = [{"filename": ".github/REVIEWERS", "previous_filename": ".github/CODEOWNERS"}]
        assert detect_rename_violation(files) is True

    def test_rename_of_workflow_detected(self):
        """Renaming evolution workflow file is caught."""
        files = [{"filename": ".github/workflows/ci.yml", "previous_filename": ".github/workflows/evolution-scan.yml"}]
        assert detect_rename_violation(files) is True

    def test_non_protected_rename_not_detected(self):
        """Renaming non-protected files does not trigger governance check."""
        files = [{"filename": "docs/new.md", "previous_filename": "docs/old.md"}]
        assert detect_rename_violation(files) is False

    def test_mixed_changes_only_protected_detected(self):
        """In a PR with mixed changes, only protected renames trigger."""
        files = [
            {"filename": "docs/readme.md"},  # Not protected, not renamed
            {"filename": "README.md", "previous_filename": "docs/readme.md"},  # Not protected
            {"filename": ".github/workflows/deploy.yml", "previous_filename": ".github/workflows/evolution-scan.yml"},  # PROTECTED rename!
        ]
        assert detect_rename_violation(files) is True

    def test_codeowners_rename_stripped_extension(self):
        """Renaming CODEOWNERS to .bak bypasses filename but caught by previous_filename."""
        files = [{"filename": ".github/CODEOWNERS.bak", "previous_filename": ".github/CODEOWNERS"}]
        assert detect_rename_violation(files) is True


class TestGovernanceWorkflowConsistency:
    """Validate that test patterns match actual workflow patterns."""

    def test_patterns_match_workflow(self):
        """Ensure PROTECTED_PATTERNS match the patterns in evolution-governance.yml."""
        from pathlib import Path
        workflow = Path(__file__).parent.parent / ".github" / "workflows" / "evolution-governance.yml"
        content = workflow.read_text()

        # The workflow must still check these patterns
        assert '.evolution/' in content, "Workflow must check .evolution/ paths"
        assert 'scripts/evolution_.*\\.py' in content, "Workflow must check evolution scripts"
        assert 'evolution-.*\\.yml' in content, "Workflow must check evolution workflows"
        assert 'CODEOWNERS' in content, "Workflow must check CODEOWNERS"
        # Must track renames
        assert 'previous_filename' in content, "Workflow must track file renames"
