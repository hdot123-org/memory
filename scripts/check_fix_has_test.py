#!/usr/bin/env python3
"""Fix-has-test guard: enforces that bug fix commits include regression tests.

When a PR contains a fix:/hotfix:/bugfix: commit but no files under tests/
are changed, this guard blocks the merge (exit 1).

Usage:
    python scripts/check_fix_has_test.py                    # non-PR -> exit 0
    python scripts/check_fix_has_test.py --pr 42            # CI mode (gh API)
    python scripts/check_fix_has_test.py --base origin/main  # local mode (git)
    python scripts/check_fix_has_test.py --pr 42 --json     # JSON output

Exit codes:
    0 - clean (no fix commit, or fix includes tests, or exempted)
    1 - violation (fix commit without test files)
    2 - script error (gh/git unavailable, API failure)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# Matches: fix:, fix!:, fix(scope):, fix(scope)!:, hotfix:, bugfix:
FIX_PATTERN = re.compile(r"^(fix|hotfix|bugfix)(\(.+\))?!?:", re.IGNORECASE)
RELEASE_PLEASE_PATTERN = re.compile(r"^chore\(main\):\s*release", re.IGNORECASE)


def _run(
    cmd: list[str], *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command, raising on failure."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    )


def get_pr_data(pr_number: int) -> dict[str, Any]:
    """Fetch PR data via gh CLI with bounded retry on transient 5xx (TD-503-02)."""
    max_attempts = 3
    last_err = ""
    for attempt in range(1, max_attempts + 1):
        try:
            result = _run(
                ["gh", "pr", "view", str(pr_number), "--json", "commits,files,author"]
            )
            data: dict[str, Any] = json.loads(result.stdout)
            return data
        except FileNotFoundError:
            print(
                "Error: gh CLI not found. Install GitHub CLI or use --base for local mode.",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
        except json.JSONDecodeError as exc:
            print(f"Error: failed to parse gh output: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip()
            last_err = stderr
            # 仅对 GitHub API 瞬时故障（5xx/EOF/TLS）重试；非瞬时错误（如 404）直接失败
            transient = any(
                marker in stderr
                for marker in ("HTTP 503", "HTTP 502", "HTTP 500", "HTTP 429",
                               "unexpected EOF", "TLS handshake timeout")
            )
            if transient and attempt < max_attempts:
                wait = 10 * attempt
                print(
                    f"Transient GitHub API error (attempt {attempt}/{max_attempts}): "
                    f"{stderr}\nRetrying in {wait}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            print(f"Error: gh pr view failed: {stderr}", file=sys.stderr)
            raise SystemExit(2) from exc
    # 不可达兜底（mypy --strict 要求显式返回/退出路径）
    print(
        f"Error: gh pr view failed after {max_attempts} attempts: "
        f"{last_err}",
        file=sys.stderr,
    )
    raise SystemExit(2)


def get_local_data(base_ref: str, cwd: Path | None = None) -> dict[str, Any]:
    """Get commits and changed files from git."""
    try:
        log_result = _run(["git", "log", f"{base_ref}..HEAD", "--format=%s"], cwd=cwd)
        commits = [
            line for line in log_result.stdout.strip().split("\n") if line
        ]

        diff_result = _run(["git", "diff", "--name-only", base_ref], cwd=cwd)
        files = [
            line for line in diff_result.stdout.strip().split("\n") if line
        ]

        return {"commits": commits, "files": files, "author": ""}
    except subprocess.CalledProcessError as exc:
        print(f"Error: git command failed: {exc.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2) from exc
    except FileNotFoundError:
        print("Error: git not found.", file=sys.stderr)
        raise SystemExit(2) from None


def is_dependabot(author: str) -> bool:
    """Check if the PR author is Dependabot."""
    return "dependabot" in author.lower()


def is_release_please(commits: list[str]) -> bool:
    """Check if any commit is a release-please automated commit."""
    return any(RELEASE_PLEASE_PATTERN.match(c) for c in commits)


def is_docs_only(files: list[str]) -> bool:
    """Check if all changed files are documentation (.md)."""
    non_empty = [f for f in files if f]
    if not non_empty:
        return False
    return all(f.endswith(".md") for f in non_empty)


def has_fix_commit(commits: list[str]) -> str | None:
    """Return the first fix commit message, or None."""
    for c in commits:
        if FIX_PATTERN.match(c):
            return c
    return None


def has_test_files(files: list[str]) -> bool:
    """Check if any changed file is under tests/."""
    return any(f.startswith("tests/") for f in files if f)


def _extract_commits(data: dict[str, Any]) -> list[str]:
    """Extract commit message headlines from PR data."""
    raw = data.get("commits", [])
    if not raw:
        return []
    if isinstance(raw[0], dict):
        return [c.get("messageHeadline", "") for c in raw]
    return [str(c) for c in raw]


def _extract_files(data: dict[str, Any]) -> list[str]:
    """Extract file paths from PR data."""
    raw = data.get("files", [])
    if not raw:
        return []
    if isinstance(raw[0], dict):
        return [f.get("path", "") for f in raw]
    return [str(f) for f in raw]


def _extract_author(data: dict[str, Any]) -> str:
    """Extract author login from PR data."""
    author = data.get("author", "")
    if isinstance(author, dict):
        login: str = author.get("login", "")
        return login
    return str(author)


def _output_clean(as_json: bool) -> None:
    """Output clean (no violation) result."""
    if as_json:
        print(json.dumps({"violations": [], "count": 0}))


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix-has-test CI guard")
    parser.add_argument("--pr", type=int, default=None, help="PR number (CI mode)")
    parser.add_argument(
        "--base", default=None, help="Base ref for local mode (git diff)"
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    # Determine data source
    if args.pr is not None:
        # CI mode: use gh API
        data = get_pr_data(args.pr)
        commits = _extract_commits(data)
        files = _extract_files(data)
        author = _extract_author(data)
    elif args.base is not None:
        # Local mode: use git diff
        data = get_local_data(args.base, cwd=Path.cwd())
        commits = data["commits"]
        files = data["files"]
        author = ""
    else:
        # Non-PR context -> exempt (VAL-GUARD-008)
        _output_clean(args.json)
        return 0

    # Exemption checks
    if is_dependabot(author):
        _output_clean(args.json)
        return 0

    if is_release_please(commits):
        _output_clean(args.json)
        return 0

    if is_docs_only(files):
        _output_clean(args.json)
        return 0

    # Check for fix commit
    fix_commit = has_fix_commit(commits)
    if fix_commit is None:
        _output_clean(args.json)
        return 0

    # Check for test files
    if has_test_files(files):
        _output_clean(args.json)
        return 0

    # Violation!
    violation_msg = (
        f"Bug fix detected (commit: '{fix_commit}') but no test files "
        f"under tests/ were changed. "
        f"Add a regression test under tests/ to prevent recurrence."
    )
    violation = {"commit": fix_commit, "message": violation_msg}

    if args.json:
        print(json.dumps({"violations": [violation], "count": 1}))
    else:
        print("FIX-HAS-TEST GUARD: violation detected")
        print(f"  Bug fix commit: '{fix_commit}'")
        print("  No test files under tests/ were modified.")
        print("  Add a regression test under tests/ to prevent recurrence.")

    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"check_fix_has_test.py: error: {exc}", file=sys.stderr)
        sys.exit(2)
