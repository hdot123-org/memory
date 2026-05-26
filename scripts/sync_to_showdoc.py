#!/usr/bin/env python3
"""GitLab CI → ShowDoc sync engine.

Reads ``.memory/adapter.toml`` ``[sync.showdoc]`` config, scans files matching
glob patterns, uses SHA256 manifest (``.showdoc-manifest.json``) for incremental
detection, calls ShowDoc Open API ``updateByApi`` with upsert semantics, derives
``cat_name`` from file path, validates Markdown safe subset, handles errors
per-file with retry, and outputs a structured sync report.

Usage::

    python scripts/sync_to_showdoc.py [--dry-run] [--verbose]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError as _exc:
    raise ImportError(
        "'requests' package is required for ShowDoc sync. "
        "Install with: pip install memory-core[dev]"
    ) from _exc

from memory_core.tools.adapter_toml_schema import load_showdoc_sync_config

# ---------------------------------------------------------------------------
# Markdown safe subset: ShowDoc↔飞书 19-item compat rules
# Unsafe patterns that cause validation failure:
# ---------------------------------------------------------------------------

_UNSAFE_PATTERNS = [
    # H1 heading (# at start of line, single hash) — H2-H6 are OK
    ("h1_heading", "H1 heading (# at line start) is not in the safe subset; use H2 (##) or deeper"),
    # Centered table alignment :---:
    ("table_center_align", "Center-aligned table columns (:---:) are not supported"),
    # [TOC] directive
    ("toc_directive", "[TOC] directive is not in the safe subset"),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config(adapter_path: str) -> dict[str, Any]:
    """Load [sync.showdoc] config from adapter.toml.

    Returns a dict with: enabled, item_id, api_url, core_files,
    extra_patterns, cat_name_mapping.

    Raises SystemExit if config is not enabled or file is missing.
    """
    path = Path(adapter_path)
    if not path.is_file():
        print(f"ERROR: adapter.toml not found at {adapter_path}", file=sys.stderr)
        sys.exit(1)

    config = load_showdoc_sync_config(path)

    if not config.enabled:
        print("ERROR: [sync.showdoc] is not enabled in adapter.toml", file=sys.stderr)
        sys.exit(1)

    return {
        "enabled": config.enabled,
        "item_id": config.item_id,
        "api_url": config.api_url,
        "core_files": config.core_files,
        "extra_patterns": config.extra_patterns,
        "cat_name_mapping": dict(config.cat_name_mapping),
    }


def scan_files(
    base_dir: str,
    core_files: list[str],
    extra_patterns: list[str] | None = None,
) -> list[Path]:
    """Scan for files matching glob patterns relative to base_dir.

    Returns a sorted list of Path objects for all matching files.
    """
    base = Path(base_dir)
    patterns = list(core_files)
    if extra_patterns:
        patterns.extend(extra_patterns)

    found: set[Path] = set()
    for pattern in patterns:
        # Use Path.glob for recursive patterns
        if "**" in pattern:
            for p in base.glob(pattern):
                if p.is_file():
                    found.add(p)
        else:
            p = base / pattern
            if p.is_file():
                found.add(p)

    return sorted(found)


def _file_sha256(file_path: Path) -> str:
    """Compute SHA256 hex digest of a file's content."""
    h = hashlib.sha256()
    h.update(file_path.read_bytes())
    return h.hexdigest()


def _load_manifest(manifest_path: str) -> dict[str, str]:
    """Load the SHA256 manifest from disk, or return empty dict."""
    p = Path(manifest_path)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def compute_changed(
    files: list[Path],
    manifest_path: str,
) -> list[Path]:
    """Return files whose SHA256 hash differs from the manifest.

    If manifest doesn't exist, all files are considered changed.
    """
    manifest = _load_manifest(manifest_path)
    changed: list[Path] = []

    for f in files:
        current_hash = _file_sha256(f)
        stored_hash = manifest.get(str(f))
        if stored_hash != current_hash:
            changed.append(f)

    return changed


def update_manifest(files: list[Path], manifest_path: str) -> None:
    """Update the manifest with SHA256 hashes for the given files."""
    manifest = _load_manifest(manifest_path)
    for f in files:
        manifest[str(f)] = _file_sha256(f)

    p = Path(manifest_path)
    p.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def derive_page_title(file_path: str) -> str:
    """Derive page_title from file path (filename without extension).

    e.g., memory_core/memory/docs/design/01-architecture.md -> "01-architecture"
    """
    return Path(file_path).stem


