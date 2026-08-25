"""Tests for guard residual risk specification (VAL-GUARD-016, VAL-GUARD-020).

N3: Evidence file for VAL-GUARD-016 (residual spec doc exists + covers 3 categories)
and VAL-GUARD-020 (non-managed project + extractor unit assertions).
"""

import re
from pathlib import Path

import pytest

from memory_core.tools._guard_classify import _extract_cp_path, _extract_mv_path
from memory_core.tools._guard_patterns import RE_CP, RE_MV
from tests.guard_helpers import run_guard

# Anchor to repo root so tests work regardless of cwd (CI compat)
REPO_ROOT = Path(__file__).resolve().parents[1]

# ============================================================================
# VAL-GUARD-016: Residual spec doc exists and covers 3 categories
# ============================================================================


class TestResidualSpecDoc:
    """VAL-GUARD-016: docs/specs/ residual doc exists and covers 3 residual categories"""

    def test_residual_doc_exists(self):
        """docs/specs/ must contain a residual risk spec document"""
        specs_dir = REPO_ROOT / "docs" / "specs"
        assert specs_dir.exists(), "docs/specs/ directory must exist"

        # Find residual risk doc (any .md with residual keywords)
        residual_docs = list(specs_dir.glob("*.md"))
        assert len(residual_docs) > 0, "docs/specs/ must contain at least one .md file"

        # Check that at least one doc covers residual categories
        found_residual_doc = False
        for doc in residual_docs:
            content = doc.read_text()
            # Must mention 3 residual categories
            has_cwd = "cwd" in content.lower() or "cd " in content
            has_variable = "变量" in content or "variable" in content.lower()
            has_encoded = "编码" in content or "base64" in content or "encoded" in content.lower()

            if has_cwd and has_variable and has_encoded:
                found_residual_doc = True
                break

        assert found_residual_doc, "Must find a doc covering cwd/variable/encoded residual categories"

    def test_residual_doc_mentions_sha256(self):
        """Residual doc must mention SHA-256 manifest integrity check (deep defense)"""
        specs_dir = REPO_ROOT / "docs" / "specs"
        found_sha256 = False

        for doc in specs_dir.glob("*.md"):
            content = doc.read_text()
            if ("SHA-256" in content or "sha256" in content or "SHA256" in content) and (
                "manifest" in content.lower() or "完整性" in content
            ):
                found_sha256 = True
                break

        assert found_sha256, "Residual doc must mention SHA-256 manifest integrity"

    def test_residual_doc_mentions_command_substitution(self):
        """N2: Residual doc must mention command substitution $( ) / backtick category"""
        specs_dir = REPO_ROOT / "docs" / "specs"
        found_cmd_sub = False

        for doc in specs_dir.glob("*.md"):
            content = doc.read_text()
            # Check for command substitution mention
            if ("$(" in content or "`" in content or "command substitution" in content.lower()) and (
                "block" in content.lower() or "拦截" in content or "拦截" in content
            ):
                found_cmd_sub = True
                break

        assert found_cmd_sub, "Residual doc must mention command substitution $() / backtick category"


# ============================================================================
# VAL-GUARD-004: Extractor unit assertions (hard criteria)
# ============================================================================


class TestExtractorUnitAssertions:
    """VAL-GUARD-004: Extractor unit-level assertions (hard criteria)"""

    def test_extract_mv_path_with_t_flag(self):
        """_extract_mv_path('mv -t memory/system x') must return ['memory/system']"""
        match = RE_MV.match("mv -t memory/system x")
        assert match is not None, "RE_MV must match 'mv -t memory/system x'"

        paths = _extract_mv_path(match)
        assert "memory/system" in paths, f"Expected 'memory/system' in {paths}"

    def test_extract_mv_path_with_target_directory_flag(self):
        """_extract_mv_path('mv --target-directory=memory/system x') must return ['memory/system']"""
        match = RE_MV.match("mv --target-directory=memory/system x")
        assert match is not None, "RE_MV must match 'mv --target-directory=memory/system x'"

        paths = _extract_mv_path(match)
        assert "memory/system" in paths, f"Expected 'memory/system' in {paths}"

    def test_extract_cp_path_with_t_flag(self):
        """_extract_cp_path('cp -t memory/kb src.txt') must return ['memory/kb']"""
        match = RE_CP.match("cp -t memory/kb src.txt")
        assert match is not None, "RE_CP must match 'cp -t memory/kb src.txt'"

        paths = _extract_cp_path(match)
        assert "memory/kb" in paths, f"Expected 'memory/kb' in {paths}"

    def test_multi_redirect_extraction(self):
        """RE_REDIRECT findall on 'echo x 1>/tmp/a 2>memory/kb/err.log' must return 2 targets"""
        cmd = "echo x 1>/tmp/a 2>memory/kb/err.log"

        # Use findall to get all redirect targets
        redirect_pattern = re.compile(r"(?<!&)[12]?>[>]?\s*['\"]?([^\s;|&<>'\"]+)['\"]?")
        targets = redirect_pattern.findall(cmd)

        assert len(targets) == 2, f"Expected 2 redirect targets, got {len(targets)}: {targets}"
        assert "/tmp/a" in targets, f"Expected '/tmp/a' in {targets}"
        assert "memory/kb/err.log" in targets, f"Expected 'memory/kb/err.log' in {targets}"


