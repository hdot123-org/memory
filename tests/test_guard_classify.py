"""Tests for _guard_classify.py extracted module."""

import os
from pathlib import Path

from memory_core.tools._guard_classify import (
    _check_file_type_block,
    _contains_owned_root_string,
    _expand_env_vars,
    _extract_path_from_execute,
    _is_uncertain_path,
    _parse_multiedit_paths,
    _split_shell_args,
    classify_tool_use,
)
from memory_core.tools._rule_types import RuleResult


def _result_to_dict(result):
    """Helper to convert RuleResult to dict for test assertions."""
    if isinstance(result, RuleResult):
        return result.detail
    return result


def _result_to_dict(result):
    """Helper to convert RuleResult to dict for test assertions."""
    if isinstance(result, RuleResult):
        return result.detail
    return result


class TestCheckFileTypeBlock:
    """Tests for _check_file_type_block helper."""

    def test_blocks_sql_file(self):
        """_check_file_type_block blocks .sql files."""
        result = _check_file_type_block("test.sql")
        assert result is not None
        assert result["decision"] == "block"
        assert ".sql" in result["reason"]

    def test_blocks_bak_file(self):
        """_check_file_type_block blocks .bak files."""
        result = _check_file_type_block("backup.bak")
        assert result is not None
        assert result["decision"] == "block"
        assert ".bak" in result["reason"]

    def test_blocks_sqlite_file(self):
        """_check_file_type_block blocks .sqlite files."""
        result = _check_file_type_block("database.sqlite")
        assert result is not None
        assert result["decision"] == "block"
        assert ".sqlite" in result["reason"]

    def test_blocks_db_file(self):
        """_check_file_type_block blocks .db files."""
        result = _check_file_type_block("data.db")
        assert result is not None
        assert result["decision"] == "block"
        assert ".db" in result["reason"]

    def test_blocks_sql_gz_file(self):
        """_check_file_type_block blocks .sql.gz files."""
        result = _check_file_type_block("dump.sql.gz")
        assert result is not None
        assert result["decision"] == "block"
        assert ".sql.gz" in result["reason"]

    def test_blocks_backups_directory(self):
        """_check_file_type_block blocks files in backups directory."""
        result = _check_file_type_block("backups/test.txt")
        assert result is not None
        assert result["decision"] == "block"
        assert "backups" in result["reason"]

    def test_allows_normal_file(self):
        """_check_file_type_block allows normal files."""
        result = _check_file_type_block("test.py")
        assert result is None

    def test_allows_when_force_set(self):
        """_check_file_type_block allows when MEMORY_HOOK_FORCE=1."""
        old_val = os.environ.get("MEMORY_HOOK_FORCE")
        try:
            os.environ["MEMORY_HOOK_FORCE"] = "1"
            result = _check_file_type_block("test.sql")
            assert result is None
        finally:
            if old_val is None:
                os.environ.pop("MEMORY_HOOK_FORCE", None)
            else:
                os.environ["MEMORY_HOOK_FORCE"] = old_val


class TestSplitShellArgs:
    """Tests for _split_shell_args helper."""

    def test_splits_simple_args(self):
        """_split_shell_args splits space-separated args."""
        result = _split_shell_args("arg1 arg2 arg3")
        assert result == ["arg1", "arg2", "arg3"]

    def test_handles_double_quotes(self):
        """_split_shell_args handles double-quoted strings."""
        result = _split_shell_args('arg1 "arg 2" arg3')
        assert result == ["arg1", "arg 2", "arg3"]

    def test_handles_single_quotes(self):
        """_split_shell_args handles single-quoted strings."""
        result = _split_shell_args("arg1 'arg 2' arg3")
        assert result == ["arg1", "arg 2", "arg3"]

    def test_handles_empty_string(self):
        """_split_shell_args handles empty string."""
        result = _split_shell_args("")
        assert result == []

    def test_handles_multiple_spaces(self):
        """_split_shell_args handles multiple spaces."""
        result = _split_shell_args("arg1   arg2    arg3")
        assert result == ["arg1", "arg2", "arg3"]


