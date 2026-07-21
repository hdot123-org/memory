#!/usr/bin/env python3
"""文档分类校验脚本。

扫描 memory/docs/ 和 memory/kb/ 下所有文件，校验每个文件的父目录
在 DOC_CATEGORIES 路由表或例外列表中。不在则 exit 1。

参考 scripts/check_boundary.py 模式。

用法：
    python scripts/check_doc_classification.py
    python scripts/check_doc_classification.py --json

退出码：
    0 — clean（所有文件在注册目录或例外列表中）
    1 — 检测到未注册目录中的文件
    2 — 脚本自身出错
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Import routing table from doc_router
sys.path.insert(0, str(REPO_ROOT))
from memory_core.tools.doc_router import DOC_CATEGORIES, EXCEPTION_DIRS

# Directories to scan
SCAN_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "memory" / "docs",
    REPO_ROOT / "memory" / "kb",
)

# File name patterns to skip entirely
SKIP_FILES: frozenset[str] = frozenset({
    ".DS_Store",
})

# Specific files allowed at the top level of scan roots
TOP_LEVEL_EXCEPTIONS: frozenset[str] = frozenset({
    "memory/docs/INDEX.md",
    "memory/kb/INDEX.md",
})


def _is_in_registered_dir(file_path: Path) -> bool:
    """Check if a file is in a registered doc category or exception dir."""
    rel = str(file_path.relative_to(REPO_ROOT))
    rel_dir = str(file_path.parent.relative_to(REPO_ROOT)) + "/"

    # Top-level INDEX.md files in scan roots are allowed
    if rel in TOP_LEVEL_EXCEPTIONS:
        return True

    for cat_dir in DOC_CATEGORIES.values():
        if rel_dir.startswith(cat_dir):
            return True

    for exc_dir in EXCEPTION_DIRS:
        if rel_dir.startswith(exc_dir):
            return True

    return False


def scan_doc_classification() -> list[dict[str, str]]:
    """Scan memory/docs/ and memory/kb/ for files in unregistered directories."""
    findings: list[dict[str, str]] = []

    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.name in SKIP_FILES:
                continue
            if _is_in_registered_dir(path):
                continue
            findings.append({
                "kind": "unregistered-doc-dir",
                "path": str(path.relative_to(REPO_ROOT)),
                "rule": (
                    "File is not in any DOC_CATEGORIES directory or EXCEPTION_DIRS. "
                    "See memory_core/tools/doc_router.py for the routing table."
                ),
            })

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Document classification directory guard"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output findings as JSON"
    )
    args = parser.parse_args()

    findings = scan_doc_classification()

    if args.json:
        print(json.dumps(
            {"findings": findings, "count": len(findings)},
            ensure_ascii=False, indent=2,
        ))
    else:
        if not findings:
            print("doc classification guard: clean (0 findings)")
        else:
            print(f"doc classification guard: {len(findings)} finding(s)")
            for f in findings:
                print(f"  [{f['kind']}] {f['path']}")
                print(f"    rule: {f['rule']}")

    return 1 if findings else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover
        print(f"check_doc_classification.py: error: {exc}", file=sys.stderr)
        sys.exit(2)
