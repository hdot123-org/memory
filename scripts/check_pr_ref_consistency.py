#!/usr/bin/env python3
"""PR reference consistency check (VAL-GATE-201/202/204).

Checks that for a given PR, the set of Linear INFRA IDs extracted from
linkback comments of all referenced GitHub issues is a subset of the
INFRA IDs declared in the PR body's "Fixes INFRA-xxx" lines.

Direction: linkback ⊆ Fixes (architecture §3.5)
- Mismatch (linkback has items not in Fixes) → exit non-zero
- Compliant (linkback ⊆ Fixes) → exit 0
- No linkback → exit 0 (backward compat)
- No closing refs → exit 0 (nothing to check)

Strictly read-only: only issues gh pr view and gh issue view commands.

Usage:
    python3 scripts/check_pr_ref_consistency.py <PR_NUMBER>
"""
import json
import re
import subprocess
import sys
from typing import Any, cast


def extract_fixes_infra_ids(pr_body: str) -> set[str]:
    """Extract INFRA-xxx IDs from 'Fixes/Closes/Resolves INFRA-xxx' lines in PR body.

    Supports GitHub's three equivalent keywords: Fixes, Closes, Resolves.
    Also supports comma-separated lists (e.g., "Fixes INFRA-100, INFRA-200").

    Args:
        pr_body: The PR body text

    Returns:
        Set of INFRA IDs (e.g., {"INFRA-335", "INFRA-337"})
    """
    if not pr_body:
        return set()

    # Find all keyword mentions and extract IDs after them
    # Supports: Fixes INFRA-100, Closes INFRA-200, Resolves INFRA-300
    # Also supports comma-separated: "Fixes INFRA-100, INFRA-200"
    keyword_pattern = r"(?:Fixes|Closes|Resolves)\s+((?:INFRA-\d+)(?:\s*,\s*INFRA-\d+)*)"
    matches = re.findall(keyword_pattern, pr_body, re.IGNORECASE)

    # Extract all INFRA-xxx IDs from each match
    ids = set()
    for match in matches:
        # Split comma-separated list and extract individual IDs
        id_pattern = r"INFRA-\d+"
        for infra_id in re.findall(id_pattern, match):
            ids.add(infra_id)

    return ids


def extract_linkback_from_comments(comments_text: str) -> str | None:
    """Extract INFRA-xxx ID from linear-linkback comment.

    Reuses the extraction logic from evolution_utils.extract_linkback_anchor().
    Searches for the linear-linkback marker and extracts the INFRA ID from
    the href or anchor text.

    Args:
        comments_text: Combined comment bodies from gh issue view

    Returns:
        INFRA-xxx ID if found, None otherwise
    """
    if not comments_text or "linear-linkback" not in comments_text:
        return None

    # Split into blocks (blank-line separated)
    blocks = []
    current: list[str] = []
    for line in comments_text.split("\n"):
        if line.strip() == "":
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))

    # Find first block containing "linear-linkback" marker
    linkback_block = None
    for block in blocks:
        if "linear-linkback" in block:
            linkback_block = block
            break

    if not linkback_block:
        return None

    # Tier 1: inline HTML comment format <!-- linear-linkback INFRA-xxx -->
    pattern = r'<!--\s*linear-linkback\s+(INFRA-\d+)\s*-->'
    match = re.search(pattern, linkback_block)
    if match:
        return match.group(1)

    # Tier 2a: href format (linear.app/OWNER/issue/INFRA-xxx)
    href_pattern = r'linear\.app/[^/\s"]+/issue/([A-Z]+-\d+)'
    match = re.search(href_pattern, linkback_block)
    if match:
        return match.group(1)

    # Tier 2b: anchor text (<a ...>INFRA-xxx</a>)
    anchor_pattern = r'<a[^>]*>\s*([A-Z]+-\d+)\s*</a>'
    match = re.search(anchor_pattern, linkback_block)
    if match:
        return match.group(1)

    return None


def fetch_pr_data(pr_number: int) -> dict[str, Any]:
    """Fetch PR body and closing issue references via gh CLI.

    Args:
        pr_number: GitHub PR number

    Returns:
        Dict with 'body' (str) and 'closingIssuesReferences' (list of dicts)
    """
    result = subprocess.run(
        [
            "gh", "pr", "view", str(pr_number),
            "--json", "body,closingIssuesReferences"
        ],
        capture_output=True,
        text=True,
        check=True
    )
    return cast(dict[str, Any], json.loads(result.stdout))


def fetch_issue_comments(issue_number: int) -> str:
    """Fetch issue comments via gh CLI.

    Args:
        issue_number: GitHub issue number

    Returns:
        Combined comment bodies as string
    """
    result = subprocess.run(
        [
            "gh", "issue", "view", str(issue_number),
            "--json", "comments",
            "--jq", ".comments[].body"
        ],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout


def main(args: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        args: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code (0 = pass, non-zero = fail)
    """
    if args is None:
        args = sys.argv[1:]

    if len(args) != 1:
        print("Usage: python3 scripts/check_pr_ref_consistency.py <PR_NUMBER>", file=sys.stderr)
        return 2

    try:
        pr_number = int(args[0])
    except ValueError:
        print(f"Error: PR number must be an integer, got '{args[0]}'", file=sys.stderr)
        return 2

    # Fetch PR data
    try:
        pr_data = fetch_pr_data(pr_number)
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to fetch PR #{pr_number}: {e.stderr}", file=sys.stderr)
        return 2

    pr_body = pr_data.get("body") or ""  # None body defense: convert None → ""
    closing_refs = pr_data.get("closingIssuesReferences", [])

    # No closing references → nothing to check
    if not closing_refs:
        print(f"PR #{pr_number}: No closing issue references, skipping check")
        return 0

    # Extract Fixes IDs from PR body
    fixes_ids = extract_fixes_infra_ids(pr_body)

    # Collect linkback IDs from all referenced issues
    linkback_ids = set()
    issue_numbers = [ref["number"] for ref in closing_refs]

    print(f"PR #{pr_number}: Checking {len(issue_numbers)} referenced issue(s): {issue_numbers}")
    print(f"PR #{pr_number}: Fixes set = {sorted(fixes_ids) if fixes_ids else '{}'}")

    for issue_num in issue_numbers:
        try:
            comments = fetch_issue_comments(issue_num)
            linkback = extract_linkback_from_comments(comments)
            if linkback:
                linkback_ids.add(linkback)
                print(f"  Issue #{issue_num}: linkback = {linkback}")
            else:
                print(f"  Issue #{issue_num}: no linkback (backward compat)")
        except subprocess.CalledProcessError as e:
            print(f"Error: Failed to fetch comments for issue #{issue_num}: {e.stderr}", file=sys.stderr)
            return 2

    # Check subset condition: linkback ⊆ Fixes
    print(f"PR #{pr_number}: Linkback set = {sorted(linkback_ids) if linkback_ids else '{}'}")

    missing_ids = linkback_ids - fixes_ids

    if missing_ids:
        print("\n❌ FAIL: Linkback set is NOT a subset of Fixes set")
        print(f"   Missing from Fixes: {sorted(missing_ids)}")
        print(f"   Linkback: {sorted(linkback_ids)}")
        print(f"   Fixes: {sorted(fixes_ids)}")
        return 1

    if linkback_ids:
        print("\n✅ PASS: Linkback set ⊆ Fixes set")
    else:
        print("\n✅ PASS: No linkbacks found (backward compat)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
