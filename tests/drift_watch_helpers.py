"""Shared helpers for drift watch tests (INFRA-404 dedup).

INFRA-404: function '_make_issue' had 100% AST similarity across
tests/test_drift_watch_reverse.py and tests/test_drift_watch_reverse_integration.py
(7 lines / 68 tokens each). A near-identical variant in
tests/test_drift_watch_reverse_safety_guards.py (extra optional ``category``
field) is covered by the same superset signature.

Consolidated into a single module-level helper; the test modules import it
under their historical local name via aliased import, so existing call sites
stay unchanged. Body field ordering (Rule ID, Location, Category, linkback,
sentinel) preserves each historical variant byte-for-byte.
"""

from __future__ import annotations


def make_issue(number: int, rule_id: str, location: str,
               linear_linkback: str = "", deadlock_sentinel: str = "",
               category: str = "") -> dict:
    """Create a test issue dict with optional fields.

    INFRA-404: extracted from identical '_make_issue' bodies (100% AST
    similarity). Builds the scanner-format issue body: Rule ID + Location,
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
