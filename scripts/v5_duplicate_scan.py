#!/usr/bin/env python3
"""v5 spec duplicate scanner (ast.dump + SequenceMatcher + minimum-size filter).

Methodology:
- ast.dump(annotate_fields=False) — canonical normalization per Python docs
- difflib.SequenceMatcher.ratio() ≥ 0.80 threshold
- Minimum-size filter: ≥10 body lines OR ≥50 AST tokens (SonarQube/jscpd default)
- Scope: memory_core/ + scripts/
- Output: count of truly duplicate function/method pairs

Usage:
    python3 scripts/v5_duplicate_scan.py
"""

from __future__ import annotations

import ast
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import NamedTuple

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = [PROJECT_ROOT / "memory_core", PROJECT_ROOT / "scripts"]
SIMILARITY_THRESHOLD = 0.80
MIN_BODY_LINES = 10
MIN_AST_TOKENS = 50


class FuncInfo(NamedTuple):
    file: str
    name: str
    line_no: int
    body_lines: int
    ast_tokens: int
    ast_dump: str


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


def _extract_functions(file_path: Path, source_lines: list[str]) -> list[FuncInfo]:
    """Extract all function/method definitions from a Python file."""
    source = "\n".join(source_lines)
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    funcs: list[FuncInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body_lines = _count_body_lines(node, source_lines)
            ast_tokens = _count_ast_tokens(node)
            if body_lines >= MIN_BODY_LINES or ast_tokens >= MIN_AST_TOKENS:
                # Get AST dump without annotation fields
                node_copy = ast.parse(ast.unparse(node))
                ast_dump_str = ast.dump(node_copy, annotate_fields=False)
                funcs.append(FuncInfo(
                    file=str(file_path.relative_to(PROJECT_ROOT)),
                    name=node.name,
                    line_no=node.lineno,
                    body_lines=body_lines,
                    ast_tokens=ast_tokens,
                    ast_dump=ast_dump_str,
                ))
    return funcs


def _is_duplicate(a: FuncInfo, b: FuncInfo) -> bool:
    """Check if two functions are duplicates (same name, high AST similarity)."""
    if a.name != b.name:
        return False
    if a.file == b.file and a.line_no == b.line_no:
        return False
    ratio = SequenceMatcher(None, a.ast_dump, b.ast_dump).ratio()
    return ratio >= SIMILARITY_THRESHOLD


def scan() -> list[tuple[FuncInfo, FuncInfo]]:
    """Scan all Python files and return duplicate pairs."""
    all_funcs: list[FuncInfo] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for py_file in sorted(scan_dir.rglob("*.py")):
            if "test_" in py_file.name or "__pycache__" in str(py_file):
                continue
            try:
                source_lines = py_file.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            all_funcs.extend(_extract_functions(py_file, source_lines))

    # Group by name first
    by_name: dict[str, list[FuncInfo]] = {}
    for func in all_funcs:
        by_name.setdefault(func.name, []).append(func)

    duplicates: list[tuple[FuncInfo, FuncInfo]] = []
    seen_pairs: set[tuple[str, int, str, int]] = set()

    for name, funcs in by_name.items():
        if len(funcs) < 2:
            continue
        for i in range(len(funcs)):
            for j in range(i + 1, len(funcs)):
                a, b = funcs[i], funcs[j]
                pair_key = tuple(sorted([(a.file, a.line_no), (b.file, b.line_no)]))
                if pair_key in seen_pairs:
                    continue
                if _is_duplicate(a, b):
                    duplicates.append((a, b))
                    seen_pairs.add(pair_key)

    return duplicates


def main() -> int:
    """Main entry point."""
    print("=" * 72)
    print("v5 Duplicate Scan (ast.dump + SequenceMatcher + min-size filter)")
    print("=" * 72)
    print(f"Threshold: {SIMILARITY_THRESHOLD}")
    print(f"Min-size filter: ≥{MIN_BODY_LINES} lines OR ≥{MIN_AST_TOKENS} tokens")
    print("Scope: memory_core/ + scripts/")
    print()

    duplicates = scan()

    if not duplicates:
        print("✓ No duplicate pairs found (count = 0)")
        return 0

    print(f"✗ Found {len(duplicates)} duplicate pair(s):\n")
    for i, (a, b) in enumerate(duplicates, 1):
        print(f"{i:3d}. {a.name}")
        print(f"     {a.file}:{a.line_no}  (lines={a.body_lines}, tokens={a.ast_tokens})")
        print(f"     {b.file}:{b.line_no}  (lines={b.body_lines}, tokens={b.ast_tokens})")
        print()

    print(f"Total duplicate pairs: {len(duplicates)}")
    return 1 if duplicates else 0


if __name__ == "__main__":
    sys.exit(main())