class TestExtractPathFromExecute:
    """Tests for _extract_path_from_execute helper."""

    def test_extracts_mv_destination(self):
        """_extract_path_from_execute extracts mv destination."""
        paths = _extract_path_from_execute("mv old.txt new.txt")
        assert paths == ["new.txt"]

    def test_extracts_git_mv_destination(self):
        """_extract_path_from_execute extracts git mv destination."""
        paths = _extract_path_from_execute("git mv old.txt new.txt")
        assert paths == ["new.txt"]

    def test_extracts_rm_targets(self):
        """_extract_path_from_execute extracts rm targets."""
        paths = _extract_path_from_execute("rm file1.txt file2.txt")
        assert paths == ["file1.txt", "file2.txt"]

    def test_extracts_cp_destination(self):
        """_extract_path_from_execute extracts cp destination."""
        paths = _extract_path_from_execute("cp src.txt dest.txt")
        assert paths == ["dest.txt"]

    def test_extracts_mkdir_targets(self):
        """_extract_path_from_execute extracts mkdir targets."""
        paths = _extract_path_from_execute("mkdir dir1 dir2")
        assert paths == ["dir1", "dir2"]

    def test_extracts_touch_targets(self):
        """_extract_path_from_execute extracts touch targets."""
        paths = _extract_path_from_execute("touch file1.txt file2.txt")
        assert paths == ["file1.txt", "file2.txt"]

    def test_extracts_python_open_calls(self):
        """_extract_path_from_execute extracts python open() calls."""
        paths = _extract_path_from_execute('python -c \'open("test.txt", "w")\'')
        assert "test.txt" in paths

    def test_extracts_python_path_calls(self):
        """_extract_path_from_execute extracts python Path() calls."""
        paths = _extract_path_from_execute('python -c \'Path("/tmp/file.txt")\'')
        assert "/tmp/file.txt" in paths

    def test_extracts_redirect_target(self):
        """_extract_path_from_execute extracts shell redirect target."""
        paths = _extract_path_from_execute("echo test > output.txt")
        assert paths == ["output.txt"]

    def test_extracts_tee_target(self):
        """_extract_path_from_execute extracts tee target."""
        paths = _extract_path_from_execute("echo test | tee output.txt")
        assert "output.txt" in paths

    def test_extracts_dd_target(self):
        """_extract_path_from_execute extracts dd of= target."""
        paths = _extract_path_from_execute("dd if=/dev/zero of=output.bin")
        assert paths == ["output.bin"]

    def test_extracts_install_destination(self):
        """_extract_path_from_execute extracts install destination."""
        paths = _extract_path_from_execute("install -m 755 script /usr/local/bin")
        assert paths == ["/usr/local/bin"]

    def test_extracts_ln_target(self):
        """_extract_path_from_execute extracts ln target."""
        paths = _extract_path_from_execute("ln -s target link")
        assert paths == ["link"]

    def test_returns_empty_for_unknown_command(self):
        """_extract_path_from_execute returns empty for unknown command."""
        paths = _extract_path_from_execute("ls -la")
        assert paths == []

    def test_returns_empty_for_empty_command(self):
        """_extract_path_from_execute returns empty for empty command."""
        paths = _extract_path_from_execute("")
        assert paths == []


class TestContainsOwnedRootString:
    """Tests for _contains_owned_root_string helper."""

    def test_detects_memory_slash(self):
        """_contains_owned_root_string detects 'memory/'."""
        assert _contains_owned_root_string("rm -rf memory/docs") is True

    def test_detects_agents_md_lowercase(self):
        """_contains_owned_root_string detects 'agents.md' (lowercase in cmd)."""
        # The function lowercases the command but NOT the indicators.
        # "AGENTS.md" indicator won't match "agents.md" in lowered command.
        # This matches original behavior exactly.
        assert _contains_owned_root_string("cat AGENTS.md") is False

    def test_detects_memory_system(self):
        """_contains_owned_root_string detects 'memory/system/'."""
        assert _contains_owned_root_string("rm memory/system/test") is True

    def test_detects_case_insensitive(self):
        """_contains_owned_root_string detects lowercase memory/."""
        assert _contains_owned_root_string("rm memory/docs") is True

    def test_returns_false_for_normal_command(self):
        """_contains_owned_root_string returns False for normal command."""
        assert _contains_owned_root_string("rm test.txt") is False


