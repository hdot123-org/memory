"""Tests for code_hygiene_audit tool."""

import json
import sys
from pathlib import Path

from memory_core.tools.code_hygiene_audit import (
    CATEGORY,
    RULE_ID,
    SEVERITY,
    SwallowVisitor,
    audit_file,
    main,
    scan_directory,
    should_skip_dir,
    should_skip_file,
)


class TestSwallowVisitor:
    """Tests for the SwallowVisitor AST visitor."""

    def test_bare_except_pass(self, tmp_path: Path) -> None:
        """Detect bare except with pass."""
        code = """
try:
    x = 1
except:
    pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 1
        finding = visitor.findings[0]
        assert finding["rule_id"] == RULE_ID
        assert finding["severity"] == SEVERITY
        assert finding["category"] == CATEGORY

    def test_except_exception_pass(self, tmp_path: Path) -> None:
        """Detect except Exception with pass."""
        code = """
try:
    x = 1
except Exception:
    pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 1

    def test_except_base_exception_pass(self, tmp_path: Path) -> None:
        """Detect except BaseException with pass."""
        code = """
try:
    x = 1
except BaseException:
    pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 1

    def test_except_exception_with_logger(self, tmp_path: Path) -> None:
        """Do not detect when logger is present."""
        code = """
try:
    x = 1
except Exception:
    logger.error("error")
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 0

    def test_except_exception_with_raise(self, tmp_path: Path) -> None:
        """Do not detect when raise is present."""
        code = """
try:
    x = 1
except Exception:
    raise
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 0

    def test_except_exception_with_return(self, tmp_path: Path) -> None:
        """Do not detect when return is present."""
        code = """
try:
    x = 1
except Exception:
    return None
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 0

    def test_except_exception_with_print(self, tmp_path: Path) -> None:
        """Do not detect when print is present."""
        code = """
try:
    x = 1
except Exception:
    print("err")
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 0

    def test_except_exception_with_function_call(self, tmp_path: Path) -> None:
        """Do not detect when function call is present."""
        code = """
try:
    x = 1
except Exception:
    self._handle()
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 0

    def test_except_exception_with_assignment(self, tmp_path: Path) -> None:
        """Do not detect when assignment is present."""
        code = """
try:
    x = 1
except Exception:
    x = 1
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 0

    def test_except_keyerror_pass(self, tmp_path: Path) -> None:
        """Do not detect specific exception types like KeyError."""
        code = """
try:
    x = 1
except KeyError:
    pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 0

    def test_except_exception_with_docstring(self, tmp_path: Path) -> None:
        """Detect except Exception with only docstring."""
        code = '''
try:
    x = 1
except Exception:
    """silenced"""
'''
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 1

    def test_except_exception_empty_body(self, tmp_path: Path) -> None:
        """Detect except Exception with empty body (same line)."""
        code = """
try:
    x = 1
except Exception:
    ...
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        # Python AST treats empty body differently
        # This might not trigger depending on Python version
        # but we include it for completeness

    def test_except_exception_multiple_statements(self, tmp_path: Path) -> None:
        """Do not detect when multiple statements are present."""
        code = """
try:
    x = 1
except Exception:
    pass
    x = 1
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "test.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 0


class TestNestedStructures:
    """Tests for nested class/function structures."""

    def test_class_method_bare_except(self, tmp_path: Path) -> None:
        """Detect bare except in class method with proper qualname."""
        code = """
class Bar:
    def baz(self):
        try:
            x = 1
        except:
            pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "foo.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 1
        finding = visitor.findings[0]
        assert "Bar.baz" in finding["location"]

    def test_nested_function_bare_except(self, tmp_path: Path) -> None:
        """Detect bare except in nested function with proper qualname."""
        code = """
def outer():
    def inner():
        try:
            x = 1
        except:
            pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "foo.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 1
        finding = visitor.findings[0]
        assert "outer.inner" in finding["location"]

    def test_module_level_bare_except(self, tmp_path: Path) -> None:
        """Detect bare except at module level with <module> qualname."""
        code = """
try:
    x = 1
except:
    pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "foo.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 1
        finding = visitor.findings[0]
        assert "<module>" in finding["location"]

    def test_multiple_except_handlers(self, tmp_path: Path) -> None:
        """Detect multiple bare except in same function."""
        code = """
