#!/usr/bin/env python3
"""Smoke tests for MEMORY_HOOK_ADAPTER=default — status='ok' regression.

Covers:
- default adapter must return status='ok' on build_context_package_simple
- default adapter works for codex / claude / factory hosts
- graceful handling when paths are missing (ci environment)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helper: reset adapter to default and force-reload gateway modules
# ---------------------------------------------------------------------------

_MODULE_PREFIXES = (
    "memory_core.tools.memory_hook",
    "memory_core.tools.memory_root_discovery",
)


def _reset_to_default_adapter() -> None:
    """Set MEMORY_HOOK_ADAPTER=default and purge cached gateway modules."""
    os.environ["MEMORY_HOOK_ADAPTER"] = "default"
    for name in list(sys.modules.keys()):
        if any(name.startswith(prefix) for prefix in _MODULE_PREFIXES):
            del sys.modules[name]


def _workspace_is_complete() -> bool:
    """Check whether the workspace has the full kb/doc structure.

    CI runners checkout the repo without the workspace memory tree,
    so project-map / legal-core / truth-model files are absent.
    In that case the adapter correctly reports 'degraded'.
    """
    workspace = Path(__file__).resolve().parent.parent / "workspace"
    return (workspace / "memory" / "kb" / "global" / "INDEX.md").exists()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDefaultAdapterNoCrash:
    """Default adapter must return status='ok' on build_context_package_simple."""

    def test_default_adapter_build_context_package_does_not_crash(self):
        """Regression: default adapter must not crash on build_context_package_simple."""
        _reset_to_default_adapter()
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        pkg = build_context_package_simple("codex", "session-start", {})
        assert pkg is not None
        assert "status" in pkg
        # status must be ok (or degraded with graceful missing_paths)
        assert pkg["status"] in ("ok", "degraded")

    @pytest.mark.skipif(not _workspace_is_complete(), reason="workspace memory tree incomplete (CI)")
    def test_default_adapter_status_ok_on_clean_env(self):
        """Default adapter must report status='ok' when all generic kb files are present."""
        _reset_to_default_adapter()
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        pkg = build_context_package_simple("codex", "session-start", {})
        assert pkg is not None
        assert "status" in pkg
        assert pkg["status"] == "ok", (
            f"status={pkg['status']} "
            f"missing_paths={pkg.get('missing_paths')} "
            f"validation_errors={pkg.get('validation_errors')}"
        )

    @pytest.mark.parametrize("host", ["claude", "factory"])
    def test_default_adapter_for_host(self, host: str):
        """Default adapter must return status='ok' for claude and factory hosts."""
        _reset_to_default_adapter()
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        pkg = build_context_package_simple(host, "session-start", {})
        assert pkg is not None
        assert "status" in pkg
        if _workspace_is_complete():
            assert pkg["status"] == "ok", (
                f"host={host} status={pkg['status']} "
                f"missing_paths={pkg.get('missing_paths')} "
                f"validation_errors={pkg.get('validation_errors')}"
            )
        else:
            # CI: workspace incomplete — adapter must degrade gracefully
            assert pkg["status"] in ("ok", "degraded"), (
                f"host={host} status={pkg['status']} — unexpected failure"
            )
