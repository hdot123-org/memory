"""Shared drift-watch test issue factories (INFRA-415 dedup).

INFRA-415: ``_make_issue`` had 100% AST similarity across 2 test files
(test_drift_watch_reverse, test_drift_watch_reverse_integration) — 7 lines /
68 tokens each — plus a superset variant with a ``category`` field in
test_drift_watch_reverse_safety_guards (triggering CODE_HYGIENE_DUPLICATE_BLOCK).

All variants are folded into a single ``make_issue`` factory. Test modules
import it under their original local names (``_make_issue``) so existing call
sites stay unchanged.
"""

from __future__ import annotations


def make_issue(
    number: int,
    rule_id: str,
    location: str,
    linear_linkback: str = "",
    deadlock_sentinel: str = "",
    category: str = "",
) -> dict:
    """Create a test issue with optional category, Linear linkback and deadlock sentinel.

    INFRA-415: extracted from the 100%-identical ``_make_issue`` bodies in
    test_drift_watch_reverse / test_drift_watch_reverse_integration (7 lines /
    68 tokens each), extended with the optional ``category`` field from the
    safety-guards superset variant.

    Args:
        number: GitHub issue number.
        rule_id: Evolution rule identifier (e.g. ``RULE_001``).
        location: Finding location string (e.g. ``file1.py``).
        linear_linkback: Optional Linear issue ID embedded as a
            ``<!-- linear-linkback ... -->`` marker.
        deadlock_sentinel: Optional raw sentinel line appended to the body.
        category: Optional category line (e.g. ``evolution_self_audit``).

    Returns:
        Compact issue dict ``{"number": ..., "body": ...}``.
    """
    body = f"**Rule ID**: {rule_id}\n**Location**: {location}"
    if category:
        body += f"\n**Category**: {category}"
    if linear_linkback:
        body += f"\n<!-- linear-linkback {linear_linkback} -->"
    if deadlock_sentinel:
        body += f"\n{deadlock_sentinel}"
    return {"number": number, "body": body}
