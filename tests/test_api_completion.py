"""Tests for schema conversion, PathUtils, extended PolicyRegistry, and package entry."""

from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Schema conversion tests
# ---------------------------------------------------------------------------

class TestSchemaConversion:
    """Tests for convert_to_v1, is_v1, is_v2 in memory_hook_schema."""

    def test_convert_v2_to_v1_changes_schema_version(self):
        """wb-hook-v2 -> context-package-v1."""
        from memory_core.tools.memory_hook_schema import convert_to_v1

        v2_pkg = {"schema_version": "wb-hook-v2", "host": "codex", "event": "post-gen"}
        v1 = convert_to_v1(v2_pkg)
        assert v1["schema_version"] == "context-package-v1"

    def test_convert_nests_paths(self):
        """repo_root / workspace_root / cwd go into 'paths' dict."""
        from memory_core.tools.memory_hook_schema import convert_to_v1

        v2_pkg = {
            "schema_version": "wb-hook-v2",
            "repo_root": "/repo",
            "workspace_root": "/ws",
            "cwd": "/ws/project",
        }
        v1 = convert_to_v1(v2_pkg)
        assert v1["paths"] == {
            "repo_root": "/repo",
            "workspace_root": "/ws",
            "cwd": "/ws/project",
        }

    def test_convert_renames_context_sections(self):
        """project_context -> project, task_context -> task."""
        from memory_core.tools.memory_hook_schema import convert_to_v1

        v2_pkg = {
            "schema_version": "wb-hook-v2",
            "project_context": {"name": "mem", "lang": "py"},
            "task_context": {"desc": "add tests"},
        }
        v1 = convert_to_v1(v2_pkg)
        assert v1["project"] == {"name": "mem", "lang": "py"}
        assert v1["task"] == {"desc": "add tests"}
        assert "project_context" not in v1
        assert "task_context" not in v1

    def test_convert_drops_system_context(self):
        """system_context key is not in v1 output."""
        from memory_core.tools.memory_hook_schema import convert_to_v1

        v2_pkg = {
            "schema_version": "wb-hook-v2",
            "system_context": {"python": "3.10", "os": "Darwin"},
        }
        v1 = convert_to_v1(v2_pkg)
        assert "system_context" not in v1

    def test_convert_drops_missing_paths(self):
        """missing_paths key is not in v1 output."""
        from memory_core.tools.memory_hook_schema import convert_to_v1

        v2_pkg = {
            "schema_version": "wb-hook-v2",
            "missing_paths": ["/no/such/file"],
        }
        v1 = convert_to_v1(v2_pkg)
        assert "missing_paths" not in v1

    def test_is_v1_is_v2_helpers(self):
        """Version detection helpers work correctly."""
        from memory_core.tools.memory_hook_schema import is_v1, is_v2

        v1_pkg: dict[str, Any] = {"schema_version": "context-package-v1"}
        v2_pkg: dict[str, Any] = {"schema_version": "wb-hook-v2"}
        unknown: dict[str, Any] = {"schema_version": "wb-hook-v3"}
        empty: dict[str, Any] = {}

        assert is_v1(v1_pkg) is True
        assert is_v1(v2_pkg) is False
        assert is_v1(unknown) is False
        assert is_v1(empty) is False

        assert is_v2(v2_pkg) is True
        assert is_v2(v1_pkg) is False
        assert is_v2(unknown) is False
        assert is_v2(empty) is False


# ---------------------------------------------------------------------------
# PathUtils tests
# ---------------------------------------------------------------------------

class TestPathUtils:
    """Tests for PathUtilsImpl."""

    def test_extract_excerpt_reads_file(self, tmp_path: Path):
        """Create a temp file, read excerpt returns stripped non-empty lines."""
        from memory_core.tools.memory_hook_impls import PathUtilsImpl

        f = tmp_path / "sample.txt"
        f.write_text("line1\n\n  line2  \nline3\nline4\n", encoding="utf-8")
        utils = PathUtilsImpl(tmp_path)
        excerpt = utils.extract_excerpt(f, max_lines=3)
        assert excerpt == ["line1", "line2", "line3"]

    def test_extract_excerpt_handles_missing_file(self, tmp_path: Path):
        """Returns [] for non-existent file."""
        from memory_core.tools.memory_hook_impls import PathUtilsImpl

        utils = PathUtilsImpl(tmp_path)
        missing = tmp_path / "does_not_exist.txt"
        assert utils.extract_excerpt(missing) == []

    def test_write_targets_returns_dict(self):
        """Returns a dict with expected keys."""
        from memory_core.tools.memory_hook_impls import PathUtilsImpl

        ws = Path("/tmp/ws_test")
        utils = PathUtilsImpl(ws)
        targets = utils.write_targets()
        assert isinstance(targets, dict)
        assert "fact" in targets
        assert "global_canonical" in targets
        assert "kb_policy" in targets
        assert targets["kb_policy"]["mode"] == "read-first-CRUD"

    def test_interface_matches_abc(self):
        """PathUtilsImpl is instance of PathUtils ABC."""
        from memory_core.tools.memory_hook_impls import PathUtilsImpl
        from memory_core.tools.memory_hook_interfaces import PathUtils

        ws = Path("/tmp/ws_test")
        utils = PathUtilsImpl(ws)
        assert isinstance(utils, PathUtils)


