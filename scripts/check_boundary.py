#!/usr/bin/env python3
"""BOUNDARY 污染检查脚本。

按 docs/BOUNDARY.md 4.1（单一归属）/ 4.3（通用 vs 专用）扫描主仓库路径，
拒绝业务专属文件、SSH/IP/DSN 等运维信息回流到 memory-core 通用底座。

用法：
    python scripts/check_boundary.py
    python scripts/check_boundary.py --json   # 机器可读输出

退出码：
    0 — clean
    1 — 检测到违规
    2 — 脚本自身出错
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


# 主仓库路径下不应该出现的"业务专属"文件名前缀。
# 当确实需要接入一个新业务项目时，只允许通过 adapter runtime profile 引用，
# 不允许把业务专属知识/政策直接放到 memory_core/memory/kb/。
BUSINESS_PREFIX_PATTERNS: tuple[str, ...] = (
    "workbot-",
    "axonhub-",
    "AEdu-",
    "youzy-",
)

# 这些是历史业务项目的"项目真相"文件名，不允许放在 memory_core/memory/kb/projects/
BUSINESS_PROJECT_FILES: tuple[str, ...] = (
    "workbot.md",
    "axonhub.md",
    "AEdu.md",
    "youzy.md",
)

# 业务运维信息泄露关键词。命中即视为污染。
LEAK_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ce-01", r"\bce-01\b"),
    ("axonhub-ci", r"\baxonhub-ci\b"),
    ("axonhub-app", r"\baxonhub-app\b"),
    ("axonhub-postgres", r"\baxonhub-postgres\b"),
    ("private-ip-192.168.88", r"\b192\.168\.88\.\d{1,3}\b"),
    ("AXONHUB_DB_DSN", r"AXONHUB_DB_DSN\s*="),
)

# 检查这些路径下的文件名前缀。
KB_GLOBAL_DIR = REPO_ROOT / "memory_core" / "memory" / "kb" / "global"
KB_PROJECTS_DIR = REPO_ROOT / "memory_core" / "memory" / "kb" / "projects"

# 检查这些路径下的文件内容。其余路径（archive、docs/audit、RESIDUE_*）豁免。
LEAK_SCAN_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "memory_core",
    REPO_ROOT / "workspace",
    REPO_ROOT / "tests",
    REPO_ROOT / "scripts",
)

# 这些路径段出现在文件路径任意位置都豁免内容扫描。
EXEMPT_PATH_FRAGMENTS: tuple[str, ...] = (
    "archive/",
    "docs/audit/",
    "RESIDUE_INVENTORY.md",
    "RESIDUE_DISPOSITION_PLAN.md",
    "/__pycache__/",
    ".pyc",
    "/.git/",
    ".pytest_cache",
    ".ruff_cache",
    "memory_hook_adapters/workbot_runtime_profile.py",
    "scripts/check_boundary.py",
    "tests/test_boundary_guard.py",
)


def _is_exempt(path: Path) -> bool:
    s = str(path)
    return any(frag in s for frag in EXEMPT_PATH_FRAGMENTS)


def scan_business_kb_files() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if KB_GLOBAL_DIR.is_dir():
        for entry in KB_GLOBAL_DIR.iterdir():
            if not entry.is_file():
                continue
            for prefix in BUSINESS_PREFIX_PATTERNS:
                if entry.name.startswith(prefix):
                    findings.append({
                        "kind": "business-kb-prefix",
                        "path": str(entry.relative_to(REPO_ROOT)),
                        "matched": prefix,
                        "rule": "BOUNDARY 4.1: business-prefixed kb files must live in archive/legacy-<project>/kb/",
                    })
                    break
    if KB_PROJECTS_DIR.is_dir():
        for entry in KB_PROJECTS_DIR.iterdir():
            if not entry.is_file():
                continue
            if entry.name in BUSINESS_PROJECT_FILES:
                findings.append({
                    "kind": "business-project-file",
                    "path": str(entry.relative_to(REPO_ROOT)),
                    "matched": entry.name,
                    "rule": "BOUNDARY 4.1: per-project truth files belong in adapter runtime profile, not memory_core/memory/kb/projects/",
                })
    return findings


def scan_runtime_leaks() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    compiled = [(name, re.compile(rx)) for name, rx in LEAK_PATTERNS]
    for root in LEAK_SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if _is_exempt(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError, OSError):
                continue
            for name, regex in compiled:
                m = regex.search(text)
                if m:
                    line_no = text[: m.start()].count("\n") + 1
                    findings.append({
                        "kind": "runtime-leak",
                        "path": str(path.relative_to(REPO_ROOT)),
                        "line": str(line_no),
                        "matched": name,
                        "rule": "BOUNDARY 4.3: business runtime details (SSH alias / IP / DSN / deploy host) must not leak into core paths",
                    })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="memory-core BOUNDARY pollution guard")
    parser.add_argument("--json", action="store_true", help="Output findings as JSON")
    args = parser.parse_args()

    findings = scan_business_kb_files() + scan_runtime_leaks()

    if args.json:
        print(json.dumps({"findings": findings, "count": len(findings)}, ensure_ascii=False, indent=2))
    else:
        if not findings:
            print("BOUNDARY guard: clean (0 findings)")
        else:
            print(f"BOUNDARY guard: {len(findings)} finding(s)")
            for f in findings:
                loc = f"{f['path']}:{f.get('line', '-')}"
                print(f"  [{f['kind']}] {loc}  matched={f['matched']!r}")
                print(f"    rule: {f['rule']}")

    return 1 if findings else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover
        print(f"check_boundary.py: error: {exc}", file=sys.stderr)
        sys.exit(2)