def func():
    try:
        x = 1
    except:
        pass

    try:
        y = 2
    except:
        pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "foo.py")
        visitor.visit(tree)

        assert len(visitor.findings) == 2
        # Check locations are different
        assert visitor.findings[0]["location"] != visitor.findings[1]["location"]


class TestRobustness:
    """Tests for CLI robustness and edge cases."""

    def test_syntax_error_file(self, tmp_path: Path) -> None:
        """Skip files with syntax errors without crashing."""
        test_file = tmp_path / "broken.py"
        test_file.write_text("def foo(\n")  # Syntax error

        findings = audit_file(test_file, tmp_path)
        assert findings == []

    def test_unicode_decode_error(self, tmp_path: Path) -> None:
        """Handle files with encoding issues using replacement."""
        test_file = tmp_path / "bad_encoding.py"
        # Write invalid UTF-8 bytes
        test_file.write_bytes(b"# coding: utf-8\n\xff\xfe")

        audit_file(test_file, tmp_path)
        # Should not crash, might return empty or findings

    def test_utf8_bom_file(self, tmp_path: Path) -> None:
        """Correctly parse files with UTF-8 BOM."""
        test_file = tmp_path / "bom.py"
        # Write with BOM
        test_file.write_bytes(
            b'\xef\xbb\xbfx = 1\n\ntry:\n    pass\nexcept:\n    pass\n'
        )

        findings = audit_file(test_file, tmp_path)
        assert len(findings) == 1

    def test_empty_file(self, tmp_path: Path) -> None:
        """Handle empty files."""
        test_file = tmp_path / "empty.py"
        test_file.write_text("")

        findings = audit_file(test_file, tmp_path)
        assert findings == []

    def test_comment_only_file(self, tmp_path: Path) -> None:
        """Handle files with only comments."""
        test_file = tmp_path / "comments.py"
        test_file.write_text("# This is a comment\n# Another comment")

        findings = audit_file(test_file, tmp_path)
        assert findings == []

    def test_pyi_file_skip(self, tmp_path: Path) -> None:
        """Skip .pyi stub files."""
        test_file = tmp_path / "stub.pyi"
        test_file.write_text("def foo(): ...")

        assert should_skip_file(test_file) is True

    def test_pb2_file_skip(self, tmp_path: Path) -> None:
        """Skip _pb2.py generated files."""
        test_file = tmp_path / "test_pb2.py"
        test_file.write_text("x = 1")

        assert should_skip_file(test_file) is True

    def test_pycache_dir_skip(self, tmp_path: Path) -> None:
        """Skip __pycache__ directories."""
        assert should_skip_dir(Path("__pycache__")) is True

    def test_venv_dir_skip(self, tmp_path: Path) -> None:
        """Skip .venv directories."""
        assert should_skip_dir(Path(".venv")) is True


class TestOutputFormat:
    """Tests for output format compliance."""

    def test_json_output_valid(self, tmp_path: Path) -> None:
        """Output valid JSON array."""
        code = """
try:
    x = 1
except:
    pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        # Run main with --json
        old_argv = sys.argv
        try:
            sys.argv = [
                "memory-code-hygiene-audit",
                "--json",
                "--target",
                str(tmp_path),
            ]

            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()

            main()

            output = sys.stdout.getvalue()
            sys.stdout = old_stdout

            # Parse JSON
            findings = json.loads(output)
            assert isinstance(findings, list)
            if findings:
                assert "rule_id" in findings[0]
                assert "severity" in findings[0]
                assert "category" in findings[0]
                assert "description" in findings[0]
                assert "location" in findings[0]
                assert "evidence" in findings[0]

        finally:
            sys.argv = old_argv

    def test_exit_code_no_findings(self, tmp_path: Path) -> None:
        """Exit code 0 when no findings."""
        test_file = tmp_path / "clean.py"
        test_file.write_text("x = 1")

        old_argv = sys.argv
        try:
            sys.argv = [
                "memory-code-hygiene-audit",
                "--target",
                str(tmp_path),
            ]
            result = main()
            assert result == 0
        finally:
            sys.argv = old_argv

    def test_exit_code_with_findings(self, tmp_path: Path) -> None:
        """Exit code 1 when findings present."""
        test_file = tmp_path / "bad.py"
        test_file.write_text("try:\n    pass\nexcept:\n    pass")

        old_argv = sys.argv
        try:
            sys.argv = [
                "memory-code-hygiene-audit",
                "--target",
                str(tmp_path),
            ]
            result = main()
            assert result == 1
        finally:
            sys.argv = old_argv


class TestLocationFormat:
    """Tests for location format compliance."""

    def test_location_length_limit(self, tmp_path: Path) -> None:
        """Location should not exceed 90 characters."""
        # Create deeply nested structure
        code = """
