"""Test for release workflow tag extraction logic.

This module tests the tag extraction logic for both push tag and workflow_dispatch
trigger methods, mirroring the bash logic in .github/workflows/release-and-dispatch.yml
"""


import re
from pathlib import Path

import pytest


class TestReleaseTagExtraction:
    """Test suite for release workflow tag extraction logic."""

    # Regex pattern for valid semver tag (matching the workflow logic)
    SEMVER_TAG_PATTERN = re.compile(r'^v[0-9]+\.[0-9]+\.[0-9]+.*$')

    def _extract_tag(self, event_name: str, ref: str, ref_name: str, input_tag: str | None) -> str:
        """Simulate the workflow tag extraction logic.

        Mirrors the bash logic:
        - workflow_dispatch: use inputs.release_tag
        - push with refs/tags/v*: use github.ref_name
        - other: fail
        """
        if event_name == "workflow_dispatch":
            if not input_tag:
                raise ValueError("release_tag input is required for manual workflow dispatch")
            if not self.SEMVER_TAG_PATTERN.match(input_tag):
                raise ValueError(f"release_tag must be a valid semver tag (e.g., v1.2.3), got: {input_tag}")
            return input_tag
        elif ref.startswith("refs/tags/v"):
            return ref_name
        else:
            raise ValueError("release must be triggered by a version tag or workflow_dispatch with release_tag")

    # ==================== workflow_dispatch tests ====================

    def test_manual_trigger_valid_tag(self):
        """Test manual trigger with valid semver tag."""
        result = self._extract_tag(
            event_name="workflow_dispatch",
            ref="refs/heads/main",
            ref_name="main",
            input_tag="v1.2.3"
        )
        assert result == "v1.2.3"

    def test_manual_trigger_valid_tag_with_prerelease(self):
        """Test manual trigger with valid semver tag including prerelease."""
        result = self._extract_tag(
            event_name="workflow_dispatch",
            ref="refs/heads/main",
            ref_name="main",
            input_tag="v1.2.3-beta.1"
        )
        assert result == "v1.2.3-beta.1"

    def test_manual_trigger_valid_tag_with_build(self):
        """Test manual trigger with valid semver tag including build metadata."""
        result = self._extract_tag(
            event_name="workflow_dispatch",
            ref="refs/heads/main",
            ref_name="main",
            input_tag="v1.2.3+build.123"
        )
        assert result == "v1.2.3+build.123"

    def test_manual_trigger_missing_tag(self):
        """Test manual trigger with missing input_tag fails."""
        with pytest.raises(ValueError, match="release_tag input is required"):
            self._extract_tag(
                event_name="workflow_dispatch",
                ref="refs/heads/main",
                ref_name="main",
                input_tag=""
            )

    def test_manual_trigger_none_tag(self):
        """Test manual trigger with None input_tag fails."""
        with pytest.raises(ValueError, match="release_tag input is required"):
            self._extract_tag(
                event_name="workflow_dispatch",
                ref="refs/heads/main",
                ref_name="main",
                input_tag=None
            )

    def test_manual_trigger_invalid_tag_no_v_prefix(self):
        """Test manual trigger with tag missing 'v' prefix fails."""
        with pytest.raises(ValueError, match="release_tag must be a valid semver tag"):
            self._extract_tag(
                event_name="workflow_dispatch",
                ref="refs/heads/main",
                ref_name="main",
                input_tag="1.2.3"
            )

    def test_manual_trigger_invalid_tag_missing_patch(self):
        """Test manual trigger with tag missing patch version fails."""
        with pytest.raises(ValueError, match="release_tag must be a valid semver tag"):
            self._extract_tag(
                event_name="workflow_dispatch",
                ref="refs/heads/main",
                ref_name="main",
                input_tag="v1.2"
            )

    def test_manual_trigger_invalid_tag_non_numeric(self):
        """Test manual trigger with non-numeric version fails."""
        with pytest.raises(ValueError, match="release_tag must be a valid semver tag"):
            self._extract_tag(
                event_name="workflow_dispatch",
                ref="refs/heads/main",
                ref_name="main",
                input_tag="vabc.def.ghi"
            )

    # ==================== push tag tests ====================

    def test_push_tag_trigger_valid(self):
        """Test push tag trigger with valid tag."""
        result = self._extract_tag(
            event_name="push",
            ref="refs/tags/v0.2.0",
            ref_name="v0.2.0",
            input_tag=""
        )
        assert result == "v0.2.0"

    def test_push_tag_trigger_different_versions(self):
        """Test push tag trigger with various version formats."""
        test_cases = [
            ("refs/tags/v0.1.0", "v0.1.0"),
            ("refs/tags/v1.0.0", "v1.0.0"),
            ("refs/tags/v10.20.30", "v10.20.30"),
            ("refs/tags/v1.2.3-alpha", "v1.2.3-alpha"),
        ]
        for ref, expected in test_cases:
            result = self._extract_tag(
                event_name="push",
                ref=ref,
                ref_name=expected,
                input_tag=""
            )
            assert result == expected

    # ==================== invalid trigger tests ====================

    def test_push_branch_trigger_fails(self):
        """Test push to branch (not tag) fails."""
        with pytest.raises(ValueError, match="release must be triggered by a version tag"):
            self._extract_tag(
                event_name="push",
                ref="refs/heads/main",
                ref_name="main",
                input_tag=""
            )

    def test_push_non_version_tag_fails(self):
        """Test push with non-version tag fails."""
        with pytest.raises(ValueError, match="release must be triggered by a version tag"):
            self._extract_tag(
                event_name="push",
                ref="refs/tags/some-feature",
                ref_name="some-feature",
                input_tag=""
            )

    def test_push_tag_without_v_prefix_fails(self):
        """Test push with tag missing 'v' prefix fails (ref check requires v*)."""
        with pytest.raises(ValueError, match="release must be triggered by a version tag"):
            self._extract_tag(
                event_name="push",
                ref="refs/tags/1.2.3",  # No 'v' prefix, so ref doesn't match refs/tags/v*
                ref_name="1.2.3",
                input_tag=""
            )

    def test_other_event_fails(self):
        """Test other event types fail."""
        with pytest.raises(ValueError, match="release must be triggered by a version tag"):
            self._extract_tag(
                event_name="pull_request",
                ref="refs/pull/123/head",
                ref_name="123/merge",
                input_tag=""
            )