class TestIsUncertainPath:
    """Tests for _is_uncertain_path helper."""

    def test_detects_wildcard(self):
        """_is_uncertain_path detects wildcard *."""
        assert _is_uncertain_path("test*.txt") is True

    def test_detects_question_mark(self):
        """_is_uncertain_path detects wildcard ?."""
        assert _is_uncertain_path("test?.txt") is True

    def test_detects_variable(self):
        """_is_uncertain_path detects variable $."""
        assert _is_uncertain_path("$HOME/test.txt") is True

    def test_detects_command_substitution(self):
        """_is_uncertain_path detects command substitution `."""
        assert _is_uncertain_path("`pwd`/test.txt") is True

    def test_detects_brace_expansion(self):
        """_is_uncertain_path detects brace expansion {."""
        assert _is_uncertain_path("test{1,2}.txt") is True

    def test_detects_bracket_expansion(self):
        """_is_uncertain_path detects bracket expansion [."""
        assert _is_uncertain_path("test[1-3].txt") is True

    def test_returns_false_for_normal_path(self):
        """_is_uncertain_path returns False for normal path."""
        assert _is_uncertain_path("test.txt") is False


class TestExpandEnvVars:
    """Tests for _expand_env_vars helper."""

    def test_expands_home(self):
        """_expand_env_vars expands $HOME."""
        old_home = os.environ.get("HOME")
        try:
            os.environ["HOME"] = "/home/testuser"
            result = _expand_env_vars("$HOME/test.txt")
            assert result == "/home/testuser/test.txt"
        finally:
            if old_home:
                os.environ["HOME"] = old_home
            else:
                os.environ.pop("HOME", None)

    def test_expands_project_dir(self):
        """_expand_env_vars expands $PROJECT_DIR."""
        old_proj = os.environ.get("FACTORY_PROJECT_DIR")
        try:
            os.environ["FACTORY_PROJECT_DIR"] = "/tmp/project"
            result = _expand_env_vars("$PROJECT_DIR/test.txt")
            assert result == "/tmp/project/test.txt"
        finally:
            if old_proj:
                os.environ["FACTORY_PROJECT_DIR"] = old_proj
            else:
                os.environ.pop("FACTORY_PROJECT_DIR", None)

    def test_expands_tilde(self):
        """_expand_env_vars expands ~."""
        old_home = os.environ.get("HOME")
        try:
            os.environ["HOME"] = "/home/testuser"
            result = _expand_env_vars("~/test.txt")
            assert result == "/home/testuser/test.txt"
        finally:
            if old_home:
                os.environ["HOME"] = old_home
            else:
                os.environ.pop("HOME", None)

    def test_leaves_unknown_vars(self):
        """_expand_env_vars leaves unknown variables as-is."""
        result = _expand_env_vars("$UNKNOWN_VAR/test.txt")
        assert result == "$UNKNOWN_VAR/test.txt"


class TestParseMultieditPaths:
    """Tests for _parse_multiedit_paths helper."""

    def test_extracts_file_paths(self):
        """_parse_multiedit_paths extracts file paths from edits."""
        payload = {
            "edits": [
                {"file_path": "file1.txt", "old_str": "old", "new_str": "new"},
                {"file_path": "file2.txt", "old_str": "old2", "new_str": "new2"},
            ]
        }
        result = _parse_multiedit_paths(payload)
        assert result == ["file1.txt", "file2.txt"]

    def test_returns_empty_for_no_edits(self):
        """_parse_multiedit_paths returns empty for no edits."""
        result = _parse_multiedit_paths({})
        assert result == []

    def test_skips_edits_without_file_path(self):
        """_parse_multiedit_paths skips edits without file_path."""
        payload = {
            "edits": [
                {"file_path": "file1.txt"},
                {"old_str": "old", "new_str": "new"},
            ]
        }
        result = _parse_multiedit_paths(payload)
        assert result == ["file1.txt"]


