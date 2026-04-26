#!/usr/bin/env python3
"""One-click rollback drill for memory-hook core provider.

Usage:
  python3 workspace/tools/memory_hook_provider_rollback.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from workspace.tools import memory_hook_gateway as gateway


def run_rollback_drill() -> dict[str, Any]:
    requested_provider = os.environ.get("MEMORY_HOOK_CORE_PROVIDER", gateway.DEFAULT_CORE_PROVIDER)
    try:
        external_provider, _, external_errors = gateway._resolve_core_builder("external-core")
    except Exception as exc:
        external_provider = "external-core"
        external_errors = [str(exc)]

    try:
        legacy_provider, _, legacy_errors = gateway._resolve_core_builder("legacy")
    except Exception as exc:
        legacy_provider = "legacy"
        legacy_errors = [str(exc)]

    external_probe_ok = external_provider == "external-core" and not external_errors
    legacy_probe_ok = legacy_provider == "legacy" and not legacy_errors
    passed = external_probe_ok and legacy_probe_ok
    return {
        "status": "passed" if passed else "failed",
        "requested_provider": requested_provider,
        "external_probe_provider": external_provider,
        "external_probe_errors": external_errors,
        "external_probe_ok": external_probe_ok,
        "legacy_probe_provider": legacy_provider,
        "legacy_probe_errors": legacy_errors,
        "legacy_probe_ok": legacy_probe_ok,
        "rollback_target": "legacy",
    }


def main() -> int:
    result = run_rollback_drill()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