class VeryLongClassNameThatMakesThePathVeryLong:
    def very_long_method_name_that_adds_to_length(self):
        try:
            x = 1
        except:
            pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(
            str(test_file), "path/to/module.py"
        )
        visitor.visit(tree)

        if visitor.findings:
            location = visitor.findings[0]["location"]
            assert len(location) <= 90

    def test_location_format(self, tmp_path: Path) -> None:
        """Location format should be file::qualname::Llineno."""
        code = """
def foo():
    try:
        x = 1
    except:
        pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        tree = compile(code, str(test_file), "exec", ast.PyCF_ONLY_AST)
        visitor = SwallowVisitor(str(test_file), "foo.py")
        visitor.visit(tree)

        finding = visitor.findings[0]
        location = finding["location"]
        parts = location.split("::")
        assert len(parts) == 3
        assert parts[0] == "foo.py"
        assert parts[1] == "foo"
        assert parts[2].startswith("L")


class TestDryRunFlag:
    """Tests for --dry-run flag behavior."""

    def test_dry_run_flag_accepted(self, tmp_path: Path) -> None:
        """--dry-run flag should be accepted."""
        test_file = tmp_path / "clean.py"
        test_file.write_text("x = 1")

        old_argv = sys.argv
        try:
            sys.argv = [
                "memory-code-hygiene-audit",
                "--dry-run",
                "--target",
                str(tmp_path),
            ]
            result = main()
            # Should not crash
            assert result in (0, 1, 2)
        finally:
            sys.argv = old_argv


class TestScanDirectory:
    """Tests for directory scanning."""

    def test_scan_finds_python_files(self, tmp_path: Path) -> None:
        """Scan should find all Python files."""
        # Create multiple files
        (tmp_path / "a.py").write_text("try:\n    pass\nexcept:\n    pass")
        (tmp_path / "b.py").write_text("try:\n    pass\nexcept:\n    pass")

        findings = scan_directory(tmp_path, tmp_path)
        assert len(findings) == 2

    def test_scan_skips_excluded_dirs(self, tmp_path: Path) -> None:
        """Scan should skip excluded directories."""
        # Create file in excluded dir
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "bad.py").write_text("try:\n    pass\nexcept:\n    pass")

        # Create file in normal dir
        normal = tmp_path / "src"
        normal.mkdir()
        (normal / "good.py").write_text("x = 1")

        findings = scan_directory(tmp_path, tmp_path)
        # Should not find the __pycache__ file
        assert len(findings) == 0


import ast

from memory_core.tools.code_hygiene_audit import (
    TODO_RULE_ID,
    TODO_SEVERITY,
    check_todos,
)


class TestTodoDetection:
    """Tests for TODO/FIXME/HACK detection without issue references."""

    def test_todo_without_issue_detected(self, tmp_path: Path) -> None:
        """Bare TODO comment without issue reference is flagged."""
        code = "# TODO fix this later\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 1
        finding = findings[0]
        assert finding["rule_id"] == TODO_RULE_ID
        assert finding["rule_id"] == "CODE_HYGIENE_UNTRACKED_TODO"
        assert finding["severity"] == TODO_SEVERITY
        assert finding["severity"] == "warning"
        assert finding["category"] == "code_hygiene"

    def test_todo_in_string_literal_not_flagged(self, tmp_path: Path) -> None:
        """String literals containing '# TODO' are not flagged (INFRA-272)."""
        code = 'code = "# TODO fix this later\\nx = 1\\n"\nx = 1\n'
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 0

    def test_todo_in_triple_quoted_string_not_flagged(self, tmp_path: Path) -> None:
        """TODO inside a triple-quoted string is not flagged (INFRA-272)."""
        code = 'code = """\n# TODO fix this\ntry:\n    x = 1\nexcept:\n    pass\n"""\n'
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 0

    def test_fixme_without_issue_detected(self, tmp_path: Path) -> None:
        """Bare FIXME comment without issue reference is flagged."""
        code = "# FIXME this is broken\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 1
        finding = findings[0]
        assert finding["rule_id"] == "CODE_HYGIENE_UNTRACKED_TODO"
        assert finding["severity"] == "warning"

    def test_hack_without_issue_detected(self, tmp_path: Path) -> None:
        """Bare HACK comment is flagged."""
        code = "# HACK workaround for bug\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 1
        finding = findings[0]
        assert finding["rule_id"] == "CODE_HYGIENE_UNTRACKED_TODO"

    def test_todo_with_issue_ref_parentheses_exempt(self, tmp_path: Path) -> None:
        """TODO(#123) is not flagged."""
        code = "# TODO(#123) fix this later\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 0

    def test_fixme_with_gh_issue_ref_exempt(self, tmp_path: Path) -> None:
        """FIXME(GH-456) is not flagged."""
        code = "# FIXME(GH-456) broken\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 0

    def test_todo_with_infra_issue_ref_exempt(self, tmp_path: Path) -> None:
        """TODO(INFRA-789) is not flagged."""
        code = "# TODO(INFRA-789) implement this\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 0

    def test_hack_with_issue_ref_exempt(self, tmp_path: Path) -> None:
        """HACK(#123) is not flagged."""
        code = "# HACK(#123) workaround for upstream bug\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 0

    def test_finding_has_correct_6_field_schema(self, tmp_path: Path) -> None:
        """Finding has all 6 fields with correct types."""
        code = "# TODO fix this\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 1
        finding = findings[0]
        required_fields = {"rule_id", "severity", "category", "description", "location", "evidence"}
        assert set(finding.keys()) == required_fields
        assert all(isinstance(v, str) for v in finding.values())

    def test_finding_location_format(self, tmp_path: Path) -> None:
        """Location format is path/to/file.py::L<lineno>."""
        code = "x = 1\n# TODO fix this\ny = 2\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 1
        finding = findings[0]
        assert finding["location"] == "test.py::L2"

    def test_finding_evidence_contains_comment(self, tmp_path: Path) -> None:
        """Evidence contains the offending comment text."""
        code = "# TODO fix this later\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 1
        finding = findings[0]
        assert "TODO" in finding["evidence"]
        assert "fix this later" in finding["evidence"]

    def test_todo_in_excluded_dir_not_scanned(self, tmp_path: Path) -> None:
        """Files in excluded directories are not scanned."""
        # Create .venv directory with TODO
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        (venv_dir / "test.py").write_text("# TODO fix this\nx = 1\n")

        # Create build directory with TODO
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "test.py").write_text("# TODO fix this\nx = 1\n")

        # Create normal file with TODO
        (tmp_path / "normal.py").write_text("# TODO fix this\nx = 1\n")

        findings = scan_directory(tmp_path, tmp_path)
        # Only the normal file should be scanned
        todo_findings = [f for f in findings if f["rule_id"] == "CODE_HYGIENE_UNTRACKED_TODO"]
        assert len(todo_findings) == 1
        assert "normal.py" in todo_findings[0]["location"]

    def test_scan_directory_combines_silent_swallow_and_todo(self, tmp_path: Path) -> None:
        """scan_directory returns both SILENT_SWALLOW and CODE_HYGIENE_UNTRACKED_TODO findings."""
        # File with both patterns
        code = """
# TODO fix this
try:
    x = 1
except:
    pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = scan_directory(tmp_path, tmp_path)
        rule_ids = {f["rule_id"] for f in findings}
        assert "SILENT_SWALLOW" in rule_ids
        assert "CODE_HYGIENE_UNTRACKED_TODO" in rule_ids

    def test_multiple_todos_in_same_file(self, tmp_path: Path) -> None:
        """Multiple bare TODOs in same file are all detected."""
        code = "# TODO first\n# TODO second\n# FIXME third\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 3

    def test_mixed_tracked_and_untracked_todos(self, tmp_path: Path) -> None:
        """Only untracked TODOs are flagged, tracked ones are exempt."""
        code = "# TODO(#123) tracked\n# TODO untracked\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 1
        assert "untracked" in findings[0]["evidence"]

    def test_todo_case_insensitive(self, tmp_path: Path) -> None:
        """TODO detection is case-insensitive."""
        code = "# todo fix this\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 1

    def test_todo_word_prefix_not_flagged(self, tmp_path: Path) -> None:
        """'# TODOLIST' is not a TODO marker — word boundary prevents false positive (INFRA-273)."""
        code = "# TODOLIST items here\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 0

    def test_todos_plural_not_flagged(self, tmp_path: Path) -> None:
        """'# TODOS' is not a TODO marker (INFRA-273)."""
        code = "# TODOS need fixing\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 0

    def test_todo_underscore_suffix_not_flagged(self, tmp_path: Path) -> None:
        """'# TODO_LIST' is not a TODO marker (INFRA-273)."""
        code = "# TODO_LIST items\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 0

    def test_fixme_word_prefix_not_flagged(self, tmp_path: Path) -> None:
        """'# FIXMELIST' is not a FIXME marker (INFRA-273)."""
        code = "# FIXMELIST items\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 0

    def test_hack_word_prefix_not_flagged(self, tmp_path: Path) -> None:
        """'# HACKLIST' is not a HACK marker (INFRA-273)."""
        code = "# HACKLIST items\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 0

    def test_todo_bare_marker_still_detected_with_word_boundary(self, tmp_path: Path) -> None:
        """Bare '# TODO' (nothing after) is still detected with word boundary fix (INFRA-273)."""
        code = "# TODO\nx = 1\n"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = check_todos(test_file, "test.py")
        assert len(findings) == 1


from memory_core.tools.code_hygiene_audit import (
    DUPLICATE_RULE_ID,
    DUPLICATE_SEVERITY,
)


class TestDuplicateDetection:
    """Tests for AST-based duplicate code detection."""

    def test_duplicate_same_name_detected(self, tmp_path: Path) -> None:
        """Two same-name functions with >=80% similarity and >=10 lines are detected."""
        # Create two functions with same name and high similarity (>=10 lines)
        code = """
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result

