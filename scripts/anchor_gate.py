#!/usr/bin/env python3
"""Anchor gate for compensation-layer GitHub Issue close (INFRA-357).

Reads gh issue list candidates JSON (``[{"number": N}, ...]``) from stdin,
extracts the linear-linkback anchor of each candidate issue (delegating to
extract_anchor.py, the same extraction path as reconcile §4b / GATE A),
and prints the number of the FIRST candidate whose anchor == target_ref.

All other outcomes print NOTHING and exit 0 (fail-closed: caller must
skip the close and leave it to reconcile-evolution.sh):
  - candidate has no anchor            -> drift "missing anchor"
  - candidate anchor != target_ref     -> drift "anchor mismatch (got X)"
  - extract_anchor.py failure (gh err) -> drift "anchor extract failed"

Failure/degradation trails (issue-flow.md §9.4.1):
  - anchor-extract.log : extractor stderr / nonzero rc, timestamped
  - anchor-drift.log   : every skipped close, §4b-compatible format

Usage:
    echo '<candidates_json>' | anchor_gate.py <target_ref> <repo> <log_dir>

Exit code: 0 for gate decisions (empty output = do not close);
           2 on invalid usage.

Architecture reference: docs/architecture/issue-flow.md §9.4/§9.4.1（INFRA-357）
"""
import json
import os
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Same resolution as GATE A 4.5/4.6 in trigger-droid.sh:
# repo layout  <root>/webhook-scripts/../scripts/extract_anchor.py
# prod layout  ~/.factory/webhook/scripts/../scripts/extract_anchor.py
EXTRACTOR = os.path.join(SCRIPT_DIR, "extract_anchor.py")

EXTRACT_TIMEOUT = 60  # extract_anchor.py has its own 30s gh timeout


def _ts_extract() -> str:
    """Timestamp for anchor-extract.log (GATE A 4.5 format)."""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _ts_drift() -> str:
    """Timestamp for anchor-drift.log (reconcile §4b format)."""
    return time.strftime("%Y-%d %H:%M:%S")


def log_extract_err(target: str, number: int, result: subprocess.CompletedProcess[str]) -> None:
    """Record extractor failure to anchor-extract.log (best effort)."""
    if result.returncode == 0 and not (result.stderr or "").strip():
        return
    try:
        with open(_extract_log_path, "a") as f:
            err = (result.stderr or "").strip().replace("\n", " | ")[:500]
            f.write(
                f"[{_ts_extract()}] anchor-extract {target}#{number} "
                f"rc={result.returncode}: {err}\n"
            )
    except Exception as exc:
        # INFRA-359: never silently swallow the log failure -- warn on
        # stderr, but keep it best effort so the gate decision is unchanged.
        print(
            f"anchor_gate: extract log write failed ({target}#{number} "
            f"rc={result.returncode}): {exc}",
            file=sys.stderr,
        )


def log_drift(target_ref: str, number: int, reason: str) -> None:
    """Record a skipped close to anchor-drift.log, §4b format (best effort)."""
    try:
        with open(_drift_log_path, "a") as f:
            f.write(
                f"[{_ts_drift()}] DRIFT: {target_ref} GitHub Issue #{number} {reason}\n"
            )
    except Exception as exc:
        # INFRA-359: never silently swallow the log failure -- warn on
        # stderr, but keep it best effort so the gate decision is unchanged.
        print(
            f"anchor_gate: drift log write failed ({target_ref} GitHub Issue "
            f"#{number} {reason}): {exc}",
            file=sys.stderr,
        )


def extract_anchor(target: str, number: int, repo: str) -> tuple[int, str]:
    """Run extract_anchor.py for one candidate. Returns (rc, anchor)."""
    try:
        result = subprocess.run(
            [sys.executable, EXTRACTOR, target, str(number), repo],
            capture_output=True,
            text=True,
            timeout=EXTRACT_TIMEOUT,
        )
    except Exception:
        return 1, ""
    log_extract_err(target, number, result)
    return result.returncode, result.stdout.strip()


def gate(candidates_json: str, target_ref: str, repo: str, log_dir: str) -> str:
    """Return the issue number to close, or '' (fail-closed)."""
    global _extract_log_path, _drift_log_path
    _extract_log_path = os.path.join(log_dir, "anchor-extract.log")
    _drift_log_path = os.path.join(log_dir, "anchor-drift.log")

    try:
        candidates = json.loads(candidates_json) if candidates_json.strip() else []
    except Exception:
        candidates = []
    if not isinstance(candidates, list):
        candidates = []

    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        number = cand.get("number")
        if not number:
            continue

        rc, anchor = extract_anchor("issue", number, repo)
        if rc != 0:
            # gh failure -> fail-closed, no close, drift trail
            log_drift(target_ref, number, f"anchor extract failed (rc={rc})")
            continue
        if anchor == target_ref:
            return str(number)
        if not anchor:
            log_drift(target_ref, number, "missing anchor")
        else:
            log_drift(target_ref, number, f"anchor mismatch (got {anchor})")

    return ""


def main() -> None:
    if len(sys.argv) != 4:
        print(
            f"Usage: {sys.argv[0]} <target_ref> <repo> <log_dir>  (candidates JSON on stdin)",
            file=sys.stderr,
        )
        sys.exit(2)

    target_ref, repo, log_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    if not os.path.isdir(log_dir):
        print(f"Error: log_dir not found: {log_dir}", file=sys.stderr)
        sys.exit(2)

    candidates_json = sys.stdin.read()
    matched = gate(candidates_json, target_ref, repo, log_dir)
    if matched:
        print(matched)
    # else: print nothing (empty output = do not close, fail-closed)
    sys.exit(0)


# Module-level log paths (set by gate(); module state keeps the CLI thin
# and the small logging helpers testable).
_extract_log_path = os.devnull
_drift_log_path = os.devnull

if __name__ == "__main__":
    main()
