#!/usr/bin/env python3.12
"""Promote knowledge items from pending/ to formal domains in global KB.

This CLI tool implements the human confirmation step in the sedimentation mechanism:
- Interactive mode (no args): List pending candidates for review
- Command mode: Promote specific file to target domain

Usage:
    memory-promote                                    # Interactive mode
    memory-promote <file> --to operations             # Command mode
    memory-promote --help                             # Show help
    memory-promote --version                          # Show version

The tool moves files from ~/.memory/global-kb/pending/ to one of:
- operations/
- engineering/
- collaboration/

After promotion, INDEX.md is updated to reflect the new location.
"""

import argparse
import logging
import sys
from pathlib import Path

from memory_core.constants import CURRENT_MEMORY_VERSION

logger = logging.getLogger(__name__)

try:
    from .global_kb_init import get_global_kb_root
except ImportError:
    from memory_core.tools.global_kb_init import get_global_kb_root


# Valid target domains for promotion
VALID_DOMAINS = ("operations", "engineering", "collaboration")


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for memory-promote CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        prog="memory-promote",
        description="Promote knowledge items from pending/ to formal domains in global KB.",
        epilog="Examples:\n"
        "  memory-promote                                    # List pending candidates\n"
        "  memory-promote <file> --to operations             # Promote to operations domain\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "file",
        nargs="?",
        help="Path to file in pending/ directory to promote",
    )
    parser.add_argument(
        "--to",
        dest="domain",
        choices=VALID_DOMAINS,
        help="Target domain: operations, engineering, or collaboration",
    )
    parser.add_argument(
        "--global-kb-root",
        type=Path,
        default=None,
        help="Custom global KB root path (default: ~/.memory/global-kb)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {CURRENT_MEMORY_VERSION}",
    )

    args = parser.parse_args(argv)

    # Determine global KB root
    global_kb_root = args.global_kb_root or get_global_kb_root()

    pending_dir = global_kb_root / "pending"

    # Interactive mode: no file argument
    if args.file is None:
        return _interactive_mode(pending_dir)

    # Command mode: file argument provided
    if args.domain is None:
        parser.error("--to is required when specifying a file")

    return _command_mode(
        file_path=Path(args.file),
        domain=args.domain,
        pending_dir=pending_dir,
        global_kb_root=global_kb_root,
    )


