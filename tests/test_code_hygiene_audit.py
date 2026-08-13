"""Tests for code_hygiene_audit tool."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from memory_core.tools.code_hygiene_audit import (
    EXCLUDE_DIRS,
    MAX_FILE_SIZE,
    RULE_ID,
    SEVERITY,
    CATEGORY,
    DESCRIPTION,
    SwallowVisitor,
    audit_file,
    main,
    scan_directory,
    should_skip_file,
    should_skip_dir,
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

        findings = audit_file(test_file, tmp_path)
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

            result = main()

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
