#!/usr/bin/env python3
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
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from memory_core.constants import CURRENT_MEMORY_VERSION

try:
    from .global_kb_init import get_global_kb_root
except ImportError:
    from memory_core.tools.global_kb_init import get_global_kb_root


# Valid target domains for promotion
VALID_DOMAINS = ("operations", "engineering", "collaboration")


def main(argv: List[str] | None = None) -> int:
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
    if args.global_kb_root:
        global_kb_root = args.global_kb_root
    else:
        global_kb_root = get_global_kb_root()

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
    candidates = [
        f for f in pending_dir.iterdir()
        if f.is_file() and f.name != "README.md"
    ]

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
            with open(candidate, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("# "):
                    print(f"   {first_line}")
                elif first_line:
                    print(f"   {first_line[:80]}")
        except Exception:
            pass
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
    try:
        _update_index(global_kb_root, domain, file_path.name)
        print("✓ INDEX.md 已更新")
    except Exception as e:
        print(f"Warning: failed to update INDEX.md: {e}", file=sys.stderr)
        # Non-fatal: file was moved successfully

    return 0


def _update_index(global_kb_root: Path, domain: str, filename: str) -> None:
    """
    Update INDEX.md to reflect promoted file.

    Args:
        global_kb_root: Path to global KB root
        domain: Domain where file was promoted
        filename: Name of promoted file
    """
    index_path = global_kb_root / "INDEX.md"
    if not index_path.exists():
        return

    content = index_path.read_text(encoding="utf-8")

    # Add entry to domain section
    # Look for domain section and add file reference
    domain_marker = f"### [{domain}/](./{domain}/)"
    if domain_marker in content:
        # Add file entry after domain marker
        lines = content.split("\n")
        new_lines = []
        in_domain_section = False
        added = False

        for line in lines:
            new_lines.append(line)
            if domain_marker in line:
                in_domain_section = True
            elif in_domain_section and line.startswith("### "):
                # Reached next domain section, insert before it
                if not added:
                    new_lines.insert(-1, f"- [{filename}](./{domain}/{filename})")
                    added = True
                in_domain_section = False

        if not added and in_domain_section:
            # Domain section is last, append at end
            new_lines.append(f"- [{filename}](./{domain}/{filename})")

        index_path.write_text("\n".join(new_lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