def _interactive_mode(pending_dir: Path) -> int:
    """
    Interactive mode: list pending candidates.

    Args:
        pending_dir: Path to pending/ directory

    Returns:
        Exit code (0 for success)
    """
    if not pending_dir.exists():
        print(f"Error: pending directory does not exist: {pending_dir}", file=sys.stderr)
        return 1

    # List all files in pending/ (excluding README.md)
    candidates = [f for f in pending_dir.iterdir() if f.is_file() and f.name != "README.md"]

    if not candidates:
        print("无候选知识点 (No pending candidates)")
        print("\npending/ 目录为空。当项目产生新知识并触发 session-end 时,候选内容会自动出现在这里。")
        return 0

    print(f"待确认知识点 ({len(candidates)} 个):")
    print()
    for i, candidate in enumerate(candidates, 1):
        print(f"{i}. {candidate.name}")
        # Try to read first line as title
        try:
            with candidate.open(encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("# "):
                    print(f"   {first_line}")
                elif first_line:
                    print(f"   {first_line[:80]}")
        except Exception as exc:
            logger.debug("promote_global_kb._interactive_mode: reading candidate file failed: %s", exc)
        print()

    print("使用以下命令提升到指定域:")
    print("  memory-promote <file> --to operations|engineering|collaboration")
    return 0


def _command_mode(
    file_path: Path,
    domain: str,
    pending_dir: Path,
    global_kb_root: Path,
) -> int:
    """
    Command mode: promote file to target domain.

    Args:
        file_path: Path to file to promote
        domain: Target domain (operations, engineering, collaboration)
        pending_dir: Path to pending/ directory
        global_kb_root: Path to global KB root

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Validate domain
    if domain not in VALID_DOMAINS:
        print(
            f"Error: invalid domain '{domain}'. Must be one of: {', '.join(VALID_DOMAINS)}",
            file=sys.stderr,
        )
        return 1

    # Check file exists
    if not file_path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        return 1

    # Check file is in pending/
    try:
        file_path.relative_to(pending_dir)
    except ValueError:
        print(
            f"Error: file must be in pending/ directory: {file_path}",
            file=sys.stderr,
        )
        return 1

    # Target directory
    target_dir = global_kb_root / domain
    if not target_dir.exists():
        print(f"Error: target domain directory does not exist: {target_dir}", file=sys.stderr)
        return 1

    # Move file
    target_path = target_dir / file_path.name
    try:
        file_path.rename(target_path)
        print(f"✓ 已提升: {file_path.name} → {domain}/")
    except Exception as e:
        print(f"Error: failed to move file: {e}", file=sys.stderr)
        return 1

    # Update INDEX.md
    updated = _update_index(global_kb_root, domain, file_path.name)
    if updated:
        print("✓ INDEX.md 已更新")
    else:
        print(
            "⚠ 警告: INDEX.md 未更新（格式不匹配：既非表格格式也非 marker 格式）",
            file=sys.stderr,
        )

    return 0


def _update_index(global_kb_root: Path, domain: str, filename: str) -> bool:
    """
    Update INDEX.md to reflect promoted file.

    支持两种格式：
    - 表格格式（sediment 默认产物：``| 标题 | 域 | 文件 |``）→ 追加表格行
    - marker 格式（生产 global_kb_init 产物：``### [domain/](./domain/)``）→ 追加 bullet

    Returns:
        True 表示成功更新；False 表示 no-op（INDEX 不存在或格式不匹配）。
    """
    index_path = global_kb_root / "INDEX.md"
    if not index_path.exists():
        return False

    content = index_path.read_text(encoding="utf-8")

    # ---------- 路径 A：表格格式 ----------
    if _is_table_format_index(content):
        return _append_table_row(index_path, content, global_kb_root, domain, filename)

    # ---------- 路径 B：marker 格式（既有行为）----------
    return _append_marker_bullet(index_path, content, domain, filename)


def _is_table_format_index(content: str) -> bool:
    """检测 INDEX.md 是否为 sediment 产出的表格格式。"""
    return "| 标题 | 域 | 文件 |" in content or ("| title |" in content.lower() and "| file |" in content.lower())


def _append_table_row(
    index_path: Path,
    content: str,
    global_kb_root: Path,
    domain: str,
    filename: str,
) -> bool:
    """向表格格式 INDEX 追加 ``| title | domain | file |`` 行。"""
    file_rel = f"{domain}/{filename}"
    # 幂等：已存在则跳过（仍视为成功）
    if file_rel in content or filename in content:
        return True

    # 从文件 frontmatter 读取 title；读取失败则退化为 filename
    title = _read_title_from_file(global_kb_root / domain / filename) or filename

    # 转义标题中的竖线，防止破坏表格格式
    title_escaped = title.replace("|", "\\|")

    new_line = f"| {title_escaped} | {domain} | {file_rel} |"
    new_content = content if content.endswith("\n") else content + "\n"
    new_content += new_line + "\n"
    try:
        index_path.write_text(new_content, encoding="utf-8")
    except OSError as e:
        print(f"Warning: failed to write INDEX.md: {e}", file=sys.stderr)
        return False
    return True


def _read_title_from_file(file_path: Path) -> str | None:
    """从文件 frontmatter 的 title 字段或首个 # H1 读取标题。"""
    if not file_path.exists():
        return None
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    # 优先 frontmatter 的 title
    import re as _re

    fm = _re.match(r"^---\n(.*?)\n---\n?", text, flags=_re.DOTALL)
    if fm:
        for line in fm.group(1).split("\n"):
            stripped = line.strip()
            if stripped.startswith("title:"):
                _, _, value = stripped.partition(":")
                value = value.strip().strip('"').strip("'")
                if value:
                    return value
    # 退化：首个 # H1
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def _append_marker_bullet(index_path: Path, content: str, domain: str, filename: str) -> bool:
    """向 marker 格式 INDEX 追加 ``- [filename](...)`` bullet（既有行为）。"""
    domain_marker = f"### [{domain}/](./{domain}/)"
    if domain_marker not in content:
        return False

    lines = content.split("\n")
    new_lines: list[str] = []
    in_domain_section = False
    added = False

    for line in lines:
        new_lines.append(line)
        if domain_marker in line:
            in_domain_section = True
        elif in_domain_section and line.startswith("### "):
            if not added:
                new_lines.insert(-1, f"- [{filename}](./{domain}/{filename})")
                added = True
            in_domain_section = False

    if not added and in_domain_section:
        new_lines.append(f"- [{filename}](./{domain}/{filename})")

    try:
        index_path.write_text("\n".join(new_lines), encoding="utf-8")
    except OSError as e:
        print(f"Warning: failed to write INDEX.md: {e}", file=sys.stderr)
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
