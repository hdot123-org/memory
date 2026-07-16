#!/usr/bin/env python3
"""M4: Re-sign CLI — Explicit integrity re-sign with audit trail.

Usage:
    python -m memory_core.tools.memory_integrity_resign \
        --project-root /path/to/project \
        --reason "description of why re-sign is needed" \
        [--strict] \
        [--token APPROVED-TOKEN]

Workflow:
    1. Parse args and validate project root
    2. If --strict: verify first, show diff of any errors
    3. Require --reason (mandatory) + --token or --force flag
    4. Write audit entry to memory/system/integrity-audit.jsonl
    5. Sign v2 manifest

Constraints:
    --reason is always required (non-empty string)
    --token or --force is required (prevents accidental re-sign)
    Source repo: refuses to re-sign (zero side-effects)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from memory_core.constants import SYSTEM_DIR

# Import now_iso utility (REF-001 §4.8)
try:
    from ._file_utils import now_iso as _now_iso
except ImportError:
    from _file_utils import now_iso as _now_iso  # type: ignore


def _is_source_repo(project_root: Path) -> bool:
    """Check if this is the memory-core source repo."""
    try:
        from memory_core.ownership import is_memory_core_source_repo

        return is_memory_core_source_repo(project_root)
    except ImportError:
        return False


def _load_key() -> bytes | None:
    """Load the integrity signing key."""
    try:
        from memory_core.tools.memory_hook_integrity_keys import load_key

        return load_key()
    except ImportError:
        return None


def _verify_project(project_root: Path, key: bytes) -> dict[str, Any] | None:
    """Verify current manifest and return result dict."""
    try:
        from memory_core.tools.memory_hook_integrity_verify import verify_project

        result = verify_project(project_root, key)
        return result.to_dict()
    except Exception as exc:
        return {"ok": False, "errors": [{"kind": "verify_exception", "detail": str(exc)}]}


def _sign_project(
    project_root: Path,
    key: bytes,
    *,
    include_runtime: bool = False,
) -> dict[str, Any] | None:
    """Sign the project and return manifest dict."""
    try:
        from memory_core.tools.memory_hook_integrity_manifest import sign_project

        return sign_project(project_root, key, include_runtime=include_runtime)
    except Exception as exc:
        print(f"[resign] sign failed: {exc}", file=sys.stderr)
        return None


def _write_audit(
    project_root: Path,
    *,
    reason: str,
    token: str | None,
    force: bool,
    verify_result: dict[str, Any] | None,
    manifest_result: dict[str, Any] | None,
) -> bool:
    """Write an audit entry to memory/system/integrity-audit.jsonl.

    Returns True on success.
    """
    audit_path = project_root / SYSTEM_DIR / "integrity-audit.jsonl"
    entry = {
        "timestamp": _now_iso(),
        "action": "resign",
        "reason": reason,
        "token_provided": token is not None,
        "force_used": force,
        "verify_ok": verify_result.get("ok") if verify_result else None,
        "verify_errors": verify_result.get("errors", []) if verify_result else [],
        "manifest_entry_count": manifest_result.get("entry_count") if manifest_result else None,
        "manifest_schema": manifest_result.get("schema_version") if manifest_result else None,
    }

    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except OSError as exc:
        print(f"[resign] audit write failed: {exc}", file=sys.stderr)
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Re-sign project integrity manifest with audit trail (M4).",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="Absolute path to project root",
    )
    parser.add_argument(
        "--reason",
        type=str,
        required=True,
        help="Mandatory: description of why re-sign is needed",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Approval token for re-sign",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force re-sign without token (requires explicit --force flag)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Verify before re-sign; show diff if errors found",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would happen without making changes",
    )
    parser.add_argument(
        "--include-runtime",
        action="store_true",
        default=False,
        help="Include runtime artifact paths (memory/artifacts/memory-hook/) in signing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()

    # Validate project root exists
    if not project_root.is_dir():
        print(f"[resign] project root does not exist: {project_root}", file=sys.stderr)
        return 1

    # Refuse source repo
    if _is_source_repo(project_root):
        print("[resign] cannot re-sign memory-core source repo (zero side-effects)", file=sys.stderr)
        return 1

    # Validate reason
    if not args.reason or not args.reason.strip():
        print("[resign] --reason is required and must be non-empty", file=sys.stderr)
        return 1

    # Require token or force
    if not args.token and not args.force:
        print("[resign] --token or --force is required for re-sign", file=sys.stderr)
        return 1

    # Load key
    key = _load_key()
    if key is None:
        print("[resign] no integrity key found; run sign first", file=sys.stderr)
        return 1

    # Strict mode: verify first and show diff
    verify_result: dict[str, Any] | None = None
    if args.strict:
        verify_result = _verify_project(project_root, key)
        if verify_result and not verify_result.get("ok", True):
            errors = verify_result.get("errors", [])
            print(f"[resign] verify found {len(errors)} error(s):", file=sys.stderr)
            for err in errors:
                print(
                    f"  - {err.get('rel_path', '')}: {err.get('kind', '')}: {err.get('detail', '')}",
                    file=sys.stderr,
                )
            if not args.force and not args.token:
                print("[resign] use --force or --token to proceed despite errors", file=sys.stderr)
                return 1

    if args.dry_run:
        print("[resign] dry-run: would re-sign with:")
        print(f"  reason: {args.reason}")
        print(f"  token_provided: {args.token is not None}")
        print(f"  force: {args.force}")
        if verify_result:
            print(f"  verify_ok: {verify_result.get('ok')}")
            print(f"  verify_errors: {len(verify_result.get('errors', []))}")
        return 0

    # Write audit trail
    audit_ok = _write_audit(
        project_root,
        reason=args.reason,
        token=args.token,
        force=args.force,
        verify_result=verify_result,
        manifest_result=None,  # Updated after sign
    )
    if not audit_ok:
        print("[resign] audit write failed, aborting", file=sys.stderr)
        return 1

    # Sign v2 manifest
    manifest = _sign_project(project_root, key, include_runtime=args.include_runtime)
    if manifest is None:
        print("[resign] sign failed", file=sys.stderr)
        return 1

    print(f"[resign] signed {manifest.get('entry_count', 0)} entries")
    print(f"[resign] schema: {manifest.get('schema_version', 'unknown')}")
    print(f"[resign] ownership_digest: {manifest.get('ownership_digest', 'none')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