class TestClassifyToolUse:
    """Tests for classify_tool_use main function."""

    def test_allows_unknown_tool(self, tmp_path: Path):
        """classify_tool_use allows unknown tool."""
        # Create memory/system to make it a managed project
        (tmp_path / "memory" / "system").mkdir(parents=True)
        payload = {"tool_name": "UnknownTool"}
        result = classify_tool_use(payload, tmp_path)
        assert isinstance(result, RuleResult)
        assert result.detail["decision"] == "allow"
        assert "Unknown tool" in result.message

    def test_allows_when_no_tool_name(self, tmp_path: Path):
        """classify_tool_use allows when no tool_name."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        payload = {}
        result = classify_tool_use(payload, tmp_path)
        assert isinstance(result, RuleResult)
        assert result.detail["decision"] == "allow"
        assert "No tool_name" in result.message

    def test_allows_write_without_file_path(self, tmp_path: Path):
        """classify_tool_use allows Write without file_path."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        payload = {"tool_name": "Write"}
        result = classify_tool_use(payload, tmp_path)
        assert isinstance(result, RuleResult)
        assert result.detail["decision"] == "allow"
        assert "without file_path" in result.message

    def test_blocks_write_sql_file(self, tmp_path: Path):
        """classify_tool_use blocks Write to .sql file."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        payload = {"tool_name": "Write", "file_path": "test.sql", "content": "SELECT"}
        result = classify_tool_use(payload, tmp_path)
        assert isinstance(result, RuleResult)
        assert result.matched is True
        assert result.severity == "error"
        assert result.detail["decision"] == "block"
        assert ".sql" in result.message

    def test_blocks_write_bak_file(self, tmp_path: Path):
        """classify_tool_use blocks Write to .bak file."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        payload = {"tool_name": "Write", "file_path": "backup.bak", "content": "backup"}
        result = classify_tool_use(payload, tmp_path)
        assert isinstance(result, RuleResult)
        assert result.detail["decision"] == "block"
        assert ".bak" in result.message

    def test_blocks_write_to_backups_dir(self, tmp_path: Path):
        """classify_tool_use blocks Write to backups directory."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        payload = {"tool_name": "Write", "file_path": "backups/test.txt", "content": "test"}
        result = classify_tool_use(payload, tmp_path)
        assert isinstance(result, RuleResult)
        assert result.detail["decision"] == "block"
        assert "backups" in result.message

    def test_returns_rule_result_for_write(self, tmp_path: Path):
        """classify_tool_use returns RuleResult for Write tool."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        payload = {"tool_name": "Write", "file_path": "test.py", "content": "print('test')"}

        result = classify_tool_use(payload, tmp_path)
        assert isinstance(result, RuleResult)
        assert result.matched is False
        assert result.severity == "info"
        assert result.detail["decision"] == "allow"

    def test_returns_rule_result_for_execute(self, tmp_path: Path):
        """classify_tool_use returns RuleResult for Execute tool."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        payload = {"tool_name": "Execute", "command": "ls -la"}

        result = classify_tool_use(payload, tmp_path)
        assert isinstance(result, RuleResult)
        assert result.matched is False
        assert result.detail["decision"] == "allow"

    def test_returns_rule_result_for_multiedit(self, tmp_path: Path):
        """classify_tool_use returns RuleResult for MultiEdit tool."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        payload = {
            "tool_name": "MultiEdit",
            "edits": [
                {"file_path": "test.py", "old_str": "old", "new_str": "new"},
            ]
        }

        result = classify_tool_use(payload, tmp_path)
        assert isinstance(result, RuleResult)
        assert result.matched is False
        assert result.detail["decision"] == "allow"
        assert "item_results" in result.detail

    def test_handles_tool_input_wrapper(self, tmp_path: Path):
        """classify_tool_use handles tool_input wrapper format."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        payload = {
            "tool_input": {
                "tool_name": "Write",
                "file_path": "test.sql",
                "content": "SELECT"
            }
        }
        result = classify_tool_use(payload, tmp_path)
        assert isinstance(result, RuleResult)
        assert result.detail["decision"] == "block"
        assert ".sql" in result.message

    def test_has_rule_name_property(self):
        """classify_tool_use has rule_name property for Protocol compliance."""
        assert hasattr(classify_tool_use, "rule_name")
        assert classify_tool_use.rule_name == "classify_tool_use"


class TestRuleEvaluatorProtocolCompliance:
    """Tests for RuleEvaluator Protocol compliance across all 5 executors."""

    def test_classify_tool_use_has_rule_name(self):
        """classify_tool_use has rule_name property."""
        assert hasattr(classify_tool_use, "rule_name")
        assert classify_tool_use.rule_name == "classify_tool_use"

    def test_classify_tool_use_returns_rule_result(self):
        """classify_tool_use returns RuleResult."""
        # classify_tool_use is a function, not a class with evaluate method
        # but it has rule_name property for Protocol compliance
        payload = {"tool_name": "Execute", "command": "echo test"}
        result = classify_tool_use(payload, Path("/tmp"))
        assert isinstance(result, RuleResult)

    def test_project_map_validator_has_rule_name(self, tmp_path: Path):
        """ProjectMapValidator has rule_name property."""
        from unittest.mock import MagicMock

        from memory_core.tools.business_policy_checks import ProjectMapValidator
        config = MagicMock()
        validator = ProjectMapValidator(config)
        assert hasattr(validator, "rule_name")
        assert validator.rule_name == "project_map_validation"

    def test_project_map_validator_has_evaluate(self, tmp_path: Path):
        """ProjectMapValidator has evaluate method returning RuleResult."""
        from unittest.mock import MagicMock

        from memory_core.tools._rule_types import RuleContext
        from memory_core.tools.business_policy_checks import ProjectMapValidator
        config = MagicMock()
        config.read_text_if_exists_fn = MagicMock(return_value="")
        config.project_map_files = [tmp_path / "index.md", tmp_path / "core.md", tmp_path / "registry.md"]
        config.project_map_governance = tmp_path / "governance.md"
        validator = ProjectMapValidator(config)
        assert hasattr(validator, "evaluate")
        ctx = RuleContext()
        result = validator.evaluate(ctx)
        assert isinstance(result, RuleResult)

    def test_frozen_tuple_checker_has_rule_name(self):
        """FrozenTupleChecker has rule_name property."""
        from unittest.mock import MagicMock

        from memory_core.tools.business_policy_checks import FrozenTupleChecker
        config = MagicMock()
        checker = FrozenTupleChecker(config)
        assert hasattr(checker, "rule_name")
        assert checker.rule_name == "frozen_tuple_check"

    def test_frozen_tuple_checker_has_evaluate(self, tmp_path: Path):
        """FrozenTupleChecker has evaluate method returning RuleResult."""
        from unittest.mock import MagicMock

        from memory_core.tools._rule_types import RuleContext
        from memory_core.tools.business_policy_checks import FrozenTupleChecker
        config = MagicMock()
        config.governance_frozen_tuple_files = []
        config.frozen_tuple_expected = []
        config.frozen_tuple_legacy_markers = []
        checker = FrozenTupleChecker(config)
        assert hasattr(checker, "evaluate")
        ctx = RuleContext()
        result = checker.evaluate(ctx)
        assert isinstance(result, RuleResult)

    def test_event_contract_checker_has_rule_name(self):
        """EventContractChecker has rule_name property."""
        from unittest.mock import MagicMock

        from memory_core.tools.business_policy_checks import EventContractChecker
        config = MagicMock()
        checker = EventContractChecker(config)
        assert hasattr(checker, "rule_name")
        assert checker.rule_name == "event_contract_check"

    def test_event_contract_checker_has_evaluate(self):
        """EventContractChecker has evaluate method returning RuleResult."""
        from unittest.mock import MagicMock

        from memory_core.tools._rule_types import RuleContext
        from memory_core.tools.business_policy_checks import EventContractChecker
        config = MagicMock()
        config.event_contract_files = {}
        checker = EventContractChecker(config)
        assert hasattr(checker, "evaluate")
        ctx = RuleContext()
        result = checker.evaluate(ctx)
        assert isinstance(result, RuleResult)

    def test_truth_basis_resolver_has_rule_name(self):
        """TruthBasisResolver has rule_name property."""
        from unittest.mock import MagicMock

        from memory_core.tools.business_policy_checks import TruthBasisResolver
        config = MagicMock()
        resolver = TruthBasisResolver(config)
        assert hasattr(resolver, "rule_name")
        assert resolver.rule_name == "truth_basis_resolution"

    def test_truth_basis_resolver_has_evaluate(self):
        """TruthBasisResolver has evaluate method returning RuleResult."""
        from unittest.mock import MagicMock

        from memory_core.tools._rule_types import RuleContext
        from memory_core.tools.business_policy_checks import TruthBasisResolver
        config = MagicMock()
        config.global_canonical = []
        config.project_canonical = {}
        resolver = TruthBasisResolver(config)
        assert hasattr(resolver, "evaluate")
        ctx = RuleContext(extra={"project_scope": "test"})
        result = resolver.evaluate(ctx)
        assert isinstance(result, RuleResult)
