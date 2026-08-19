"""Shared drift-watch test helpers (INFRA-404/406/407 dedup).

Three test files (test_drift_watch_reverse.py, test_drift_watch_reverse_integration.py,
test_drift_watch_reverse_safety_guards.py) contained near-identical ``_make_issue``
helpers with 89-100% AST similarity.  This module provides a single superset helper;
each test module imports it under its historical local name via aliased import,
so existing call sites stay unchanged.

Body field ordering (Rule ID, Location, Category, linkback, sentinel) preserves
each historical variant byte-for-byte, so tests keep their existing assertions.

Supersedes PR #820 (INFRA-404/406, Fixes #818/#821) and
PR #823 (INFRA-407, Fixes #822).
"""

from __future__ import annotations


def make_issue(number: int, rule_id: str, location: str,
               linear_linkback: str = "", deadlock_sentinel: str = "",
               category: str = "") -> dict:
    """Create a test issue dict with optional fields.

    Builds the scanner-format issue body: Rule ID + Location,
    plus optional Category, Linear linkback comment, and deadlock sentinel.
    """
    body = f"**Rule ID**: {rule_id}\n**Location**: {location}"
    if category:
        body += f"\n**Category**: {category}"
    if linear_linkback:
        body += f"\n<!-- linear-linkback {linear_linkback} -->"
    if deadlock_sentinel:
        body += f"\n{deadlock_sentinel}"
    return {"number": number, "body": body}
