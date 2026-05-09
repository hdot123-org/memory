#!/usr/bin/env python3
"""Smoke tests for MEMORY_HOOK_ADAPTER=default — regression for IndexError crash.

Covers:
- default adapter must not crash on build_context_package_simple (IndexError on project_map_files[1])
- default adapter reports a serializable status ('ok' or 'degraded')
- default adapter works for codex / claude / factory hosts
"""

from __future__ import annotations

import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Helper: reset adapter to default and force-reload gateway modules
# ---------------------------------------------------------------------------

_MODULE_PREFIXES = (
    "memory_core.tools.memory_hook",
)


def _reset_to_default_adapter() -> None:
    """Set MEMORY_HOOK_ADAPTER=default and purge cached gateway modules."""
    os.environ["MEMORY_HOOK_ADAPTER"] = "default"
    for name in list(sys.modules.keys()):
        if any(name.startswith(prefix) for prefix in _MODULE_PREFIXES):
            del sys.modules[name]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDefaultAdapterNoCrash:
    """Default adapter must not crash on build_context_package_simple."""

    def test_default_adapter_build_context_package_does_not_crash(self):
        """Regression: default adapter must not crash on build_context_package_simple."""
        _reset_to_default_adapter()
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        pkg = build_context_package_simple("codex", "session-start", {})
        assert pkg is not None
        assert "status" in pkg
        # status can be ok or degraded, but must not crash
        assert pkg["status"] in ("ok", "degraded")

    def test_default_adapter_status_ok_on_clean_env(self):
        """If repo state is clean, default adapter should report status ok (or degraded with details)."""
        _reset_to_default_adapter()
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        pkg = build_context_package_simple("codex", "session-start", {})
        assert pkg is not None
        assert "status" in pkg
        if pkg["status"] != "ok":
            # Output missing_paths and validation_errors to aid debugging
            print("\nmissing_paths:", pkg.get("missing_paths"))
            print("validation_errors:", pkg.get("validation_errors"))
        # Must not crash; status must be serializable
        assert pkg["status"] in ("ok", "degraded")

    @pytest.mark.parametrize("host", ["claude", "factory"])
    def test_default_adapter_for_host(self, host: str):
        """Default adapter must not crash for claude and factory hosts."""
        _reset_to_default_adapter()
        from memory_core.tools.memory_hook_gateway import build_context_package_simple

        pkg = build_context_package_simple(host, "session-start", {})
        assert pkg is not None
        assert "status" in pkg
        assert pkg["status"] in ("ok", "degraded")