class TestPyprojectVersionConsistency:
    """Test suite for pyproject.toml version consistency with tag."""

    @pytest.fixture
    def pyproject_version(self) -> str:
        """Read version from pyproject.toml."""
        import tomllib
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        with pyproject_path.open("rb") as f:
            config = tomllib.load(f)
        return config["project"]["version"]

    def test_current_pyproject_version_matches_expected(self, pyproject_version: str):
        """Verify current pyproject.toml version is as expected."""
        # This test documents the current version
        assert pyproject_version == "0.9.0"

    def test_tag_matches_pyproject_version(self, pyproject_version: str):
        """Simulate the workflow version verification logic.

        Mirrors:
        TAG_VER="${{ steps.version.outputs.tag }}"
        PY_VER="v$(python -c 'import tomllib; f=open("pyproject.toml","rb"); print(tomllib.load(f)["project"]["version"])')"
        if [ "$TAG_VER" != "$PY_VER" ]; then
            echo "Tag $TAG_VER does not match pyproject.toml version $PY_VER"
            exit 1
        fi
        """
        tag = "v0.9.0"  # Simulated extracted tag
        py_ver = f"v{pyproject_version}"
        assert tag == py_ver, f"Tag {tag} does not match pyproject.toml version {py_ver}"

    def test_tag_mismatch_fails(self, pyproject_version: str):
        """Test that version mismatch raises error."""
        tag = "v1.0.0"  # Different version
        py_ver = f"v{pyproject_version}"
        assert tag != py_ver


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
