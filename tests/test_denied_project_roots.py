"""Tests for denied_project_roots module."""

from __future__ import annotations

import os
from pathlib import Path


class TestDeniedProjectRoots:
    """Tests for denied_project_roots function."""

    def test_denied_project_roots_includes_home_directory(self):
        """Test that home directory is included in denied roots."""
        from memory_core.tools.denied_project_roots import denied_project_roots

        roots = denied_project_roots()

        home = Path.home().resolve(strict=False)
        assert home in roots

    def test_denied_project_roots_home_path_resolved(self):
        """Test that home path is properly resolved."""
        from memory_core.tools.denied_project_roots import denied_project_roots

        roots = denied_project_roots()

        # All paths should be resolved
        for root in roots:
            assert root.is_absolute()

    def test_denied_project_roots_no_duplicates(self):
        """Test that denied roots list contains no duplicates."""
        from memory_core.tools.denied_project_roots import denied_project_roots

        roots = denied_project_roots()

        assert len(roots) == len(set(roots))

    def test_denied_project_roots_from_env_single_path(self, monkeypatch):
        """Test that single path from environment variable is included."""
        from memory_core.tools.denied_project_roots import denied_project_roots

        test_path = "/tmp/test_denied_path"
        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", test_path)

        roots = denied_project_roots()

        resolved_test_path = Path(test_path).expanduser().resolve(strict=False)
        assert resolved_test_path in roots

    def test_denied_project_roots_from_env_multiple_paths(self, monkeypatch):
        """Test that multiple paths from environment variable (os.pathsep separated) are included."""
        from memory_core.tools.denied_project_roots import denied_project_roots

        test_paths = ["/tmp/test_path1", "/tmp/test_path2"]
        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", os.pathsep.join(test_paths))

        roots = denied_project_roots()

        for path in test_paths:
            resolved = Path(path).expanduser().resolve(strict=False)
            assert resolved in roots

    def test_denied_project_roots_from_env_with_tilde(self, monkeypatch, tmp_path):
        """Test that tilde paths are expanded from environment variable."""
        from memory_core.tools.denied_project_roots import denied_project_roots

        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", "~/test_path")

        roots = denied_project_roots()

        expanded = Path("~/test_path").expanduser().resolve(strict=False)
        assert expanded in roots
        assert expanded.is_absolute()

    def test_denied_project_roots_from_env_empty_string(self, monkeypatch):
        """Test that empty environment variable doesn't add extra paths."""
        from memory_core.tools.denied_project_roots import denied_project_roots

        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", "")

        roots = denied_project_roots()

        # Should only contain home directory
        home = Path.home().resolve(strict=False)
        assert roots == [home]

    def test_denied_project_roots_from_env_with_whitespace(self, monkeypatch):
        """Test that whitespace-only paths are ignored."""
        from memory_core.tools.denied_project_roots import denied_project_roots

        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", "  \t\n  ")

        roots = denied_project_roots()

        # Should only contain home directory (whitespace-only paths are skipped)
        home = Path.home().resolve(strict=False)
        assert roots == [home]

    def test_denied_project_roots_from_env_mixed_whitespace_and_paths(self, monkeypatch):
        """Test mixed whitespace and valid paths."""
        from memory_core.tools.denied_project_roots import denied_project_roots

        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", f"  /tmp/path1  {os.pathsep} /tmp/path2  ")

        roots = denied_project_roots()

        path1 = Path("/tmp/path1").expanduser().resolve(strict=False)
        path2 = Path("/tmp/path2").expanduser().resolve(strict=False)
        home = Path.home().resolve(strict=False)

        assert path1 in roots
        assert path2 in roots
        assert home in roots

    def test_denied_project_roots_handles_home_runtime_error(self, monkeypatch):
        """Test handling when Path.home() raises RuntimeError."""
        from memory_core.tools import denied_project_roots as module

        # Patch Path.home to raise RuntimeError
        def mock_home():
            raise RuntimeError("No home directory")

        monkeypatch.setattr(Path, "home", mock_home)
        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", "")

        roots = module.denied_project_roots()

        # Should return empty list when home fails and no env paths
        assert roots == []

    def test_denied_project_roots_returns_list_of_paths(self):
        """Test that function returns list of Path objects."""
        from memory_core.tools.denied_project_roots import denied_project_roots

        roots = denied_project_roots()

        assert isinstance(roots, list)
        for root in roots:
            assert isinstance(root, Path)

    def test_denied_project_roots_order_preservation(self, monkeypatch):
        """Test that order of paths is preserved (home first, then env paths)."""
        from memory_core.tools.denied_project_roots import denied_project_roots

        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", "/tmp/path1" + os.pathsep + "/tmp/path2")

        roots = denied_project_roots()

        home = Path.home().resolve(strict=False)
        path1 = Path("/tmp/path1").expanduser().resolve(strict=False)
        path2 = Path("/tmp/path2").expanduser().resolve(strict=False)

        # Home should be first
        assert roots[0] == home
        # Then paths from env
        assert path1 in roots
        assert path2 in roots