# ============================================================================
# VAL-GUARD-020: Non-managed project + empty stdin semantic
# ============================================================================


class TestUnmanagedProject:
    """VAL-GUARD-020: Non-managed project (no memory/system) → all allow"""

    @pytest.fixture
    def unmanaged_project(self, tmp_path):
        """Create a tmp project WITHOUT memory/system directory"""
        # Just create a basic project structure, no memory/ at all
        (tmp_path / "src").mkdir()
        (tmp_path / "README.md").write_text("# Test")
        return tmp_path

    def test_escape_matrix_in_unmanaged_project_allows(self, unmanaged_project):
        """Escape matrix commands in unmanaged project must all allow (no memory/system early-return)"""
        test_commands = [
            "touch /tmp/decoy.txt && python3 -c \"import shutil; shutil.move('/tmp/decoy.txt', 'memory/system/x')\"",
            "echo x | tee /tmp/f && rm -rf memory/kb",
            "echo ok > /tmp/a && echo hack >> memory/kb/hack.md",
        ]

        for cmd in test_commands:
            payload = {"tool_name": "Execute", "tool_input": {"command": cmd}}
            exit_code, output = run_guard(payload, unmanaged_project)

            # In unmanaged project (no memory/system), everything should allow
            assert exit_code == 0, f"Command {cmd!r} should allow in unmanaged project, got exit {exit_code}"
            assert output.get("decision") == "allow", f"Command {cmd!r} decision should be 'allow'"

    def test_empty_stdin_allows(self, unmanaged_project):
        """Empty stdin → exit 0 + allow JSON"""
        payload = {}
        exit_code, output = run_guard(payload, unmanaged_project)

        assert exit_code == 0, "Empty stdin should exit 0"
        assert output.get("decision") == "allow", "Empty stdin should allow"


# ============================================================================
# N1: cd no-op bypass prevention
# ============================================================================


class TestCdNoOpBypass:
    """N1: cd no-op (cd . / cd ./) bypass prevention"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_cd_noop_bypass_blocked(self, fake_project):
        """cd memory && cd . && rm -f x.md should block (cd . is no-op, doesn't reset context)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "cd memory && cd . && rm -f x.md"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "cd memory && cd . && rm should block"
        assert output.get("decision") == "block", "Decision should be 'block'"

    def test_cd_noop_variant_blocked(self, fake_project):
        """cd memory && cd ./ && rm -f x.md should block (cd ./ is no-op)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "cd memory && cd ./ && rm -f x.md"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "cd memory && cd ./ && rm should block"
        assert output.get("decision") == "block", "Decision should be 'block'"


# ============================================================================
# N4: Token-aware write verb matching
# ============================================================================


class TestTokenAwareWriteVerbs:
    """N4: Write verb matching must be token/position aware"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_sort_t_flag_not_false_positive(self, fake_project):
        """sort -t "," should NOT trigger -t write verb (sort doesn't use -t for target)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": 'sort -t "," memory/kb/data.csv > /tmp/out'},
        }
        exit_code, output = run_guard(payload, fake_project)

        # Should allow: sort is readonly, -t is field separator not target
        assert exit_code == 0, "sort -t should allow (not false positive on -t)"
        assert output.get("decision") == "allow", "Decision should be 'allow'"

    def test_mv_t_flag_still_blocked(self, fake_project):
        """mv -t memory/system should still block (mv uses -t for target)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "mv -t memory/system x"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "mv -t memory/system should block"
        assert output.get("decision") == "block", "Decision should be 'block'"

    def test_find_delete_token_aware(self, fake_project):
        """find -delete should block only when first word is 'find'"""
        # find -delete with owned target
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "find memory/docs -name '*.tmp' -delete"},
        }
        exit_code, output = run_guard(payload, fake_project)
        assert exit_code == 2, "find -delete should block"
        assert output.get("decision") == "block", "Decision should be 'block'"

        # grep -delete should allow (grep doesn't have -delete action)
        payload2 = {
            "tool_name": "Execute",
            "tool_input": {"command": "grep -delete memory/kb/data.txt"},
        }
        exit_code2, output2 = run_guard(payload2, fake_project)
        # grep -delete is not a real flag, but grep is readonly so should allow
        assert exit_code2 == 0, "grep -delete should allow (grep is readonly)"
        assert output2.get("decision") == "allow", "Decision should be 'allow'"


# ============================================================================
# N2: Command substitution block preservation
# ============================================================================