def derive_cat_name(
    file_path: str,
    cat_name_mapping: dict[str, str],
    default_cat_name: str,
) -> str:
    """Derive cat_name from file path using configurable mapping.

    Uses longest-prefix matching: the longest key in the mapping that
    matches the beginning of the file path wins.
    """
    best_match: str | None = None
    best_len = 0

    for prefix, cat_name in cat_name_mapping.items():
        if file_path.startswith(prefix) and len(prefix) > best_len:
            best_match = cat_name
            best_len = len(prefix)

    return best_match if best_match else default_cat_name


def validate_markdown(content: str) -> tuple[bool, list[str]]:
    """Validate Markdown content against the ShowDoc safe subset.

    Returns (is_valid, list_of_reasons).
    """
    reasons: list[str] = []

    for pattern_id, message in _UNSAFE_PATTERNS:
        if pattern_id == "h1_heading":
            # Check for H1: lines starting with single # (not ##+)
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("#") and not stripped.startswith("##"):
                    reasons.append(message)
                    break
        elif pattern_id == "table_center_align":
            if ":---:" in content:
                reasons.append(message)
        elif pattern_id == "toc_directive":
            if "[TOC]" in content:
                reasons.append(message)

    return (len(reasons) == 0, reasons)


def sync_file(
    api_url: str,
    api_key: str,
    api_token: str,
    item_id: int,
    file_path: str,
    file_content: str,
    page_title: str,
    cat_name: str,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Sync a single file to ShowDoc via the updateByApi endpoint.

    Retries up to max_retries times with exponential backoff on transient errors.

    Returns dict with 'success' and optional 'error' / 'retries'.
    """
    endpoint = f"{api_url}/server/index.php?s=/api/item/updateByApi"
    params = {
        "api_key": api_key,
        "api_token": api_token,
        "page_title": page_title,
        "page_content": file_content,
        "cat_name": cat_name,
    }

    last_error = ""
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(endpoint, params=params, timeout=30)
            data = resp.json()

            if data.get("error_code") == 0:
                return {"success": True}

            last_error = data.get("error_message", f"API error: {resp.status_code}")
            # Non-transient auth errors should not be retried
            if data.get("error_code") in (10201, 10202, 10301):
                return {"success": False, "error": last_error}

        except requests.RequestException as exc:
            last_error = str(exc)

        # Exponential backoff: 5s, 15s, 30s
        if attempt < max_retries:
            backoff = min(5 * (3 ** (attempt - 1)), 30)
            time.sleep(backoff)

    return {"success": False, "error": last_error, "retries": max_retries}


def resolve_auth(config_api_url: str) -> tuple[str, str, str]:
    """Resolve ShowDoc URL, API key, and token.

    - api_url: uses config value if set, otherwise SHOWDOC_URL env var
    - api_key: always from SHOWDOC_API_KEY env var
    - api_token: always from SHOWDOC_API_TOKEN env var
    """
    api_url = config_api_url if config_api_url else os.environ.get("SHOWDOC_URL", "")
    api_key = os.environ.get("SHOWDOC_API_KEY", "")
    api_token = os.environ.get("SHOWDOC_API_TOKEN", "")

    if not api_url:
        print("ERROR: SHOWDOC_URL not set and api_url is empty in config", file=sys.stderr)
        sys.exit(1)
    if not api_key:
        print("ERROR: SHOWDOC_API_KEY environment variable is not set", file=sys.stderr)
        sys.exit(1)
    if not api_token:
        print("ERROR: SHOWDOC_API_TOKEN environment variable is not set", file=sys.stderr)
        sys.exit(1)

    return api_url, api_key, api_token


def sync_files(
    files: list[Path],
    api_url: str,
    api_key: str,
    api_token: str,
    item_id: int,
    base_dir: str,
    cat_name_mapping: dict[str, str],
    default_cat_name: str = "文档",
    manifest_path: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Sync multiple files to ShowDoc.

    Returns a structured report dict with: total, changed, synced, failed,
    skipped, successes, failures, skipped_items.
    """
    report: dict[str, Any] = {
        "total": len(files),
        "changed": 0,
        "synced": 0,
        "failed": 0,
        "skipped": 0,
        "successes": [],
        "failures": [],
        "skipped_items": [],
    }

    if manifest_path and not dry_run:
        # Compute changed files based on manifest
        files_to_sync = compute_changed(files, manifest_path)
    else:
        files_to_sync = list(files)

    report["changed"] = len(files_to_sync)

    synced_files: list[Path] = []

    for f in files_to_sync:
        rel_path = str(f.relative_to(Path(base_dir))) if Path(base_dir) in [f] + list(f.parents) else str(f)
        try:
            content = f.read_text(encoding="utf-8")
        except Exception as exc:
            report["failed"] += 1
            report["failures"].append({"file": str(f), "error": f"Read error: {exc}"})
            continue

        # Validate Markdown safe subset
        is_valid, reasons = validate_markdown(content)
        if not is_valid:
            report["skipped"] += 1
            report["skipped_items"].append({"file": str(f), "reasons": reasons})
            print(f"  SKIP {rel_path}: validation failed: {'; '.join(reasons)}")
            continue

        page_title = derive_page_title(str(f))
        cat_name = derive_cat_name(str(f), cat_name_mapping, default_cat_name)

        if dry_run:
            print(f"  DRY-RUN would sync: {rel_path} -> {page_title} (cat: {cat_name})")
            report["synced"] += 1
            report["successes"].append({"file": str(f), "page_title": page_title})
            continue

        # API call
        result = sync_file(
            api_url=api_url,
            api_key=api_key,
            api_token=api_token,
            item_id=item_id,
            file_path=str(f),
            file_content=content,
            page_title=page_title,
            cat_name=cat_name,
        )

        if result["success"]:
            report["synced"] += 1
            report["successes"].append({"file": str(f), "page_title": page_title})
            synced_files.append(f)
            print(f"  SYNC {rel_path} -> {page_title}")
        else:
            report["failed"] += 1
            err = result.get("error", "unknown error")
            report["failures"].append({"file": str(f), "error": err})
            print(f"  FAIL {rel_path}: {err}")

    # Update manifest after successful sync (not in dry-run)
    if manifest_path and not dry_run and synced_files:
        update_manifest(synced_files, manifest_path)

    return report


def print_report(report: dict[str, Any]) -> None:
    """Print structured sync report to stdout."""
    print("\n" + "=" * 50)
    print("ShowDoc Sync Report")
    print("=" * 50)
    print(f"  Total files scanned: {report['total']}")
    print(f"  Files changed:       {report['changed']}")
    print(f"  Files synced:        {report['synced']}")
    print(f"  Files failed:        {report['failed']}")
    print(f"  Files skipped:       {report['skipped']}")

    if report["successes"]:
        print("\n  Successes:")
        for s in report["successes"]:
            path = Path(s["file"]).name
            print(f"    ✓ {path} -> {s['page_title']}")

    if report["failures"]:
        print("\n  Failures:")
        for f in report["failures"]:
            path = Path(f["file"]).name
            print(f"    ✗ {path}: {f['error']}")

    if report["skipped_items"]:
        print("\n  Skipped (validation):")
        for s in report["skipped_items"]:
            path = Path(s["file"]).name
            print(f"    ⊘ {path}: {'; '.join(s['reasons'])}")

    print("=" * 50)

    # Exit with non-zero if any failures
    if report["failed"] > 0:
        sys.exit(1)


def main() -> None:
    """Entry point for the sync script."""
    parser = argparse.ArgumentParser(
        description="Sync Markdown docs from GitLab to ShowDoc via Open API",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be synced without making API calls or modifying manifest",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--adapter",
        default=None,
        help="Path to adapter.toml (default: .memory/adapter.toml)",
    )
    args = parser.parse_args()

    # Determine adapter.toml path
    if args.adapter:
        adapter_path = args.adapter
    else:
        # Default: look for .memory/adapter.toml relative to script location
        script_dir = Path(__file__).resolve().parent
        repo_root = script_dir.parent
        adapter_path = str(repo_root / ".memory" / "adapter.toml")

    # Load config
    config = load_config(adapter_path)
    repo_root = str(Path(adapter_path).resolve().parent.parent)

    # Resolve auth
    api_url, api_key, api_token = resolve_auth(config["api_url"])

    # Scan files
    all_files = scan_files(repo_root, config["core_files"], config.get("extra_patterns"))

    if not all_files:
        print("No files found matching the configured patterns.")
        print_report({"total": 0, "changed": 0, "synced": 0, "failed": 0, "skipped": 0,
                       "successes": [], "failures": [], "skipped_items": []})
        return

    # Manifest path: next to adapter.toml
    manifest_path = str(Path(adapter_path).parent / ".showdoc-manifest.json")

    if args.dry_run:
        print(f"DRY-RUN mode: {len(all_files)} files scanned, no API calls will be made.\n")

    # Sync files
    report = sync_files(
        files=all_files,
        api_url=api_url,
        api_key=api_key,
        api_token=api_token,
        item_id=config["item_id"],
        base_dir=repo_root,
        cat_name_mapping=config["cat_name_mapping"],
        default_cat_name="文档",
        manifest_path=manifest_path,
        dry_run=args.dry_run,
    )

    # Print report
    print_report(report)


if __name__ == "__main__":
    main()