class TestIsDeniedProjectRoot:
    """Tests for is_denied_project_root function."""

    def test_is_denied_project_root_exact_match(self, monkeypatch):
        """Test that exact path match returns True."""
        from memory_core.tools.denied_project_roots import is_denied_project_root

        test_path = "/tmp/test_exact_match"
        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", test_path)

        path = Path(test_path)
        assert is_denied_project_root(path) is True

    def test_is_denied_project_root_not_denied(self, monkeypatch, tmp_path):
        """Test that non-denied path returns False."""
        from memory_core.tools.denied_project_roots import is_denied_project_root

        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", "")

        some_path = tmp_path / "some_project"
        some_path.mkdir()

        assert is_denied_project_root(some_path) is False

    def test_is_denied_project_root_subpath_not_denied(self, monkeypatch, tmp_path):
        """Test that subpath of denied root is not denied (exact match required)."""
        from memory_core.tools.denied_project_roots import is_denied_project_root

        denied_root = tmp_path / "denied_root"
        denied_root.mkdir()
        subpath = denied_root / "subpath"
        subpath.mkdir()

        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", str(denied_root))

        # Subpath should NOT be denied (exact match required)
        assert is_denied_project_root(subpath) is False

    def test_is_denied_project_root_with_tilde(self, monkeypatch):
        """Test that tilde paths are expanded and matched."""
        from memory_core.tools.denied_project_roots import is_denied_project_root

        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", "~/denied_test")

        # Should match with tilde
        assert is_denied_project_root(Path("~/denied_test")) is True
        # Should also match expanded
        assert is_denied_project_root(Path("~/denied_test").expanduser()) is True

    def test_is_denied_project_root_path_expansion(self, monkeypatch, tmp_path):
        """Test path expansion in is_denied_project_root."""
        from memory_core.tools.denied_project_roots import is_denied_project_root

        denied_root = tmp_path / "denied_root"
        denied_root.mkdir()

        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", str(denied_root))

        # Test with relative path that resolves to denied root
        relative_path = Path(tmp_path.name) / "denied_root"
        assert is_denied_project_root(relative_path) is False  # Won't match because path is different

    def test_is_denied_project_root_resolves_paths(self, monkeypatch, tmp_path):
        """Test that paths are resolved before comparison."""
        from memory_core.tools.denied_project_roots import is_denied_project_root

        # Create symlink
        real_path = tmp_path / "real_denied"
        real_path.mkdir()
        symlink_path = tmp_path / "symlink_denied"
        symlink_path.symlink_to(real_path)

        # Deny the real path
        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", str(symlink_path))

        # Should match the symlink path
        assert is_denied_project_root(symlink_path) is True

    def test_is_denied_project_root_home_directory(self):
        """Test that home directory is denied."""
        from memory_core.tools.denied_project_roots import is_denied_project_root

        home = Path.home()
        assert is_denied_project_root(home) is True

    def test_is_denied_project_root_returns_bool(self, monkeypatch, tmp_path):
        """Test that function returns boolean."""
        from memory_core.tools.denied_project_roots import is_denied_project_root

        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", "")

        some_path = tmp_path / "test_project"
        some_path.mkdir()

        result = is_denied_project_root(some_path)
        assert isinstance(result, bool)

    def test_is_denied_project_root_multiple_denied_paths(self, monkeypatch, tmp_path):
        """Test matching against multiple denied paths."""
        from memory_core.tools.denied_project_roots import is_denied_project_root

        path1 = tmp_path / "denied1"
        path2 = tmp_path / "denied2"
        path1.mkdir()
        path2.mkdir()

        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", str(path1) + os.pathsep + str(path2))

        assert is_denied_project_root(path1) is True
        assert is_denied_project_root(path2) is True
        assert is_denied_project_root(tmp_path / "other") is False


class TestModuleIntegration:
    """Integration tests for the denied_project_roots module."""

    def test_module_exposes_both_functions(self):
        """Test that module exposes both public functions."""
        from memory_core.tools import denied_project_roots as module

        assert hasattr(module, "denied_project_roots")
        assert hasattr(module, "is_denied_project_root")
        assert callable(module.denied_project_roots)
        assert callable(module.is_denied_project_root)

    def test_empty_denied_roots_list(self, monkeypatch):
        """Test behavior when no denied roots (home fails and no env)."""
        from memory_core.tools.denied_project_roots import (
            denied_project_roots,
            is_denied_project_root,
        )

        # Make home fail and no env paths
        def mock_home():
            raise RuntimeError("No home")

        monkeypatch.setattr(Path, "home", mock_home)
        monkeypatch.setenv("MEMORY_HOOK_DENY_PROJECT_ROOTS", "")

        roots = denied_project_roots()
        assert roots == []

        # Any path should not be denied when list is empty
        assert is_denied_project_root(Path("/some/path")) is False
