#!/usr/bin/env python3
"""Probe provider availability for memory-hook core.

This module **does not perform rollback**. It probes whether the
external-core and legacy providers can be resolved by the gateway,
and returns a structured diagnostic result.

Usage:
  python3 workspace/tools/memory_hook_provider_probe.py
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


def probe_provider_availability() -> dict[str, Any]:
    """Probe external-core and legacy provider resolvability.

    Returns a dict with probe results for both providers and an overall
    ``status`` key (``"passed"`` when legacy is available).
    """
    requested_provider = os.environ.get("MEMORY_HOOK_CORE_PROVIDER", "legacy")

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
    passed = legacy_probe_ok

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


# Backwards-compatible alias – old name, same behaviour.
run_rollback_drill = probe_provider_availability


def main() -> int:
    result = probe_provider_availability()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
