"""Shared drift-watch test helpers (INFRA-407 dedup).

INFRA-407: Function '_make_issue' had 89% AST similarity across test files
(test_drift_watch_reverse_safety_guards vs test_drift_watch_reverse_integration,
plus an identical variant in test_drift_watch_reverse). All variants built a
scanner-style issue dict with optional Linear linkback / deadlock sentinel /
category body fields.

Consolidated into a single superset helper; each test module imports it under
its historical local name via aliased import, so existing call sites stay
unchanged. With ``category=""`` (the default) the generated body is identical
to the plain variants, so tests keep their historical assertions.
"""

from __future__ import annotations


def make_issue(number: int, rule_id: str, location: str,
               linear_linkback: str = "", deadlock_sentinel: str = "",
               category: str = "") -> dict:
    """Create a test issue with optional category, Linear linkback and deadlock sentinel.

    INFRA-407: extracted from 3 near-identical _make_issue bodies. Builds the
    issue body the same way the evolution scanner formats findings, so the
    reverse drift watch parser sees realistic input.
    """
    body = f"**Rule ID**: {rule_id}\n**Location**: {location}"
    if category:
        body += f"\n**Category**: {category}"
    if linear_linkback:
        body += f"\n<!-- linear-linkback {linear_linkback} -->"
    if deadlock_sentinel:
        body += f"\n{deadlock_sentinel}"
    return {"number": number, "body": body}
