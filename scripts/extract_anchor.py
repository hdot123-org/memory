#!/usr/bin/env python3
"""Extract linear-linkback anchor (INFRA-xxx) from GitHub issue/PR comments.

CLI wrapper for evolution_utils.extract_linkback_anchor().
Used by reconcile-evolution.sh and trigger-droid.sh for anchor-based mirror location.

Usage:
    extract_anchor.py issue <number> <repo>
    extract_anchor.py pr <number> <repo>

Returns:
    INFRA-xxx on success, empty string on no anchor found.
    Exit code 0 always (empty output = no anchor).
    Exit code 1 on gh CLI failure (fail-closed signal).

Architecture reference: docs/architecture/issue-flow.md §9.4/§10.3（镜像定位锚点）
"""

import subprocess
import sys
from pathlib import Path

# Add scripts/ to path so we can import evolution_utils
SCRIPT_DIR = str(Path(__file__).resolve().parent)
sys.path.insert(0, SCRIPT_DIR)

from evolution_utils import extract_linkback_anchor


def fetch_comments(target_type: str, number: str, repo: str) -> tuple[int, str]:
    """Fetch comments from GitHub issue or PR.

    Returns:
        (exit_code, comments_text)
        exit_code: 0=success, 1=gh failure
        comments_text: joined comment bodies, or empty string
    """
    if target_type == "issue":
        cmd = ["gh", "issue", "view", number, "--repo", repo, "--json", "comments", "--jq", ".comments[].body"]
    elif target_type == "pr":
        cmd = ["gh", "pr", "view", number, "--repo", repo, "--json", "comments", "--jq", ".comments[].body"]
    else:
        print(f"Error: unknown target type '{target_type}'", file=sys.stderr)
        return 1, ""

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"gh error: {result.stderr.strip()}", file=sys.stderr)
            return 1, ""
        return 0, result.stdout
    except subprocess.TimeoutExpired:
        print("gh timeout", file=sys.stderr)
        return 1, ""
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1, ""


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <issue|pr> <number> <repo>", file=sys.stderr)
        sys.exit(1)

    target_type = sys.argv[1]
    number = sys.argv[2]
    repo = sys.argv[3]

    if target_type not in ("issue", "pr"):
        print(f"Error: first arg must be 'issue' or 'pr', got '{target_type}'", file=sys.stderr)
        sys.exit(1)

    exit_code, comments_text = fetch_comments(target_type, number, repo)
    if exit_code != 0:
        # gh failure -> exit 1 (fail-closed signal to caller)
        sys.exit(1)

    anchor = extract_linkback_anchor(comments_text)
    if anchor:
        print(anchor)
    # else: print nothing (empty output = no anchor found)
    sys.exit(0)


if __name__ == "__main__":
    main()