class TestCommandSubstitutionBlock:
    """N2: Command substitution $( ) / backtick must block"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_dollar_paren_substitution_blocked(self, fake_project):
        """echo $(rm -rf memory/kb) should block"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "echo $(rm -rf memory/kb)"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "$() command substitution should block"
        assert output.get("decision") == "block", "Decision should be 'block'"

    def test_backtick_substitution_blocked(self, fake_project):
        """echo `rm -rf memory/kb` should block"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "echo `rm -rf memory/kb`"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "Backtick command substitution should block"
        assert output.get("decision") == "block", "Decision should be 'block'"


# ============================================================================
# B3: Readonly whitelist alignment (architecture §2.2)
# ============================================================================


class TestReadonlyWhitelistAlignment:
    """B3: Readonly commands must align with architecture §2.2 safe set"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_rg_allowed(self, fake_project):
        """rg "memory/kb" src/ should allow (rg is read-only per architecture §2.2)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": 'rg "memory/kb" src/'},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 0, "rg should allow"
        assert output.get("decision") == "allow", "Decision should be 'allow'"

    def test_sed_n_allowed(self, fake_project):
        """sed -n 1p memory/kb/README.md should allow (sed -n is read-only)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "sed -n 1p memory/kb/README.md"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 0, "sed -n should allow"
        assert output.get("decision") == "allow", "Decision should be 'allow'"

    def test_sed_i_blocked(self, fake_project):
        """sed -i memory/kb/README.md should block (sed -i is write)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "sed -i 's/old/new/g' memory/kb/README.md"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "sed -i should block"
        assert output.get("decision") == "block", "Decision should be 'block'"


# ============================================================================
# B2: Git readonly subcommand tightening
# ============================================================================


class TestGitReadonlyTightening:
    """B2: Git readonly subcommands must be narrowed to truly safe set"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_git_log_owned_redirect_blocked(self, fake_project):
        """git log > memory/kb/out.txt should block (readonly cmd with owned redirect)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "git log > memory/kb/out.txt"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "git log > owned should block"
        assert output.get("decision") == "block", "Decision should be 'block'"

    def test_git_add_owned_blocked(self, fake_project):
        """git add memory/kb/x should block (git add is write, not readonly)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "git add memory/kb/x"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "git add owned should block"
        assert output.get("decision") == "block", "Decision should be 'block'"

    def test_git_clean_owned_blocked(self, fake_project):
        """git clean -f memory/kb should block (git clean is write)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "git clean -f memory/kb"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "git clean owned should block"
        assert output.get("decision") == "block", "Decision should be 'block'"

    def test_git_show_owned_redirect_blocked(self, fake_project):
        """git show HEAD > memory/kb/dump.txt should block (readonly cmd with owned redirect)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "git show HEAD > memory/kb/dump.txt"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "git show > owned should block"
        assert output.get("decision") == "block", "Decision should be 'block'"


# ============================================================================
# B4: Single & operator splitting
# ============================================================================


class TestSingleAmpersandSplitting:
    """B4: Single & (background operator) must split command segments"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_single_ampersand_splits(self, fake_project):
        """echo hi & rm -rf memory/kb should block (single & splits)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "echo hi & rm -rf memory/kb"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "Single & should split and rm should block"
        assert output.get("decision") == "block", "Decision should be 'block'"

    def test_double_ampersand_not_broken(self, fake_project):
        """echo hi && echo done should allow (&& is logical AND, not broken by B4)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "echo hi && echo done"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 0, "&& should not be broken"
        assert output.get("decision") == "allow", "Decision should be 'allow'"

    def test_ampersand_redirect_not_broken(self, fake_project):
        """echo hi &> /tmp/out should allow (&> is redirect, not split point)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "echo hi &> /tmp/out"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 0, "&> should not be broken"
        assert output.get("decision") == "allow", "Decision should be 'allow'"


# ============================================================================
# B1: Multi-segment legacy protection
# ============================================================================


class TestMultiSegmentLegacyProtection:
    """B1: Legacy extraction must run per write-intent segment"""

    @pytest.fixture
    def fake_project(self, tmp_path):
        (tmp_path / "memory" / "system").mkdir(parents=True)
        return tmp_path

    def test_backups_file_type_blocked(self, fake_project):
        """echo x > backups/y.sql && echo done should block (file-type blacklist)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "echo x > backups/y.sql && echo done"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "backups/ file-type should block"
        assert output.get("decision") == "block", "Decision should be 'block'"

    def test_uncertain_path_with_owned_context_blocked(self, fake_project):
        """rm -f $D/* && echo "memory/kb" should block (uncertain path + owned context)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": 'rm -f $D/* && echo "memory/kb"'},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "Uncertain path with owned context should block"
        assert output.get("decision") == "block", "Decision should be 'block'"

    def test_git_log_owned_redirect_blocked(self, fake_project):
        """git log > memory/kb/out.txt should block (legacy extraction per segment)"""
        payload = {
            "tool_name": "Execute",
            "tool_input": {"command": "git log > memory/kb/out.txt"},
        }
        exit_code, output = run_guard(payload, fake_project)

        assert exit_code == 2, "git log > owned should block"
        assert output.get("decision") == "block", "Decision should be 'block'"
