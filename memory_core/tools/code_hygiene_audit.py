"""Code hygiene audit: Detect silent exception swallowing patterns."""

import argparse
import ast
import codecs
import io
import json
import os
import re
import sys
import tokenize
from difflib import SequenceMatcher
from pathlib import Path
from typing import NamedTuple

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

# Untracked comment detection constants (absorbed from scan_tech_debt.py)
TODO_RULE_ID = "CODE_HYGIENE_UNTRACKED_TODO"
TODO_SEVERITY = "warning"
TODO_DESCRIPTION = "TODO/FIXME/HACK without issue reference"

# Regex patterns: TODO/FIXME/HACK NOT followed by (#NNN) or (GH-NNN)
TODO_PATTERNS = [
    (re.compile(r"#\s*TODO(?!\s*[\(#])", re.IGNORECASE), "TODO without issue reference"),
    (re.compile(r"#\s*FIXME(?!\s*[\(#])", re.IGNORECASE), "FIXME without issue reference"),
    (re.compile(r"#\s*HACK(?!\s*[\(#])", re.IGNORECASE), "HACK without issue reference"),
]

# Duplicate detection constants (absorbed from v5_duplicate_scan.py)
DUPLICATE_RULE_ID = "CODE_HYGIENE_DUPLICATE_BLOCK"
DUPLICATE_SEVERITY = "info"
DUPLICATE_DESCRIPTION = "Duplicate code block detected"
SIMILARITY_THRESHOLD = 0.80
MIN_BODY_LINES = 10
MIN_AST_TOKENS = 50


class FuncInfo(NamedTuple):
    """Information about a function for duplicate detection."""
    file: str
    name: str
    line_no: int
    body_lines: int
    ast_tokens: int
    ast_dump: str


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
        except Exception as e:
            print(
                f"[code_hygiene_audit] Warning: Failed to extract evidence from "
                f"{self.filepath}: {e}",
                file=sys.stderr,
            )

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


def check_todos(filepath: Path, relpath: str) -> list[dict[str, str]]:
    """Check for TODO/FIXME/HACK comments without issue references.

    Detects TODO/FIXME/HACK markers that are NOT followed by issue
    references like (#NNN) or (GH-NNN).

    Uses tokenization to inspect only real Python comments, correctly
    ignoring string literals that contain '# TODO' style text (INFRA-272).
    Falls back to a line-by-line scan if tokenization fails (e.g. on
    files with syntax errors) so real TODOs are never silently missed.

    Args:
        filepath: Absolute path to the file
        relpath: Relative path for reporting

    Returns:
        List of findings in 6-field JSON schema
    """
    findings: list[dict[str, str]] = []

    try:
        # Read file with BOM handling
        raw = filepath.read_bytes()
        if raw.startswith(codecs.BOM_UTF8):
            raw = raw[len(codecs.BOM_UTF8) :]
        source = raw.decode("utf-8", errors="replace")

        # Collect (lineno, comment_text) from real COMMENT tokens only.
        # String literals containing "# TODO" are STRING tokens, not COMMENT
        # tokens, so they are correctly excluded (INFRA-272).
        comment_lines: list[tuple[int, str]] = []
        try:
            tokens = tokenize.generate_tokens(io.StringIO(source).readline)
            for tok in tokens:
                if tok.type == tokenize.COMMENT:
                    comment_lines.append((tok.start[0], tok.string))
        except Exception:
            # Fallback: tokenization failed (e.g. syntax error). Scan every
            # line to avoid missing real TODOs in un-parseable files.
            for lineno, line in enumerate(source.splitlines(), start=1):
                hash_pos = line.find("#")
                if hash_pos >= 0:
                    comment_lines.append((lineno, line[hash_pos:]))

        for lineno, text in comment_lines:
            for pattern, label in TODO_PATTERNS:
                if pattern.match(text):
                    # Build finding in 6-field schema
                    findings.append(
                        {
                            "rule_id": TODO_RULE_ID,
                            "severity": TODO_SEVERITY,
                            "category": CATEGORY,
                            "description": label,
                            "location": f"{relpath}::L{lineno}",
                            "evidence": text.strip(),
                        }
                    )

    except OSError as e:
        print(
            f"[code_hygiene_audit] Warning: OSError reading {filepath}: {e}",
            file=sys.stderr,
        )
    except Exception as e:
        print(
            f"[code_hygiene_audit] Warning: Error checking TODOs in {filepath}: {e}",
            file=sys.stderr,
        )

    return findings


