"""Code hygiene audit: Detect silent exception swallowing patterns."""

import argparse
import ast
import codecs
import json
import os
import sys
from pathlib import Path
from typing import Any, NoReturn


# Module-level constants for testability
EXCLUDE_DIRS = frozenset(
    {
        "__pycache__",
        ".venv",
        "node_modules",
        "dist",
        "build",
        ".pytest_cache",
        ".ruff_cache",
        ".eggs",
        ".git",
        "archive",
    }
)
MAX_FILE_SIZE = 1_048_576  # 1MB
SKIP_SUFFIXES = frozenset({".pyi"})
SKIP_PATTERNS = frozenset({"_pb2.py"})

RULE_ID = "SILENT_SWALLOW"
SEVERITY = "warning"
CATEGORY = "code_hygiene"
DESCRIPTION = (
    "Silent exception swallow: except clause uses bare pass with no logging or re-raise"
)


class SwallowVisitor(ast.NodeVisitor):
    """AST visitor to detect silent exception swallowing patterns."""

    def __init__(self, filepath: str, relpath: str) -> None:
        self.filepath = filepath
        self.relpath = relpath
        self.stack: list[str] = ["<module>"]
        self.findings: list[dict[str, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Enter class scope."""
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Enter function scope."""
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Enter async function scope."""
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Check except handler for silent swallow pattern."""
        if self._is_silent_swallow(node):
            qualname = (
                ".".join(self.stack[1:]) if len(self.stack) > 1 else self.stack[0]
            )
            # Use lineno for unique location (col_offset can be same for different handlers)
            location = self._build_location(qualname, node.lineno)
            evidence = self._extract_evidence(node)
            self.findings.append(
                {
                    "rule_id": RULE_ID,
                    "severity": SEVERITY,
                    "category": CATEGORY,
                    "description": DESCRIPTION,
                    "location": location,
                    "evidence": evidence,
                }
            )
        self.generic_visit(node)

    def _is_silent_swallow(self, handler: ast.ExceptHandler) -> bool:
        """Check if the except handler silently swallows exceptions.

        Only detects:
        1. Bare except: (no type) with trivial body
        2. except Exception: or except BaseException: with trivial body
        """
        body = handler.body

        # Check for bare except (no type) - only report if body is trivial
        if handler.type is None:
            return self._is_trivial_body(body)

        # Check for except Exception: or except BaseException:
        if isinstance(handler.type, ast.Name) and handler.type.id in (
            "Exception",
            "BaseException",
        ):
            return self._is_trivial_body(body)

        return False

    def _is_trivial_body(self, body: list[ast.stmt]) -> bool:
        """Check if the handler body is trivial (pass or docstring only).

        Trivial means:
        - Empty body
        - Single pass statement
        - Single string literal (docstring)
        """
        if len(body) == 0:
            return True
        if len(body) == 1:
            stmt = body[0]
            if isinstance(stmt, ast.Pass):
                return True
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                # Pure string expression (docstring)
                return True
        return False

    def _build_location(self, qualname: str, lineno: int) -> str:
        """Build location string with length limit of 90 characters.

        Format: relative/path.py::qualname::L{lineno}
        If over 90 chars, truncate qualname from the middle.
        """
        prefix = f"{self.relpath}::"
        suffix = f"::L{lineno}"

        # Available space for qualname
        max_qualname_len = 90 - len(prefix) - len(suffix)

        if len(qualname) > max_qualname_len:
            # Truncate from middle to preserve both ends
            half = max_qualname_len // 2 - 1
            qualname = qualname[:half] + ".." + qualname[-half:]

        return f"{prefix}{qualname}{suffix}"

    def _extract_evidence(self, node: ast.ExceptHandler) -> str:
        """Extract the except clause as evidence string."""
        try:
            with open(self.filepath, "rb") as f:
                raw = f.read()

            # Remove BOM if present
            if raw.startswith(codecs.BOM_UTF8):
                raw = raw[len(codecs.BOM_UTF8) :]

            source = raw.decode("utf-8", errors="replace")
            lines = source.splitlines()

            if node.lineno <= len(lines):
                # Get the except line and the body
                start_line = node.lineno - 1
                end_line = getattr(node, "end_lineno", node.lineno + 1) - 1

                evidence_lines = lines[start_line : min(end_line, start_line + 5)]
                return "\n".join(evidence_lines).strip()
        except Exception:
            pass

        return "except clause with silent swallow"


def should_skip_file(path: Path) -> bool:
    """Check if a file should be skipped."""
    # Check file suffix
    if path.suffix in SKIP_SUFFIXES:
        return True

    # Check filename patterns
    filename = path.name
    for pattern in SKIP_PATTERNS:
        if pattern in filename:
            return True

    # Check file size
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return True
    except OSError:
        return True

    return False


def should_skip_dir(dirpath: Path) -> bool:
    """Check if a directory should be skipped."""
    return dirpath.name in EXCLUDE_DIRS


def audit_file(filepath: Path, repo_root: Path) -> list[dict[str, str]]:
    """Audit a single Python file for silent exception swallowing.

    Returns a list of findings. Returns empty list on error or if no findings.
    """
    try:
        # Read file with BOM handling
        raw = filepath.read_bytes()
        if raw.startswith(codecs.BOM_UTF8):
            raw = raw[len(codecs.BOM_UTF8) :]
        source = raw.decode("utf-8", errors="replace")

        # Parse AST
        tree = ast.parse(source)

        # Build relative path (fallback to filename if not in repo_root)
        try:
            relpath = filepath.relative_to(repo_root).as_posix()
        except ValueError:
            relpath = filepath.name

        # Visit AST
        visitor = SwallowVisitor(str(filepath), relpath)
        visitor.visit(tree)

        return visitor.findings

    except SyntaxError:
        # Skip files with syntax errors
        print(
            f"[code_hygiene_audit] Warning: SyntaxError in {filepath}, skipping",
            file=sys.stderr,
        )
        return []
    except RecursionError:
        # Skip files that cause recursion
        print(
            f"[code_hygiene_audit] Warning: RecursionError in {filepath}, skipping",
            file=sys.stderr,
        )
        return []
    except OSError as e:
        # Skip files with OS errors
        print(
            f"[code_hygiene_audit] Warning: OSError in {filepath}: {e}, skipping",
            file=sys.stderr,
        )
        return []
    except Exception as e:
        # Catch-all for unexpected errors
        print(
            f"[code_hygiene_audit] Warning: Error in {filepath}: {e}, skipping",
            file=sys.stderr,
        )
        return []


def scan_directory(target: Path, repo_root: Path) -> list[dict[str, str]]:
    """Scan a directory recursively for Python files with silent exception swallowing.

    Returns a list of all findings.
    """
    all_findings: list[dict[str, str]] = []

    for root, dirs, files in os.walk(target):
        root_path = Path(root)

        # Filter directories in-place to avoid descending into excluded dirs
        dirs[:] = [d for d in dirs if not should_skip_dir(Path(d))]

        for filename in files:
            if not filename.endswith(".py"):
                continue

            filepath = root_path / filename
            if not filepath.is_file():
                continue

            if should_skip_file(filepath):
                continue

            findings = audit_file(filepath, repo_root)
            all_findings.extend(findings)

    return all_findings


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for code hygiene audit.

    Returns:
        0 if no findings, 1 if findings found
    """
    parser = argparse.ArgumentParser(
        description="Audit Python code for silent exception swallowing patterns"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without side effects (default behavior)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output findings as JSON array",
    )
    parser.add_argument(
        "--target",
        type=str,
        default=".",
        help="Target directory to scan (default: current directory)",
    )
    args = parser.parse_args(argv)

    target_path = Path(args.target).resolve()
    repo_root = Path.cwd()

    if not target_path.exists():
        print(
            f"[code_hygiene_audit] Error: Target not found: {args.target}",
            file=sys.stderr,
        )
        return 2

    if target_path.is_file():
        # Single file mode
        if should_skip_file(target_path):
            print(
                f"[code_hygiene_audit] Error: File type excluded: {args.target}",
                file=sys.stderr,
            )
            return 2
        findings = audit_file(target_path, repo_root)
    else:
        # Directory mode
        findings = scan_directory(target_path, repo_root)

    # Sort findings by location for consistent output
    findings.sort(key=lambda f: f.get("location", ""))

    if args.json:
        json.dump(findings, sys.stdout, indent=2)
        print()
    else:
        # Human-readable output
        if findings:
            print(f"Found {len(findings)} silent exception swallowing patterns:")
            for finding in findings:
                print(f"  [{finding['severity'].upper()}] {finding['location']}")
                print(f"    {finding['description']}")
        else:
            print("No silent exception swallowing patterns found.")

    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