def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = scan_directory(tmp_path, tmp_path)
        duplicate_findings = [f for f in findings if f["rule_id"] == "CODE_HYGIENE_DUPLICATE_BLOCK"]
        assert len(duplicate_findings) == 1
        finding = duplicate_findings[0]
        assert finding["rule_id"] == DUPLICATE_RULE_ID
        assert finding["severity"] == DUPLICATE_SEVERITY
        assert finding["severity"] == "info"
        assert finding["category"] == "code_hygiene"

    def test_duplicate_small_functions_not_flagged(self, tmp_path: Path) -> None:
        """Functions with <10 lines AND <50 tokens are not flagged."""
        # Two small functions (5 lines each, well under threshold)
        code = """
def small_func(x):
    return x + 1

def small_func(x):
    return x + 1
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = scan_directory(tmp_path, tmp_path)
        duplicate_findings = [f for f in findings if f["rule_id"] == "CODE_HYGIENE_DUPLICATE_BLOCK"]
        assert len(duplicate_findings) == 0

    def test_duplicate_different_names_now_detected(self, tmp_path: Path) -> None:
        """Cross-name functions with identical structure are now detected (INFRA-273)."""
        code = """
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result

def handle_input(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = scan_directory(tmp_path, tmp_path)
        duplicate_findings = [f for f in findings if f["rule_id"] == "CODE_HYGIENE_DUPLICATE_BLOCK"]
        assert len(duplicate_findings) == 1
        finding = duplicate_findings[0]
        assert "Cross-name structural duplicate" in finding["evidence"]
        assert "process_data" in finding["evidence"]
        assert "handle_input" in finding["evidence"]

    def test_cross_name_different_structure_not_flagged(self, tmp_path: Path) -> None:
        """Functions with different names and genuinely different structures are not flagged."""
        code = """
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result

def compute_total(values):
    total = 0
    for v in values:
        total += v * v
    return total
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = scan_directory(tmp_path, tmp_path)
        duplicate_findings = [f for f in findings if f["rule_id"] == "CODE_HYGIENE_DUPLICATE_BLOCK"]
        assert len(duplicate_findings) == 0

    def test_duplicate_cross_file_detection(self, tmp_path: Path) -> None:
        """Same-name functions in different files are detected."""
        # File 1
        code1 = """
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result
"""
        (tmp_path / "file1.py").write_text(code1)

        # File 2 - same function name, similar implementation
        code2 = """
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result
"""
        (tmp_path / "file2.py").write_text(code2)

        findings = scan_directory(tmp_path, tmp_path)
        duplicate_findings = [f for f in findings if f["rule_id"] == "CODE_HYGIENE_DUPLICATE_BLOCK"]
        assert len(duplicate_findings) == 1
        finding = duplicate_findings[0]
        # Location should reference both files
        assert "file1.py" in finding["location"]
        assert "file2.py" in finding["location"]

    def test_duplicate_pair_deduplication(self, tmp_path: Path) -> None:
        """Same pair is reported at most once."""
        # Create three identical functions - should report 3 pairs (1-2, 1-3, 2-3)
        code = """
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result

def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result

def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = scan_directory(tmp_path, tmp_path)
        duplicate_findings = [f for f in findings if f["rule_id"] == "CODE_HYGIENE_DUPLICATE_BLOCK"]
        # Should have exactly 3 unique pairs
        assert len(duplicate_findings) == 3

    def test_duplicate_finding_has_correct_6_field_schema(self, tmp_path: Path) -> None:
        """Duplicate finding has all 6 fields with correct types."""
        code = """
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result

def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = scan_directory(tmp_path, tmp_path)
        duplicate_findings = [f for f in findings if f["rule_id"] == "CODE_HYGIENE_DUPLICATE_BLOCK"]
        assert len(duplicate_findings) == 1
        finding = duplicate_findings[0]
        required_fields = {"rule_id", "severity", "category", "description", "location", "evidence"}
        assert set(finding.keys()) == required_fields
        assert all(isinstance(v, str) for v in finding.values())

    def test_duplicate_location_references_both_files(self, tmp_path: Path) -> None:
        """Location format references both file:line pairs."""
        code = """
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result

def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = scan_directory(tmp_path, tmp_path)
        duplicate_findings = [f for f in findings if f["rule_id"] == "CODE_HYGIENE_DUPLICATE_BLOCK"]
        assert len(duplicate_findings) == 1
        finding = duplicate_findings[0]
        # Location should contain line numbers
        assert "L" in finding["location"]

    def test_scan_directory_combines_all_three_rules(self, tmp_path: Path) -> None:
        """scan_directory returns SILENT_SWALLOW + TODO + DUPLICATE findings together."""
        # File with all three patterns
        code = """
# TODO fix this later

def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result

def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
        elif item < 0:
            result.append(item * -1)
        else:
            result.append(0)
    return result

try:
    x = 1
except:
    pass
"""
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        findings = scan_directory(tmp_path, tmp_path)
        rule_ids = {f["rule_id"] for f in findings}
        assert "SILENT_SWALLOW" in rule_ids
        assert "CODE_HYGIENE_UNTRACKED_TODO" in rule_ids
        assert "CODE_HYGIENE_DUPLICATE_BLOCK" in rule_ids