# ---------------------------------------------------------------------------
# Package API tests
# ---------------------------------------------------------------------------

class TestPackageAPI:
    """Tests for memory_core.tools lazy exports."""

    def test_lazy_import_build_context_package(self):
        """from memory_core.tools import build_context_package works."""
        from memory_core.tools import build_context_package
        assert callable(build_context_package)

    def test_lazy_import_core_config(self):
        """from memory_core.tools import CoreConfig works."""
        from memory_core.tools import CoreConfig
        assert isinstance(CoreConfig, type)

    def test_lazy_import_build_simple(self):
        """from memory_core.tools import build_context_package_simple works."""
        from memory_core.tools import build_context_package_simple
        assert callable(build_context_package_simple)

    def test_lazy_import_unknown_raises(self):
        """from memory_core.tools import nonexistent raises AttributeError."""
        import memory_core.tools
        with pytest.raises(AttributeError):
            _ = memory_core.tools.nonexistent_symbol_xyz


# ---------------------------------------------------------------------------
# Extended PolicyRegistry tests
# ---------------------------------------------------------------------------

class TestExtendedPolicyRegistry:
    """Tests for PolicyRegistryImpl extended stub methods."""

    def _make_registry(self) -> Any:
        from memory_core.tools.memory_hook_impls import PolicyRegistryImpl
        return PolicyRegistryImpl()

    def test_validate_project_map_returns_list(self):
        """Stub returns []."""
        reg = self._make_registry()
        result = reg.validate_project_map()
        assert isinstance(result, list)
        assert result == []

    def test_truth_basis_for_scope_returns_dict(self):
        """Stub returns {}."""
        reg = self._make_registry()
        result = reg.truth_basis_for_scope("test-scope")
        assert isinstance(result, dict)
        assert result == {}

    def test_all_new_methods_have_stubs(self):
        """All 9 new methods return neutral defaults."""
        reg = self._make_registry()
        # Methods that should return []
        list_methods = [
            "validate_project_map",
            "validate_unique_legal_system_contract",
            "governance_frozen_tuple_errors",
            "event_contract_blocker_errors",
            "decision_refs_for_scope",
            "lesson_refs_for_scope",
            "docs_refs_for_scope",
        ]
        for method_name in list_methods:
            method = getattr(reg, method_name)
            if "for_scope" in method_name:
                result = method("scope")
            else:
                result = method()
            assert isinstance(result, list), f"{method_name} should return list"

        # Methods that should return {}
        dict_methods = [
            ("git_registration_probe", ("event", {})),
            ("truth_basis_for_scope", ("scope",)),
        ]
        for method_name, args in dict_methods:
            method = getattr(reg, method_name)
            result = method(*args)
            assert isinstance(result, dict), f"{method_name} should return dict"

    def test_git_registration_probe_returns_dict(self):
        """git_registration_probe stub returns."""
        reg = self._make_registry()
        result = reg.git_registration_probe("pre-gen", {"cwd": "/ws"})
        assert isinstance(result, dict)
        assert result == {}

    def test_scope_ref_methods_return_lists(self):
        """decision/lesson/docs refs all return []."""
        reg = self._make_registry()
        for method_name in (
            "decision_refs_for_scope",
            "lesson_refs_for_scope",
            "docs_refs_for_scope",
        ):
            method = getattr(reg, method_name)
            result = method("any-scope")
            assert result == []
            assert isinstance(result, list)

    def test_governance_errors_returns_list(self):
        """governance_frozen_tuple_errors and event_contract_blocker_errors return lists."""
        reg = self._make_registry()
        result1 = reg.governance_frozen_tuple_errors()
        result2 = reg.event_contract_blocker_errors()
        assert isinstance(result1, list)
        assert isinstance(result2, list)
        assert result1 == []
        assert result2 == []