def _count_ast_tokens(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count AST nodes (rough token proxy) in a function body."""
    return sum(1 for _ in ast.walk(func_node))


def _count_body_lines(func_node: ast.FunctionDef | ast.AsyncFunctionDef, source_lines: list[str]) -> int:
    """Count non-empty, non-comment body lines."""
    if not func_node.body:
        return 0
    start = func_node.body[0].lineno - 1
    end = func_node.end_lineno or (start + 1)
    count = 0
    for line in source_lines[start:end]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def extract_functions_for_duplicate_check(filepath: Path, repo_root: Path) -> list[FuncInfo]:
    """Extract function definitions from a Python file for duplicate detection.
    
    Only includes functions that meet the size threshold:
    >= MIN_BODY_LINES body lines OR >= MIN_AST_TOKENS AST tokens.
    
    Args:
        filepath: Absolute path to the file
        repo_root: Repository root for relative path computation
        
    Returns:
        List of FuncInfo for qualifying functions
    """
    try:
        raw = filepath.read_bytes()
        if raw.startswith(codecs.BOM_UTF8):
            raw = raw[len(codecs.BOM_UTF8):]
        source = raw.decode("utf-8", errors="replace")
        source_lines = source.splitlines()
    except (OSError, UnicodeDecodeError) as e:
        print(
            f"[code_hygiene_audit] Warning: Error reading {filepath}: {e}",
            file=sys.stderr,
        )
        return []

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    try:
        relpath = filepath.relative_to(repo_root).as_posix()
    except ValueError:
        relpath = filepath.name

    funcs: list[FuncInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body_lines = _count_body_lines(node, source_lines)
            ast_tokens = _count_ast_tokens(node)
            if body_lines >= MIN_BODY_LINES or ast_tokens >= MIN_AST_TOKENS:
                # Get AST dump without annotation fields for comparison
                node_copy = ast.parse(ast.unparse(node))
                ast_dump_str = ast.dump(node_copy, annotate_fields=False)
                funcs.append(FuncInfo(
                    file=relpath,
                    name=node.name,
                    line_no=node.lineno,
                    body_lines=body_lines,
                    ast_tokens=ast_tokens,
                    ast_dump=ast_dump_str,
                ))
    return funcs


def check_duplicates(funcs: list[FuncInfo]) -> list[dict[str, str]]:
    """Compare functions for duplicate code blocks.
    
    Groups functions by name, then compares same-name pairs using
    SequenceMatcher.ratio() >= SIMILARITY_THRESHOLD.
    Deduplicates pairs by canonicalized (file_a, line_a, file_b, line_b) key.
    
    Args:
        funcs: List of FuncInfo from all files
        
    Returns:
        List of findings in 6-field JSON schema
    """
    findings: list[dict[str, str]] = []
    
    # Group by name
    by_name: dict[str, list[FuncInfo]] = {}
    for func in funcs:
        by_name.setdefault(func.name, []).append(func)
    
    seen_pairs: set[tuple[str, int, str, int]] = set()
    
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                
                # Skip self-comparison
                if a.file == b.file and a.line_no == b.line_no:
                    continue
                
                # Canonicalize pair key for dedup
                pair = sorted([(a.file, a.line_no), (b.file, b.line_no)])
                pair_key = (pair[0][0], pair[0][1], pair[1][0], pair[1][1])
                if pair_key in seen_pairs:
                    continue
                
                # Compare AST dumps
                ratio = SequenceMatcher(None, a.ast_dump, b.ast_dump).ratio()
                if ratio >= SIMILARITY_THRESHOLD:
                    seen_pairs.add(pair_key)
                    # Build finding
                    location = (
                        f"{a.file}::L{a.line_no} <-> {b.file}::L{b.line_no}"
                    )
                    evidence = (
                        f"Function '{name}' has {ratio:.0%} AST similarity "
                        f"({a.body_lines} lines / {a.ast_tokens} tokens vs "
                        f"{b.body_lines} lines / {b.ast_tokens} tokens)"
                    )
                    findings.append({
                        "rule_id": DUPLICATE_RULE_ID,
                        "severity": DUPLICATE_SEVERITY,
                        "category": CATEGORY,
                        "description": DUPLICATE_DESCRIPTION,
                        "location": location,
                        "evidence": evidence,
                    })
    
    return findings


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
    all_funcs: list[FuncInfo] = []

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

            # Compute relative path for reporting
            try:
                relpath = filepath.relative_to(repo_root).as_posix()
            except ValueError:
                relpath = filepath.name

            # Get silent swallow findings
            findings = audit_file(filepath, repo_root)
            all_findings.extend(findings)

            # Get TODO/FIXME/HACK findings
            todo_findings = check_todos(filepath, relpath)
            all_findings.extend(todo_findings)

            # Extract functions for duplicate detection
            funcs = extract_functions_for_duplicate_check(filepath, repo_root)
            all_funcs.extend(funcs)

    # Run duplicate detection across all collected functions
    duplicate_findings = check_duplicates(all_funcs)
    all_findings.extend(duplicate_findings)

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
        # Also check for TODOs in single-file mode
        try:
            relpath = target_path.relative_to(repo_root).as_posix()
        except ValueError:
            relpath = target_path.name
        findings.extend(check_todos(target_path, relpath))
        # Also check for duplicates within the same file
        funcs = extract_functions_for_duplicate_check(target_path, repo_root)
        findings.extend(check_duplicates(funcs))
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
